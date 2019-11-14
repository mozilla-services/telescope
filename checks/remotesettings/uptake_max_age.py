"""
The age of data percentiles obtained from Uptake Telemetry should be under the specified
maximums.

For each specified max percentile the value obtained is returned.
The min/max timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/65071/
"""
from typing import Dict

from poucave.typings import CheckResult
from poucave.utils import fetch_redash


REDASH_QUERY_ID = 65071


async def run(api_key: str, max_percentiles: Dict[str, int]) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)
    age_percentiles = rows[0]["age_percentiles"]

    percentiles = {}
    for percentile, max_value in max_percentiles.items():
        value = age_percentiles[int(percentile)]
        percentiles[percentile] = {"value": value, "max": max_value}

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)
    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "percentiles": percentiles,
    }
    all_less = all(p["value"] < p["max"] for p in data["percentiles"].values())

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
    return all_less, data
