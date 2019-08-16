"""
The recipes in the Remote Settings collection should match the Normandy API.
"""
import aiohttp


async def run(request, normandy_server, remotesettings_server):
    async with aiohttp.ClientSession() as session:
        remotesettings_url = (
            f"{remotesettings_server}/buckets/main/collections/normandy-recipes/records"
        )
        normandy_url = f"{normandy_server}/api/v1/recipe/?enabled=true&is_approved=true"
        async with session.get(remotesettings_url) as response:
            body = await response.json()
            remotesettings_recipes = body["data"]
        async with session.get(normandy_url) as response:
            normandy_recipes = await response.json()

        remotesettings_ids = {r["id"] for r in remotesettings_recipes}
        normandy_recipes = {r["id"] for r in normandy_recipes}
        diff = normandy_recipes - remotesettings_ids

    return len(diff) == 0, list(diff)
