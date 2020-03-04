"""
The age of data percentiles obtained from Uptake Telemetry should be under the specified
maximums.

For each specified max percentile the value obtained is returned.
The min/max timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/65071/
"""
from typing import Dict, List

from poucave.typings import CheckResult
from poucave.utils import fetch_redash


REDASH_QUERY_ID = 65071


async def run(
    api_key: str, max_percentiles: Dict[str, int], channels: List[str] = ["release"]
) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)
    rows = [row for row in rows if row["channel"].lower() in channels]

    # If no changes were published during this period, then percentiles can be empty.
    if len(rows) == 0:
        return True, {"percentiles": "No broadcast data during this period."}

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)
    data = {"min_timestamp": min_timestamp, "max_timestamp": max_timestamp}

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
