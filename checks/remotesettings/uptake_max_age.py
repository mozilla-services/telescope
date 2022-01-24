"""
The age of data percentiles obtained from Uptake Telemetry should be under the specified
maximums.

For each specified max percentile the value obtained is returned.
The min/max timestamps give the datetime range of the obtained dataset.
"""
from typing import Dict, List

from telescope.typings import CheckResult
from telescope.utils import csv_quoted, fetch_bigquery

from .utils import current_firefox_esr


EVENTS_TELEMETRY_QUERY = r"""
-- This query returns the percentiles for the sync duration and age of data, by source.

-- The events table receives data every 5 minutes.

WITH event_uptake_telemetry AS (
    SELECT
      timestamp AS submission_timestamp,
      normalized_channel AS channel,
      -- Periods of 10min
      UNIX_SECONDS(timestamp) - MOD(UNIX_SECONDS(timestamp), 600) AS period,
      SAFE_CAST(`moz-fx-data-shared-prod`.udf.get_key(event_map_values, "age") AS INT64) AS age
    FROM
        `moz-fx-data-shared-prod.telemetry_derived.events_live`
    WHERE
      timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)
      {channel_condition}
      {version_condition}
      AND event_category = 'uptake.remotecontent.result'
      AND event_object = 'remotesettings'
      AND event_string_value = 'success'
      AND `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "source") = 'settings-changes-monitoring'
      AND `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "trigger") = 'broadcast'
),
total_count_by_period AS (
    SELECT period, channel, COUNT(*) AS total
    FROM event_uptake_telemetry
    GROUP BY period, channel
)
SELECT
    -- If no period has enough total. Fallback to min/max timestamp of above query.
    COALESCE(MIN(submission_timestamp), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {period_hours} HOUR)) AS min_timestamp,
    COALESCE(MAX(submission_timestamp), CURRENT_TIMESTAMP()) AS max_timestamp,
    et.channel,
    SUM(total) AS total_received,
    APPROX_QUANTILES(age, 100) AS age_percentiles
FROM
    event_uptake_telemetry AS et,
    total_count_by_period AS tc
WHERE et.period = tc.period
  AND et.channel = tc.channel
  AND et.age IS NOT NULL
  -- This removes noise on periods where there is no change published.
  -- See also https://bugzilla.mozilla.org/show_bug.cgi?id=1614716
  AND ((et.channel = 'nightly' AND total > 2000) OR total > 10000)
GROUP BY et.channel
"""


async def run(
    max_percentiles: Dict[str, int],
    channels: List[str] = ["release"],
    period_hours: int = 6,
    include_legacy_versions: bool = False,
) -> CheckResult:
    version_condition = ""
    if not include_legacy_versions:
        min_version = await current_firefox_esr()
        version_condition = f"AND SAFE_CAST(SPLIT(app_version, '.')[OFFSET(0)] AS INTEGER) >= {min_version[0]}"
    channel_condition = (
        f"AND LOWER(normalized_channel) IN ({csv_quoted(channels)})" if channels else ""
    )
    rows = await fetch_bigquery(
        EVENTS_TELEMETRY_QUERY.format(
            period_hours=period_hours,
            channel_condition=channel_condition,
            version_condition=version_condition,
        )
    )

    # If no changes were published during this period, then percentiles can be empty.
    if len(rows) == 0:
        return True, {"percentiles": "No broadcast data during this period."}

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)
    data = {
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
    }

    age_percentiles = rows[0]["age_percentiles"]

    percentiles = {}
    for percentile, max_value in max_percentiles.items():
        value = age_percentiles[int(percentile)]
        percentiles[percentile] = {"value": value, "max": max_value}

    all_less = all(p["value"] < p["max"] for p in percentiles.values())

    """
    {
      "min_timestamp": "2019-09-26T10:46:09.079",
      "max_timestamp": "2019-09-27T10:38:55.064",
      "percentiles": {
        "1": {
          "value": 68,
          "max": 120
        },
        "5": {
          "value": 248,
          "max": 600
        },
        "50": {
          "value": 764,
          "max": 1200
        }
      }
    }
    """
    return all_less, {**data, "percentiles": percentiles}
