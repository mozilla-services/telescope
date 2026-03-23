"""
The sync duration percentiles obtained from Uptake Telemetry should be under the specified
maximums.

For each specified max percentile the value obtained is returned.
The min/max timestamps give the datetime range of the obtained dataset.
"""

from typing import Dict, List

from telescope.typings import CheckResult
from telescope.utils import csv_quoted, fetch_bigquery

from .utils import current_firefox_esr


EVENTS_TELEMETRY_QUERY = r"""
-- This query returns the percentiles for the sync duration, by source.

-- The events table receives data every 5 minutes.

WITH event_uptake_telemetry AS (
    SELECT
      submission_timestamp,
      normalized_channel AS channel,
      mozfun.map.get_key(e.extra, 'source') AS source,
      SAFE_CAST(mozfun.map.get_key(e.extra, 'duration') AS INT64) AS duration
    FROM
      `moz-fx-data-shared-prod.firefox_desktop_live.events_v1`
    INNER JOIN UNNEST(events) AS e ON
      e.category = 'uptake.remotecontent.result'
      AND e.name = 'uptake_remotesettings'
    WHERE
      submission_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)
      AND mozfun.map.get_key(e.extra, 'value') = 'success'
      {channel_condition}
      {version_condition}
)
SELECT
    MIN(submission_timestamp) AS min_timestamp,
    MAX(submission_timestamp) AS max_timestamp,
    channel,
    source,
    APPROX_QUANTILES(duration, 100) AS duration_percentiles
FROM event_uptake_telemetry
WHERE duration > 0
  AND source = '{source}'
GROUP BY channel, source
-- We sort channel DESC to have release first for retrocompat reasons.
ORDER BY channel DESC, source, min_timestamp
"""


async def run(
    max_percentiles: Dict[str, int],
    source: str = "settings-sync",
    channels: List[str] = ["release"],
    period_hours: int = 6,
    include_legacy_versions: bool = False,
) -> CheckResult:
    version_condition = ""
    if not include_legacy_versions:
        min_version = await current_firefox_esr()
        version_condition = f"AND SAFE_CAST(mozfun.norm.truncate_version(client_info.app_display_version, 'major') AS INTEGER) >= {min_version[0]}"
    channel_condition = (
        f"AND LOWER(normalized_channel) IN ({csv_quoted(channels)})" if channels else ""
    )
    rows = await fetch_bigquery(
        EVENTS_TELEMETRY_QUERY.format(
            source=source,
            channel_condition=channel_condition,
            version_condition=version_condition,
            period_hours=period_hours,
        )
    )
    if len(rows) == 0:
        raise ValueError(f"No data for source {source} and channels {channels}")

    duration_percentiles = rows[0]["duration_percentiles"]

    # Percentiles have `str` type because config keys are strings in TOML.
    # (eg. ``params.max_percentiles.50 = 1000``)
    percentiles = {}
    for percentile, max_value in max_percentiles.items():
        value = duration_percentiles[int(percentile)]
        percentiles[percentile] = {"value": value, "max": max_value}

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)
    data = {
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
        "percentiles": percentiles,
    }
    all_less = all(p["value"] < p["max"] for p in data["percentiles"].values())

    """
    {
      "min_timestamp": "2019-09-26T10:19:31.229",
      "max_timestamp": "2019-09-27T10:15:10.882",
      "percentiles": {
        "50": {
          "value": 405,
          "max": 1000
        },
        "95": {
          "value": 7385,
          "max": 8000
        }
      }
    }
    """
    return all_less, data
