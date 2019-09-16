"""
WIP

    {
      "security-state/cert-revocations": {
        "error_rate": 54.45,
        "statuses": {
          "network_error": 17774,
          "up_to_date": 14709,
          "success": 349,
          "sync_error": 225
        }
      },
      "security-state/intermediates": {
        "error_rate": 33.62,
        "statuses": {
          "up_to_date": 49164,
          "network_error": 18740,
          "parse_error": 7983,
          "success": 6699,
          "sync_error": 986,
          "custom_1_error": 569,
          "apply_error": 8,
          "sign_retry_error": 7,
          "sign_error": 3
        }
      },

"""
import os
from collections import defaultdict

import aiohttp


QUERY_ID = 64808
REDASH_URI = (
    f"https://sql.telemetry.mozilla.org/api/queries/{QUERY_ID}/results.json?api_key="
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


async def run(api_key: str, max_percentage: float):
    rows = await fetch_redash(api_key)

    by_collection = defaultdict(dict)
    for row in rows:
        by_collection[row["source"]][row["status"]] = row["total"]

    error_rates = {}
    for cid, statuses in by_collection.items():
        total_errors = sum(
            total for status, total in statuses.items() if status.endswith("_error")
        )
        total_statuses = sum(total for status, total in statuses.items())
        error_rate = round(total_errors * 100 / total_statuses, 2)

        if error_rate < max_percentage:
            continue

        error_rates[cid] = {
            "error_rate": error_rate,
            "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
        }

    sort_by_rate = sort_dict_desc(error_rates, key=lambda item: item[1]["error_rate"])

    return len(sort_by_rate) == 0, sort_by_rate
