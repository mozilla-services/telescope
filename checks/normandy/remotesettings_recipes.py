"""
The recipes in the Remote Settings collection should match the Normandy API. The
collection of recipes with capabilities should contain all baseline recipes.

The lists of missing and extraneous recipes are returned, as well the list of
inconsistencies between the baseline and capabilities collections.
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_json

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"
REMOTESETTINGS_URL = "{server}/buckets/main/collections/{cid}/records"


async def run(normandy_server: str, remotesettings_server: str) -> CheckResult:
    # Recipes from source of truth.
    normandy_url = NORMANDY_URL.format(server=normandy_server)
    normandy_recipes = await fetch_json(normandy_url)
    normandy_by_id = {r["recipe"]["id"]: r["recipe"] for r in normandy_recipes}

    # Baseline recipes published on Remote Settings.
    rs_recipes = REMOTESETTINGS_URL.format(
        server=remotesettings_server, cid="normandy-recipes"
    )
    body = await fetch_json(rs_recipes)
    rs_recipes = body["data"]
    rs_baseline_by_id = {r["recipe"]["id"]: r["recipe"] for r in rs_recipes}

    # Recipes with advanced capabilities.
    rs_recipes_caps = REMOTESETTINGS_URL.format(
        server=remotesettings_server, cid="normandy-recipes-capabilities"
    )
    body = await fetch_json(rs_recipes_caps)
    rs_recipes_caps = body["data"]
    rs_capabilities_by_id = {r["recipe"]["id"]: r["recipe"] for r in rs_recipes_caps}

    # Make sure the baseline recipes are all listed in the capabilites collection.
    missing_caps = []
    for rid, r in rs_baseline_by_id.items():
        if rid not in rs_capabilities_by_id:
            missing_caps.append({"id": r["id"], "name": r["name"]})

    # Make sure the baseline recipes are all listed in the baseline collection
    missing = []
    for rid, r in normandy_by_id.items():
        published = rs_baseline_by_id.pop(rid, None)
        if published is None:
            missing.append({"id": r["id"], "name": r["name"]})
    extras = [{"id": r["id"], "name": r["name"]} for r in rs_baseline_by_id.values()]

    ok = (len(missing_caps) + len(missing) + len(extras)) == 0
    return ok, {"inconsistent": missing_caps, "missing": missing, "extras": extras}
