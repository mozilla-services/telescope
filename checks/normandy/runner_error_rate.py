"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum. Error rate is computed for each period of 10min.

For each recipe whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/68108/
"""
from collections import defaultdict
from typing import Dict, List, Tuple

from poucave.typings import CheckResult
from poucave.utils import fetch_redash


EXPOSED_PARAMETERS = ["max_error_percentage", "min_total_events"]

REDASH_QUERY_ID = 68108

# Normandy uses the Uptake telemetry statuses in a specific way.
# See https://searchfox.org/mozilla-central/rev/4218cb868d8deed13e902718ba2595d85e12b86b/toolkit/components/normandy/lib/Uptake.jsm#23-43
NORMANDY_STATUSES = {
    "custom_1_error": "recipe_action_disabled",
    "backoff": "recipe_didnt_match_filter",
    "apply_error": "recipe_execution_error",
    "content_error": "recipe_filter_broken",
    "download_error": "recipe_invalid_action",
    "signature_error": "runner_invalid_signature",
}
UPTAKE_STATUSES = {v: k for k, v in NORMANDY_STATUSES.items()}


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def run(
    api_key: str,
    max_error_percentage: float,
    min_total_events: int = 20,
    ignore_status: List[str] = [],
    channels: List[str] = [],
) -> CheckResult:
    # Ignored statuses are specified using the Normandy ones.
    ignored_status = [UPTAKE_STATUSES.get(s, s) for s in ignore_status]

    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    periods: Dict[Tuple[str, str], Dict] = {}
    for row in rows:
        if len(channels) > 0 and row["channel"].lower() not in channels:
            continue
        period: Tuple[str, str] = (row["min_timestamp"], row["max_timestamp"])
        if period not in periods:
            count_by_status: Dict[str, int] = defaultdict(int)
            periods[period] = count_by_status

        # In Firefox 67, `custom_2_error` was used instead of `backoff`.
        status = row["status"].replace("custom_2_error", "backoff")
        periods[period].setdefault(status, 0)
        periods[period][status] += row["total"]

    runner_error_rate = {}
    min_rate = None
    max_rate = None
    for (min_period, max_period), all_statuses in periods.items():
        # Compute error rate by period.
        # This allows us to prevent error rate to be "spread" over the overall datetime
        # range of events (eg. a spike of errors during 10min over 2H).
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

        min_rate = error_rate if min_rate is None else min(min_rate, error_rate)
        max_rate = error_rate if max_rate is None else max(max_rate, error_rate)

        # If error rate for this period is below threshold, or lower than one reported
        # in another period, then we ignore it.
        other_period_rate = runner_error_rate.get("error_rate", 0.0)
        if error_rate < max_error_percentage or error_rate < other_period_rate:
            continue

        runner_error_rate = {
            "error_rate": error_rate,
            "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
            "ignored": sort_dict_desc(ignored, key=lambda item: item[1]),
        }

    data = {
        **runner_error_rate,
        "min_rate": min_rate,
        "max_rate": max_rate,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    """
    {
      "error_rate": 1.62,
      "statuses": {
        "success": 21562,
        "network_error": 326,
        "server_error": 21,
        "sign_error": 9
      },
      "ignored": {},
      "min_rate": 1.16,
      "max_rate": 1.62,
      "min_timestamp": "2020-02-07T11:40:00",
      "max_timestamp": "2020-02-07T13:50:00"
    }
    """
    return len(runner_error_rate) == 0, data
