"""
Dummy-check to obtain dates of last approvals by collection.
"""
import asyncio

from .utils import KintoClient as Client, fetch_signed_resources


def get_last_approvals(client, bucket, collection, max_approvals):
    history = client.get_history(
        bucket=bucket,
        **{
            "resource_name": "collection",
            "target.data.id": collection,
            "target.data.status": "to-sign",
            "_limit": max_approvals,
        }
    )

    return [{"date": h["date"], "by": h["user_id"]} for h in history]


async def run(query, server, auth, max_approvals=3):
    client = Client(server_url=server, auth=auth)

    source_collections = [
        (r["source"]["bucket"], r["source"]["collection"])
        for r in fetch_signed_resources(server, auth)
    ]

    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(None, get_last_approvals, client, bid, cid, max_approvals)
        for (bid, cid) in source_collections
    ]
    results = await asyncio.gather(*futures)

    approvals = {
        f"{bid}/{cid}": entries for ((bid, cid), entries) in zip(source_collections, results)
    }

    return True, approvals
