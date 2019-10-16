"""
Recipes available on the server should match the recipes clients are reporting
Uptake Telemetry about.

The list of recipes for which no event was received is returned. The min/max
timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/64921/
"""
from collections import defaultdict

import aiohttp

from poucave.typings import CheckResult
from poucave.utils import fetch_redash

EXPOSED_PARAMETERS = ["server"]

REDASH_QUERY_ID = 64921

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"


async def run(api_key: str, server: str, min_total_events: int = 1000) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    count_by_id = defaultdict(int)
    for row in rows:
        rid = int(row["source"].split("/")[-1])
        count_by_id[rid] += row["total"]

    async with aiohttp.ClientSession() as session:
        # Recipes from source of truth.
        normandy_url = NORMANDY_URL.format(server=server)
        async with session.get(normandy_url) as response:
            normandy_recipes = await response.json()

    normandy_recipes = set(r["recipe"]["id"] for r in normandy_recipes)

    reported_recipes = set(count_by_id.keys())

    missing = list(normandy_recipes - reported_recipes)

    extras = list(reported_recipes - normandy_recipes)
    extras = [rid for rid in extras if count_by_id[rid] > min_total_events]

    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "missing": missing,
        "extras": extras,
    }
    return len(missing) == len(extras) == 0, data
