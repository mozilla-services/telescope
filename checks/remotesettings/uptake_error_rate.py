"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum.

For each collection whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/64808/
"""
from collections import defaultdict
from typing import Dict, List

from poucave.typings import CheckResult
from poucave.utils import fetch_redash

EXPOSED_PARAMETERS = [
    "max_error_percentage",
    "min_total_events",
    "ignore_status",
    "ignore_versions",
]

REDASH_QUERY_ID = 65039


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def run(
    api_key: str,
    max_error_percentage: float,
    min_total_events: int = 10000,
    ignore_status: List[str] = [],
    ignore_versions: List[int] = [],
) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    by_collection: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in rows:
        by_collection[row["source"]][row["version"]][row["status"]] = row["total"]

    error_rates = {}
    for cid, all_versions in by_collection.items():
        total_statuses = 0
        statuses: Dict[str, int] = defaultdict(int)
        ignored: Dict[str, int] = defaultdict(int)

        for version, all_statuses in all_versions.items():
            for status, total in all_statuses.items():
                total_statuses += total
                if status in ignore_status or int(version) in ignore_versions:
                    ignored[status] += total
                else:
                    statuses[status] += total

        # Ignore uptake Telemetry of a certain collection if the total of collected
        # events is too small.
        if total_statuses < min_total_events:
            continue

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
