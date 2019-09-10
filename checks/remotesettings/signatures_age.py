"""
Signatures should be refreshed periodically, keeping their age under a maximum of hours.
"""
import asyncio
from datetime import datetime, timezone

from kinto_http import Client, BearerTokenAuth

from .utils import fetch_signed_resources


def utcnow():
    # Tiny wrapper, used for mocking in tests.
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def get_signature_age_hours(client, bucket, collection):
    data = client.get_collection(bucket=bucket, id=collection)["data"]
    signature_date = data.get("last_signature_date")
    if signature_date is None:
        age = None
    else:
        dt = datetime.fromisoformat(signature_date)
        delta = utcnow() - dt
        age = int(delta.days * 24 + delta.seconds / 3600)
    return age


# TODO: should retry requests. cf. lambdas code
async def run(query, server, auth, max_age):
    max_age = int(query.get("max_age", max_age))

    _type = None
    if " " in auth:
        # eg, "Bearer ghruhgrwyhg"
        _type, auth = auth.split(" ", 1)
    auth = (
        tuple(auth.split(":", 1)) if ":" in auth else BearerTokenAuth(auth, type=_type)
    )
    client = Client(server_url=server, auth=auth)

    source_collections = [
        (r["source"]["bucket"], r["source"]["collection"])
        for r in fetch_signed_resources(server, auth)
    ]

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(None, get_signature_age_hours, client, bid, cid)
        for (bid, cid) in source_collections
    ]
    results = await asyncio.gather(*futures)

    ages = {
        f"{bid}/{cid}": age for ((bid, cid), age) in zip(source_collections, results)
    }
    all_good = all([age is not None and age < max_age for age in ages.values()])
    return all_good, ages
