"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum. Error rate is computed for each period (of 10min by default).

For each source whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
obtained dataset.
"""

from typing import Dict, List, Optional

from telescope.typings import CheckResult
from telescope.utils import csv_quoted, fetch_bigquery

from .utils import current_firefox_esr


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

SELECT
  PARSE_TIMESTAMP('%s', CAST(UNIX_SECONDS(submission_timestamp) - MOD(UNIX_SECONDS(submission_timestamp), {period_sampling_seconds}) AS STRING)) AS period,
  mozfun.map.get_key(e.extra, 'source') AS source,
  CASE WHEN mozfun.map.get_key(e.extra, 'value') = 'success' THEN 'success' ELSE 'error' END AS status,
  COUNT(DISTINCT client_info.client_id) AS row_count
FROM
  `moz-fx-data-shared-prod.firefox_desktop_live.events_v1`
INNER JOIN UNNEST(events) AS e ON
  e.category = 'uptake.remotecontent.result'
  AND e.name = 'uptake_remotesettings'
WHERE submission_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)
  AND mozfun.map.get_key(e.extra, 'value') NOT IN ('up_to_date', 'network_error', 'offline_error', 'shutdown_error')
  AND (mozfun.map.get_key(e.extra, 'value') LIKE '%error%' OR mozfun.map.get_key(e.extra, 'value') = 'success')
  {version_condition}
  {channel_condition}
  {source_condition}
  {status_condition}
GROUP BY period, source, status
ORDER BY source, period DESC, status
"""


async def fetch_remotesettings_uptake(
    channels: List[str],
    sources: List[str],
    ignore_status: List[str],
    period_hours: int,
    period_sampling_seconds: int,
    min_version: Optional[tuple],
):
    version_condition = (
        f"AND SAFE_CAST(mozfun.norm.truncate_version(client_info.app_display_version, 'major') AS INTEGER) >= {min_version[0]}"
        if min_version
        else ""
    )
    channel_condition = (
        f"AND LOWER(normalized_channel) IN ({csv_quoted(channels)})" if channels else ""
    )
    source_condition = (
        f"AND mozfun.map.get_key(e.extra, 'source') IN ({csv_quoted(sources)})"
        if sources
        else ""
    )
    status_condition = (
        f"AND mozfun.map.get_key(e.extra, 'value') NOT IN ({csv_quoted(ignore_status)})"
        if ignore_status
        else ""
    )
    return await fetch_bigquery(
        EVENTS_TELEMETRY_QUERY.format(
            period_hours=period_hours,
            period_sampling_seconds=period_sampling_seconds,
            source_condition=source_condition,
            version_condition=version_condition,
            channel_condition=channel_condition,
            status_condition=status_condition,
        )
    )


async def run(
    max_error_percentage: float,
    min_total_events: int = 1000,
    sources: List[str] = [],
    channels: List[str] = [],
    ignore_status: List[str] = [],
    ignore_versions: List[int] = [],
    period_hours: int = 4,
    period_sampling_seconds: int = 600,
    include_legacy_versions: bool = False,
) -> CheckResult:
    min_version = await current_firefox_esr() if not include_legacy_versions else None

    rows = await fetch_remotesettings_uptake(
        sources=sources,
        channels=channels,
        period_hours=period_hours,
        period_sampling_seconds=period_sampling_seconds,
        ignore_status=ignore_status,
        min_version=min_version,
    )

    if rows is None or len(rows) < 1:
        return False, {"info": "No telemetry data"}

    min_timestamp = min(r["period"] for r in rows)
    max_timestamp = max(r["period"] for r in rows)

    values: Dict[str, Dict] = {}
    for row in rows:
        key = f"{row['period'].isoformat()} {row['source']}"
        if key not in values:
            values[key] = dict(
                source=row["source"],
                period=row["period"].isoformat(),
                error=0,
                success=0,
            )
        value = values[key]
        if row["status"] == "success":
            value["success"] = row["row_count"]
        elif row["status"] == "error":
            value["error"] = row["row_count"]

    min_rate: Optional[float] = None
    max_rate: Optional[float] = None
    min_rate_key: Optional[str] = None
    max_rate_key: Optional[str] = None
    failing = []

    for key, results in values.items():
        success = results["success"]
        error = results["error"]
        total_statuses = success + error

        # Ignore uptake Telemetry of a certain source if the total of collected
        # events is too small.
        if total_statuses < min_total_events:
            continue

        error_rate = round(error * 100 / total_statuses, 2)

        if error_rate >= max_error_percentage:
            failing.append(results)

        if min_rate is None or min_rate > error_rate:
            min_rate = error_rate
            min_rate_key = key
        if max_rate is None or max_rate < error_rate:
            max_rate = error_rate
            max_rate_key = key

    data = {
        "min_rate": min_rate,
        "min_rate_key": min_rate_key,
        "max_rate": max_rate,
        "max_rate_key": max_rate_key,
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
        "failing": failing,
    }
    """
    {
      "min_rate": 2.1,
      "min_rate_key": "2020-01-17T08:10:00 Collection_Name",
      "max_rate": 100,
      "max_rate_key": "2020-01-17T09:20:00 Collection_Name",
      "min_timestamp": "2020-01-17T08:00:00",
      "max_timestamp": "2020-01-17T10:00:00",
      "failing": [{
            "source": "Collection_Name",
            "period": "2020-01-17T09:20:00",
            "success": 0,
            "error": 10,
        }]
    }
    """
    return max_rate is None or max_rate < max_error_percentage, data
