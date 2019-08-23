"""
Timestamps of entries in monitoring endpoint should match collection timestamp.
"""
import asyncio
from datetime import datetime

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
    all_good = True
    datetimes = []
    for (entry, timestamp) in zip(entries, results):
        collection_timestamp = timestamp
        entry_timestamp = str(entry["last_modified"])
        all_good = all_good and collection_timestamp == entry_timestamp
        dt = datetime.utcfromtimestamp(int(timestamp) / 1000).isoformat()
        cid = "{bucket}/{collection}".format(**entry)
        datetimes.append(
            {
                "id": cid,
                "collection": collection_timestamp,
                "entry": entry_timestamp,
                "datetime": dt,
            }
        )

    return all_good, datetimes
