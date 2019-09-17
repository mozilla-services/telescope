"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum.

For each collection whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/64808/
"""
import os
from collections import defaultdict
from typing import Dict, List

import aiohttp

from poucave.typings import CheckResult


EXPOSED_PARAMETERS = ["max_error_percentage", "min_total_events"]

REDASH_URI = (
    f"https://sql.telemetry.mozilla.org/api/queries/64808/results.json?api_key="
)
REQUESTS_TIMEOUT_SECONDS = int(os.getenv("REQUESTS_TIMEOUT_SECONDS", 5))


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def fetch_redash(api_key):
    redash_uri = REDASH_URI + api_key

    timeout = aiohttp.ClientTimeout(total=REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(redash_uri) as response:
            body = await response.json()

    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    return rows


async def run(
    api_key: str,
    max_error_percentage: float,
    min_total_events: int = 10000,
    ignore_status: List[str] = [],
) -> CheckResult:
    rows = await fetch_redash(api_key)

    min_timestamp = "9999"
    max_timestamp = "0000"
    by_collection: Dict[str, Dict[str, int]] = defaultdict(dict)
    for row in rows:
        if row["min_timestamp"] < min_timestamp:
            min_timestamp = row["min_timestamp"]
        if row["max_timestamp"] > max_timestamp:
            max_timestamp = row["max_timestamp"]
        by_collection[row["source"]][row["status"]] = row["total"]

    error_rates = {}
    for cid, all_statuses in by_collection.items():
        total_statuses = sum(total for status, total in all_statuses.items())

        # Ignore uptake Telemetry of a certain collection if the total of collected
        # events is too small.
        if total_statuses < min_total_events:
            continue

        statuses = {
            status: total
            for status, total in all_statuses.items()
            if status not in ignore_status
        }
        ignored = {
            status: total
            for status, total in all_statuses.items()
            if status in ignore_status
        }

        total_errors = sum(
            total for status, total in statuses.items() if status.endswith("_error")
        )
        error_rate = round(total_errors * 100 / total_statuses, 2)

        if error_rate < max_error_percentage:
            continue

        error_rates[cid] = {
            "error_rate": error_rate,
            "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
            "ignored": sort_dict_desc(ignored, key=lambda item: item[1]),
        }

    sort_by_rate = sort_dict_desc(error_rates, key=lambda item: item[1]["error_rate"])

    data = {
        "collections": sort_by_rate,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    """
    {
      collections": {
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
          }
        }
      },
      "min_timestamp": "2019-09-16T03:40:57.894",
      "max_timestamp": "2019-09-16T09:34:07.163"
    }
    """
    return len(sort_by_rate) == 0, data
