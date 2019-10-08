"""
Recipes available on the server should match the recipes clients are reporting
Uptake Telemetry about.

The list of recipes for which no event was received is returned. The min/max
timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/64921/
"""
import aiohttp

from poucave.typings import CheckResult
from poucave.utils import fetch_redash

EXPOSED_PARAMETERS = ["server"]

REDASH_QUERY_ID = 64921

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"


async def run(api_key: str, server: str) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    reported_recipes = set(int(r["source"].split("/")[-1]) for r in rows)

    async with aiohttp.ClientSession() as session:
        # Recipes from source of truth.
        normandy_url = NORMANDY_URL.format(server=server)
        async with session.get(normandy_url) as response:
            normandy_recipes = await response.json()

    normandy_recipes = set(r["recipe"]["id"] for r in normandy_recipes)

    missing = list(normandy_recipes - reported_recipes)

    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
        "missing": missing,
    }
    return len(missing) == 0, data
