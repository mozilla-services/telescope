"""
The total number of 'sign_retry_error' reported in Uptake Telemetry on a period of 10 min
should be under the specified maximum.

For each source, the period during which the maximum number of 'sign_retry_error' was reported
is returned.

The min/max timestamps give the datetime range of the obtained dataset.
"""
from collections import defaultdict

from telescope.typings import CheckResult
from telescope.utils import fetch_bigquery


EXPOSED_PARAMETERS = [
    "max_sign_error_total",
]
DEFAULT_PLOT = ".max_total"


EVENTS_TELEMETRY_QUERY = r"""
-- This query returns the total of 'sign_retry_error' per period and collection.

-- The events table receives data every 5 minutes.

WITH event_uptake_telemetry AS (
    SELECT
      app_version,
      SPLIT(app_version, '.')[OFFSET(0)] AS version,
      normalized_channel,
      `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "source") AS source,
      UNIX_SECONDS(timestamp) - MOD(UNIX_SECONDS(timestamp), {period_sampling_seconds}) AS period,
      event_category,
      event_object
    FROM
        `moz-fx-data-shared-prod.telemetry_derived.events_live`
    WHERE
      timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)
      AND event_category = 'uptake.remotecontent.result'
      AND event_object = 'remotesettings'
      AND event_string_value = 'sign_retry_error'
),
expanded_totals AS (
    SELECT
        period,
        source,
        -- On release and ESR, we sample Telemetry at 1%
        (CASE WHEN normalized_channel = 'release' OR normalized_channel = 'esr' THEN COUNT(*) * 100 ELSE COUNT(*) END) AS total
    FROM event_uptake_telemetry
    WHERE SAFE_CAST(version AS INTEGER) >= {min_version}
    GROUP BY period, source, normalized_channel
)
SELECT
    PARSE_TIMESTAMP('%s', CAST(period AS STRING)) AS min_timestamp,
    PARSE_TIMESTAMP('%s', CAST(period + {period_sampling_seconds} AS STRING)) AS max_timestamp,
    source,
    SUM(total) AS total
FROM expanded_totals
GROUP BY period, source
"""


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def run(
    max_sign_error_total: int,
    period_hours: int = 48,  # inspect last 48H
    period_sampling_seconds: int = 600,  # on periods of 10min
    min_version: int = 91,
) -> CheckResult:
    rows = await fetch_bigquery(
        EVENTS_TELEMETRY_QUERY.format(
            period_hours=period_hours,
            period_sampling_seconds=period_sampling_seconds,
            min_version=min_version,
        )
    )

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    max_and_period_by_collection: dict[str, tuple[int, tuple[str, str]]] = {}
    total_by_period: dict[str, int] = defaultdict(int)

    for row in rows:
        period: tuple[str, str] = (
            row["min_timestamp"].isoformat(),
            row["max_timestamp"].isoformat(),
        )
        total_for_source_on_period = row["total"]
        total_by_period[row["min_timestamp"]] += total_for_source_on_period

        previous_max, _ = max_and_period_by_collection.setdefault(
            row["source"], (total_for_source_on_period, period)
        )
        if total_for_source_on_period > previous_max:
            max_and_period_by_collection[row["source"]] = (
                total_for_source_on_period,
                period,
            )

    max_total = max(total_by_period.values())

    # As information, show the period for each collection where the number of
    # sign errors reported is at its maximum.
    info_by_source = {
        source: {
            "total": total,
            "min_timestamp": period[0],
            "max_timestamp": period[1],
        }
        for source, (total, period) in sort_dict_desc(
            max_and_period_by_collection,
            key=lambda item: item[1][0],  # (source, (total, period))
        ).items()
    }

    data = {
        "max_total": max_total,
        "sources": info_by_source,
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
    }
    """
    {
      "max_total": 7520,
      "sources": {
        "main/public-suffix-list": {
          "total": 6320,
          "min_timestamp": "2020-01-17T08:10:00",
          "max_timestamp": "2020-01-17T08:20:00",
        },
        "main/cfr": {
          "total": 1200,
          "min_timestamp": "2020-01-17T08:10:00",
          "max_timestamp": "2020-01-17T08:20:00",
        },
        ...
      },
      "min_timestamp": "2020-01-17T08:00:00",
      "max_timestamp": "2020-01-17T10:00:00",
    }
    """
    return max_total < max_sign_error_total, data
