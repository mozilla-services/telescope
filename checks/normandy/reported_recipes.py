"""
Recipes available on the server should match the recipes clients are reporting
Uptake Telemetry about.

The list of recipes for which no event was received is returned. The min/max
timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/67658/
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

from poucave.typings import CheckResult
from poucave.utils import fetch_json, fetch_redash, run_parallel


EXPOSED_PARAMETERS = ["server", "min_total_events", "lag_margin"]

REDASH_QUERY_ID = 67658

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"
RECIPE_URL = "{server}/api/v1/recipe/{id}/"

RFC_3339 = "%Y-%m-%dT%H:%M:%S.%fZ"


logger = logging.getLogger(__name__)


async def run(
    api_key: str, server: str, min_total_events: int = 1000, lag_margin: int = 600
) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    count_by_id: Dict[int, int] = defaultdict(int)
    for row in rows:
        rid = int(row["source"].split("/")[-1])
        count_by_id[rid] += row["total"]

    # Recipes from source of truth.
    normandy_url = NORMANDY_URL.format(server=server)
    normandy_recipes = await fetch_json(normandy_url)

    reported_recipes_ids = set(count_by_id.keys())

    normandy_recipes_ids = set(r["recipe"]["id"] for r in normandy_recipes)
    missing = normandy_recipes_ids - reported_recipes_ids

    extras = reported_recipes_ids - normandy_recipes_ids

    # Exclude recipes for which very few events were received.
    extras -= set(rid for rid in extras if count_by_id[rid] < min_total_events)

    # Exclude recipes that were modified recently.
    # (ie. after the Telemetry data window started)
    min_datetime = datetime.fromisoformat(min_timestamp)
    futures = [fetch_json(RECIPE_URL.format(server=server, id=rid)) for rid in extras]
    results = await run_parallel(*futures)
    for result in sorted(results, key=lambda r: r["last_updated"], reverse=True):
        logger.debug(
            "Extra recipe {id} modified on {last_updated} ({count} events)".format(
                count=count_by_id[result["id"]], **result
            )
        )
    # We add a lag margin, because modified recipes take some time to reach the
    # clients. According to current figures obtained from uptake telemetry,
    # 95% of them obtain the changes in less than ~5min (hence default of 10min).
    extras -= set(
        rid
        for rid, details in zip(extras, results)
        if datetime.strptime(details["last_updated"], RFC_3339)
        - timedelta(seconds=lag_margin)
        > min_datetime
    )

    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "missing": sorted(missing),
        "extras": sorted(extras),
    }
    return len(missing) == len(extras) == 0, data
