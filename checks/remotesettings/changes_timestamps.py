"""
Timestamps of entries in monitoring endpoint should match collection timestamp.
"""
import asyncio

from kinto_http import Client


def get_timestamp(client, bucket, collection, timestamp):
    return client.get_records_timestamp(
        bucket=bucket, collection=collection, _expected=timestamp
    )


# TODO: should retry requests. cf. lambdas code
async def run(request, server):
    loop = asyncio.get_event_loop()

    client = Client(server_url=server, bucket="monitor", collection="changes")
    entries = client.get_records()
    futures = [
        loop.run_in_executor(
            None,
            get_timestamp,
            client,
            entry["bucket"],
            entry["collection"],
            entry["last_modified"],
        )
        for entry in entries
    ]
    results = await asyncio.gather(*futures)
    failing = []
    for (entry, timestamp) in zip(entries, results):
        cid = "{bucket}/{collection}".format(**entry)
        if str(timestamp) != str(entry["last_modified"]):
            failing.append(cid)

    return len(failing) == 0, failing
