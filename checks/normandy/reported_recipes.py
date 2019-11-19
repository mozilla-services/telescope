"""
Recipes available on the server should match the recipes clients are reporting
Uptake Telemetry about.

The list of recipes for which no event was received is returned. The min/max
timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/64921/
"""
from collections import defaultdict
from datetime import datetime

from poucave.typings import CheckResult
from poucave.utils import fetch_json, fetch_redash, run_parallel


EXPOSED_PARAMETERS = ["server", "min_total_events"]

REDASH_QUERY_ID = 64921

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"
RECIPE_URL = "{server}/api/v1/recipe/{id}/"

RFC_3339 = "%Y-%m-%dT%H:%M:%S.%fZ"


async def run(api_key: str, server: str, min_total_events: int = 1000) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    count_by_id = defaultdict(int)
    for row in rows:
        rid = int(row["source"].split("/")[-1])
        count_by_id[rid] += row["total"]

    # Recipes from source of truth.
    normandy_url = NORMANDY_URL.format(server=server)
    normandy_recipes = await fetch_json(normandy_url)

    reported_recipes_ids = set(count_by_id.keys())

    normandy_recipes_ids = set(r["recipe"]["id"] for r in normandy_recipes)
    missing = list(normandy_recipes_ids - reported_recipes_ids)

    extras = reported_recipes_ids - normandy_recipes_ids

    # Exclude recipes for which very few events were received.
    extras -= set(rid for rid in extras if count_by_id[rid] < min_total_events)

    # Exclude recipes that were modified recently.
    # (ie. after the Telemetry data window started)
    min_datetime = datetime.fromisoformat(min_timestamp)
    futures = [fetch_json(RECIPE_URL.format(server=server, id=rid)) for rid in extras]
    results = await run_parallel(*futures)
    changed_recently = set(
        rid
        for rid, details in zip(extras, results)
        if datetime.strptime(details["last_updated"], RFC_3339) > min_datetime
    )

    extras = list(extras - changed_recently)

    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "missing": missing,
        "extras": extras,
    }
    return len(missing) == len(extras) == 0, data
