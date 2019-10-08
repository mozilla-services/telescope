"""
The recipes in the Remote Settings collection should match the Normandy API.
The lists of missing and extraneous recipes are returned.
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_json

NORMANDY_URL = "{server}/api/v1/recipe/signed/?enabled=1"
REMOTESETTINGS_URL = "{server}/buckets/main/collections/normandy-recipes/records"


async def run(normandy_server: str, remotesettings_server: str) -> CheckResult:
    # Recipes from source of truth.
    normandy_url = NORMANDY_URL.format(server=normandy_server)
    normandy_recipes = await fetch_json(normandy_url)

    # Recipes published on Remote Settings.
    remotesettings_url = REMOTESETTINGS_URL.format(server=remotesettings_server)
    body = await fetch_json(remotesettings_url)
    remotesettings_recipes = body["data"]

    remotesettings_by_id = {
        r["recipe"]["id"]: r["recipe"] for r in remotesettings_recipes
    }
    normandy_by_id = {r["recipe"]["id"]: r["recipe"] for r in normandy_recipes}

    missing = []
    for rid, r in normandy_by_id.items():
        published = remotesettings_by_id.pop(rid, None)
        if published is None:
            missing.append({"id": r["id"], "name": r["name"]})
    extras = [{"id": r["id"], "name": r["name"]} for r in remotesettings_by_id.values()]

    ok = (len(missing) + len(extras)) == 0
    return ok, {"missing": missing, "extras": extras}
