"""
The percentage of reported errors in Uptake Telemetry should be under the specified
maximum. Error rate is computed for each period of 10min.

For each recipe whose error rate is above the maximum, the total number of events
for each status is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/67658/
"""
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from poucave.typings import CheckResult
from poucave.utils import fetch_json, fetch_redash


EXPOSED_PARAMETERS = ["max_error_percentage", "min_total_events"]

REDASH_QUERY_ID = 67658

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"

# Normandy uses the Uptake telemetry statuses in a specific way.
# See https://searchfox.org/mozilla-central/rev/4218cb868d8deed13e902718ba2595d85e12b86b/toolkit/components/normandy/lib/Uptake.jsm#23-43
UPTAKE_STATUSES = {
    "recipe_action_disabled": "custom_1_error",
    "recipe_didnt_match_filter": "backoff",
    "recipe_execution_error": "apply_error",
    "recipe_filter_broken": "content_error",
    "recipe_invalid_action": "download_error",
    "runner_invalid_signature": "signature_error",
    "action_pre_execution_error": "custom_1_error",
    "action_post_execution_error": "custom_2_error",
}

# Invert status dict {("recipe", "custom_1_error"): "recipe_action_disabled", ...}
NORMANDY_STATUSES = {(k.split("_")[0], v): k for k, v in UPTAKE_STATUSES.items()}


def sort_dict_desc(d, key):
    return dict(sorted(d.items(), key=key, reverse=True))


async def run(
    api_key: str,
    max_error_percentage: float,
    server: str,
    max_error_percentage_with_telemetry: float = None,
    max_error_percentage_with_classify_client: float = None,
    min_total_events: int = 20,
    ignore_status: List[str] = [],
    sources: List[str] = [],
    channels: List[str] = [],
) -> CheckResult:
    if max_error_percentage_with_telemetry is None:
        max_error_percentage_with_telemetry = max_error_percentage

    if max_error_percentage_with_classify_client is None:
        max_error_percentage_with_classify_client = max_error_percentage

    # By default, only look at recipes.
    if len(sources) == 0:
        sources = ["recipe"]
    sources = [re.compile(s) for s in sources]

    # Ignored statuses are specified using the Normandy ones.
    ignored_status = [UPTAKE_STATUSES.get(s, s) for s in ignore_status]

    # Fetch list of enabled recipes from Normandy server.
    normandy_url = NORMANDY_URL.format(server=server)
    normandy_recipes = await fetch_json(normandy_url)
    enabled_recipes_by_ids = {
        str(r["recipe"]["id"]): r["recipe"] for r in normandy_recipes
    }
    enabled_recipe_ids = enabled_recipes_by_ids.keys()

    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # We will store reported events by period, by collection,
    # by version, and by status.
    # {
    #   ('2020-01-17T07:50:00', '2020-01-17T08:00:00'): {
    #     'recipes/113': {
    #       'success': 4699,
    #       'sync_error': 39
    #     },
    #     ...
    #   }
    # }
    periods: Dict[Tuple[str, str], Dict] = {}
    for row in rows:
        # Check if the source matches the selected ones.
        source = row["source"].replace("normandy/", "")
        if not any(s.match(source) for s in sources):
            continue

        # Filter by channel if parameter is specified.
        if channels and row["channel"].lower() not in channels:
            continue

        period: Tuple[str, str] = (row["min_timestamp"], row["max_timestamp"])
        periods.setdefault(period, defaultdict(Counter))

        status = row["status"]
        if "recipe" in source:
            # Make sure this recipe is enabled, otherwise ignore.
            rid = row["source"].split("/")[-1]
            if rid not in enabled_recipe_ids:
                continue
            # In Firefox 67, `custom_2_error` was used instead of `backoff`.
            if status == "custom_2_error":
                status = "backoff"

        periods[period][source][status] += row["total"]

    error_rates: Dict[str, Dict] = {}
    min_rate = None
    max_rate = None
    for (min_period, max_period), by_collection in periods.items():
        # Compute error rate by period.
        # This allows us to prevent error rate to be "spread" over the overall datetime
        # range of events (eg. a spike of errors during 10min over 2H).
        for source, all_statuses in by_collection.items():
            total_statuses = sum(total for status, total in all_statuses.items())

            # Ignore uptake Telemetry of a certain recipe if the total of collected
            # events is too small.
            if total_statuses < min_total_events:
                continue

            # Show overridden status in check output.
            source_type = source.split("/")[0]
            statuses = {
                NORMANDY_STATUSES.get((source_type, status), status): total
                for status, total in all_statuses.items()
                if status not in ignored_status
            }
            ignored = {
                NORMANDY_STATUSES.get((source_type, status), status): total
                for status, total in all_statuses.items()
                if status in ignored_status
            }
            total_errors = sum(
                total
                for status, total in statuses.items()
                if UPTAKE_STATUSES.get(status, status).endswith("_error")
            )
            error_rate = round(total_errors * 100 / total_statuses, 2)

            min_rate = error_rate if min_rate is None else min(min_rate, error_rate)
            max_rate = error_rate if max_rate is None else max(max_rate, error_rate)

            # If error rate for this period is below threshold, or lower than one reported
            # in another period, then we ignore it.
            other_period_rate = error_rates.get(source, {"error_rate": 0.0})[
                "error_rate"
            ]

            details = {}
            max_percentage = max_error_percentage
            if "recipe" in source:
                rid = source.split("/")[-1]
                recipe = enabled_recipes_by_ids[rid]
                with_telemetry = "normandy.telemetry" in recipe["filter_expression"]
                with_classify_client = "normandy.country" in recipe["filter_expression"]
                details["name"] = recipe["name"]
                details["with_telemetry"] = with_telemetry
                details["with_classify_client"] = with_classify_client
                if with_telemetry:
                    max_percentage = max_error_percentage_with_telemetry
                # If recipe has both Telemetry and Classify Client, keep highest threshold.
                if with_classify_client:
                    max_percentage = max(
                        max_percentage, max_error_percentage_with_classify_client
                    )

            if error_rate < max_percentage or error_rate < other_period_rate:
                continue

            error_rates[source] = {
                "error_rate": error_rate,
                **details,
                "statuses": sort_dict_desc(statuses, key=lambda item: item[1]),
                "ignored": sort_dict_desc(ignored, key=lambda item: item[1]),
                "min_timestamp": min_period,
                "max_timestamp": max_period,
            }

    sort_by_rate = sort_dict_desc(error_rates, key=lambda item: item[1]["error_rate"])

    data = {
        "sources": sort_by_rate,
        "min_rate": min_rate,
        "max_rate": max_rate,
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    """
    {
      "sources": {
        "recipes/123": {
          "error_rate": 60.4,
          "name": "Disable OS auth",
          "with_classify_client": true,
          "with_telemetry": false,
          "statuses": {
            "recipe_execution_error": 56,
            "success": 35,
            "action_post_execution_error": 5
          },
          "ignored": {
            "recipe_didnt_match_filter": 5
          },
          "min_timestamp": "2020-01-17T08:10:00",
          "max_timestamp": "2020-01-17T08:20:00",
        },
        ...
      },
      "min_rate": 2.1,
      "max_rate": 60.4,
      "min_timestamp": "2020-01-17T08:00:00",
      "max_timestamp": "2020-01-17T10:00:00"
    }
    """
    return len(sort_by_rate) == 0, data
