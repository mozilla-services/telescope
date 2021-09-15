"""
Signatures should be refreshed periodically, keeping their age under a maximum of hours.

The list of collections whose age is over the maximum allowed is returned.
"""
from datetime import datetime

from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcnow

from .utils import KintoClient, fetch_signed_resources


URL_PARAMETERS = ["max_age"]
EXPOSED_PARAMETERS = ["server", "max_age"]


async def get_signature_age_hours(client, bucket, collection):
    collection = await client.get_collection(bucket=bucket, id=collection)
    data = collection["data"]
    signature_date = data["last_signature_date"]
    dt = datetime.fromisoformat(signature_date)
    delta = utcnow() - dt
    age = int(delta.days * 24 + delta.seconds / 3600)
    return age


async def run(server: str, auth: str, max_age: int) -> CheckResult:
    client = KintoClient(server_url=server, auth=auth)

    resources = await fetch_signed_resources(server, auth)
    source_collections = [
        (r["source"]["bucket"], r["source"]["collection"]) for r in resources
    ]

    futures = [
        get_signature_age_hours(client, bid, cid) for (bid, cid) in source_collections
    ]
    results = await run_parallel(*futures)

    ages = {
        f"{bid}/{cid}": age
        for ((bid, cid), age) in zip(source_collections, results)
        if age is None or age > max_age
    }
    all_good = len(ages) == 0
    return all_good, ages
