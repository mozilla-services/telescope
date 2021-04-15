"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum. Error rate is computed for each period of 10min.

For each source whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/67605/
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from poucave.typings import CheckResult
from poucave.utils import fetch_bigquery


EXPOSED_PARAMETERS = [
    "max_error_percentage",
    "min_total_events",
    "ignore_status",
    "ignore_versions",
]
DEFAULT_PLOT = ".max_rate"


EVENTS_TELEMETRY_QUERY = r"""
-- This query returns the total of events received per period, collection, status and version.

-- The events table receives data every 5 minutes.

WITH uptake_telemetry AS (
    SELECT
      timestamp AS submission_timestamp,
      normalized_channel,
      SPLIT(app_version, '.')[OFFSET(0)] AS version,
      `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "source") AS source,
      UNIX_SECONDS(timestamp) - MOD(UNIX_SECONDS(timestamp), 600) AS period,
      event_string_value AS status,
      event_map_values,
      event_category,
      event_object
    FROM
      `moz-fx-data-shared-prod.telemetry_derived.events_live`
    WHERE
      timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)
      AND event_category = 'uptake.remotecontent.result'
      AND event_object = 'remotesettings'
      AND event_string_value <> 'up_to_date'
      AND app_version != '69.0'
      AND app_version != '69.0.1' -- 69.0.2, 69.0.3 seem fine.
      AND (normalized_channel != 'aurora' OR app_version NOT LIKE '70%')
)
SELECT
    -- Min/Max timestamps of this period
    PARSE_TIMESTAMP('%s', CAST(period AS STRING)) AS min_timestamp,
    PARSE_TIMESTAMP('%s', CAST(period + 600 AS STRING)) AS max_timestamp,
    source,
    status,
    normalized_channel AS channel,
    version,
    COUNT(*) AS total
FROM uptake_telemetry
GROUP BY period, source, status, channel, version
ORDER BY period, source
"""


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


def parse_ignore_status(ign):
    source, status, version = "*", ign, "*"
    if "@" in ign:
        status, version = ign.split("@")
    if "/" in status or "-" in status:
        source = status
        status = "*"
    if ":" in source:
        source, status = source.split(":")
    return (source, status, version)


async def run(
    max_error_percentage: float,
    min_total_events: int = 1000,
    sources: List[str] = [],
    channels: List[str] = [],
    ignore_status: List[str] = [],
    ignore_versions: List[int] = [],
    period_hours: int = 4,
) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_bigquery(
        EVENTS_TELEMETRY_QUERY.format(period_hours=period_hours)
    )

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # Uptake events can be ignored by status, by version, or by status on a
    # specific version (eg. ``parse_error@68``)
    ignored_statuses = []
    for ign in ignore_status:
        ignored_statuses.append(parse_ignore_status(ign))
    ignored_statuses.extend([("*", "*", str(version)) for version in ignore_versions])

    # We will store reported events by period, by source,
    # by version, and by status.
    # {
    #   ('2020-01-17T07:50:00', '2020-01-17T08:00:00'): {
    #     'settings-sync': {
    #       '71': {
    #         'success': 4699,
    #         'sync_error': 39
    #       },
    #       ...
    #     },
    #     ...
    #   }
    # }
    periods: Dict[Tuple[str, str], Dict] = {}
    for row in rows:
        # Filter by channel if parameter is specified.
        if channels and row["channel"].lower() not in channels:
            continue

        period: Tuple[str, str] = (
            row["min_timestamp"].isoformat(),
            row["max_timestamp"].isoformat(),
        )
        if period not in periods:
            by_source: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
                lambda: defaultdict(dict)
            )
            periods[period] = by_source

        if len(sources) == 0 or row["source"] in sources:
            periods[period][row["source"]][row["version"]][row["status"]] = row["total"]

    error_rates: Dict[str, Dict] = {}
    min_rate: Optional[float] = None
    max_rate: Optional[float] = None
    for (min_period, max_period), by_source in periods.items():
        # Compute error rate by period.
        # This allows us to prevent error rate to be "spread" over the overall datetime
        # range of events (eg. a spike of errors during 10min over 2H).
        for source, all_versions in by_source.items():
            total_statuses = 0
            # Store total by status (which are not ignored).
            statuses: Dict[str, int] = defaultdict(int)
            ignored: Dict[str, int] = defaultdict(int)

            for version, all_statuses in all_versions.items():
                for status, total in all_statuses.items():
                    total_statuses += total
                    # Should we ignore this status, version, status@version?
                    is_ignored = (
                        (source, status, version) in ignored_statuses
                        or (source, status, "*") in ignored_statuses
                        or ("*", status, version) in ignored_statuses
                        or (source, "*", "*") in ignored_statuses
                        or (source, "*", version) in ignored_statuses
                        or ("*", status, "*") in ignored_statuses
                        or ("*", "*", version) in ignored_statuses
                    )
                    if is_ignored:
                        ignored[status] += total
                    else:
                        statuses[status] += total

            # Ignore uptake Telemetry of a certain source if the total of collected
            # events is too small.
            if total_statuses < min_total_events:
                continue

            total_errors = sum(
                total for status, total in statuses.items() if status.endswith("_error")
            )
            error_rate = round(total_errors * 100 / total_statuses, 2)

            min_rate = error_rate if min_rate is None else min(min_rate, error_rate)
            max_rate = error_rate if max_rate is None else max(max_rate, error_rate)

            # If error rate for this period is below threshold, or lower than one reported
            # in another period, then we ignore it.
            other_period_rate = error_rates.get(source, {"error_rate": 0.0})[
                "error_rate"
            ]
            if error_rate < max_error_percentage or error_rate < other_period_rate:
                continue

            error_rates[source] = {
                "error_rate": error_rate,
                "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
                "ignored": sort_dict_desc(ignored, key=lambda item: item[1]),
                "min_timestamp": min_period,
                "max_timestamp": max_period,
            }

        sort_by_rate = sort_dict_desc(
            error_rates, key=lambda item: item[1]["error_rate"]
        )

    data = {
        "sources": sort_by_rate,
        "min_rate": min_rate,
        "max_rate": max_rate,
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
    }
    """
    {
      "sources": {
        "main/public-suffix-list": {
          "error_rate": 6.12,
          "statuses": {
            "up_to_date": 369628,
            "apply_error": 24563,
            "sync_error": 175,
            "success": 150,
            "custom_1_error": 52,
            "sign_retry_error": 5
          },
          "ignored": {
            "network_error": 10476
          },
          "min_timestamp": "2020-01-17T08:10:00",
          "max_timestamp": "2020-01-17T08:20:00",
        },
        ...
      },
      "min_rate": 2.1,
      "max_rate": 6.12,
      "min_timestamp": "2020-01-17T08:00:00",
      "max_timestamp": "2020-01-17T10:00:00"
    }
    """
    return len(sort_by_rate) == 0, data
