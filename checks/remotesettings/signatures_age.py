"""

"""
import asyncio
from datetime import datetime, timezone

from kinto_http import exceptions as kinto_exceptions, Client, BearerTokenAuth


def get_signature_date(client, bucket, collection):
    data = client.get_collection(bucket=bucket, id=collection)["data"]
    return data.get("last_signature_date")


def fetch_source_collections(client):
    # List signed collection using capabilities.
    info = client.server_info()
    try:
        resources = info["capabilities"]["signer"]["resources"]
    except KeyError:
        raise ValueError("No signer capabilities found. Run on *writer* server!")

    collections = set()
    monitored = client.get_records(
        bucket="monitor", collection="changes", _sort="bucket,collection"
    )
    for entry in monitored:
        bid = entry["bucket"]
        cid = entry["collection"]

        picked = None
        for resource in resources:
            dest = resource["destination"]
            if dest["bucket"] == bid:
                if dest["collection"] == cid or dest["collection"] is None:
                    collections.add(
                        (
                            resource["source"]["bucket"],
                            resource["source"]["collection"] or cid,
                        )
                    )

    return list(collections)


# TODO: should retry requests. cf. lambdas code
async def run(request, server, auth, max_age):
    max_age = int(request.query.get("max_age", max_age))

    _type = None
    if " " in auth:
        # eg, "Bearer ghruhgrwyhg"
        _type, auth = auth.split(" ", 1)
    auth = (
        tuple(auth.split(":", 1)) if ":" in auth else BearerTokenAuth(auth, type=_type)
    )
    client = Client(server_url=server, auth=auth)

    collections = fetch_source_collections(client)

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(None, get_signature_date, client, bid, cid)
        for (bid, cid) in collections
    ]
    results = await asyncio.gather(*futures)

    ages = {}
    for ((bid, cid), signature_date) in zip(collections, results):
        if signature_date is None:
            age = None
        else:
            dt = datetime.fromisoformat(signature_date)
            delta = datetime.utcnow().replace(tzinfo=timezone.utc) - dt
            age = int(delta.days * 24 + delta.seconds / 3600)
        ages[f"{bid}/{cid}"] = age

    all_good = all([age is not None and age < max_age for age in ages.values()])
    return all_good, ages
