"""
The sync duration percentiles obtained from Uptake Telemetry should be under the specified
maximums.

For each specified max percentile the value obtained is returned.
The min/max timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/65069/
"""
from typing import Dict

from poucave.typings import CheckResult
from poucave.utils import fetch_redash

REDASH_QUERY_ID = 65069


async def run(
    api_key: str, max_percentiles: Dict[str, int], source: str = "settings-sync"
) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)
    rows = [row for row in rows if row["source"] == source]
    if len(rows) == 0:
        raise ValueError(f"Unknown source {source}")

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
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
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
