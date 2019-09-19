"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum.

For each recipe whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/64921/
"""
from collections import defaultdict
from typing import Dict, List

import aiohttp

from poucave.typings import CheckResult


EXPOSED_PARAMETERS = ["max_error_percentage", "min_total_events"]

REDASH_URI = (
    f"https://sql.telemetry.mozilla.org/api/queries/64921/results.json?api_key="
)

# Normandy uses the Uptake telemetry statuses in a specific way.
# See https://searchfox.org/mozilla-central/rev/4218cb868d8deed13e902718ba2595d85e12b86b/toolkit/components/normandy/lib/Uptake.jsm#23-43
NORMANDY_STATUSES = {
    "custom_1_error": "action_pre_execution_error",
    "custom_2_error": "action_post_execution_error",
    "server_error": "action_server_error",
    "backoff": "recipe_didnt_match_filter",
    "apply_error": "recipe_execution_error",
    "content_error": "recipe_filter_broken",
    "download_error": "recipe_invalid_action",
    "signature_error": "runner_invalid_signature",
}


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def fetch_redash(api_key):
    redash_uri = REDASH_URI + api_key

    async with aiohttp.ClientSession() as session:
        async with session.get(redash_uri) as response:
            body = await response.json()

    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    return rows


async def run(
    api_key: str,
    max_error_percentage: float,
    min_total_events: int = 100,
    ignore_status: List[str] = [],
) -> CheckResult:
    ignored_status = ignore_status + ["backoff"]

    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    by_collection: Dict[str, Dict[str, int]] = defaultdict(dict)
    for row in rows:
        rid = int(row["source"].split("/")[-1])
        by_collection[rid][row["status"]] = row["total"]

    error_rates = {}
    for rid, all_statuses in by_collection.items():
        total_statuses = sum(total for status, total in all_statuses.items())

        # Ignore uptake Telemetry of a certain recipe if the total of collected
        # events is too small.
        if total_statuses < min_total_events:
            continue

        statuses = {
            NORMANDY_STATUSES.get(status, status): total
            for status, total in all_statuses.items()
            if status not in ignored_status
        }
        ignored = {
            NORMANDY_STATUSES.get(status, status): total
            for status, total in all_statuses.items()
            if status in ignored_status
        }
        total_errors = sum(
            total for status, total in statuses.items() if status.endswith("_error")
        )
        error_rate = round(total_errors * 100 / total_statuses, 2)

        if error_rate < max_error_percentage:
            continue

        error_rates[rid] = {
            "error_rate": error_rate,
            "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
            "ignored": sort_dict_desc(ignored, key=lambda item: item[1]),
        }

    sort_by_rate = sort_dict_desc(error_rates, key=lambda item: item[1]["error_rate"])

    data = {
        "recipes": sort_by_rate,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    """
    {
      recipes": {
        "normandy/recipe/532": {
          "error_rate": 60.4,
          "statuses": {
            "recipe_execution_error": 56,
            "runner_success": 35,
            "action_post_execution_error": 5
          },
          "ignored": {
            "backoff": 5
          }
        }
      },
      "min_timestamp": "2019-09-19T03:47:42.773",
      "max_timestamp": "2019-09-19T09:43:26.083"
    }
    """
    return len(sort_by_rate) == 0, data
