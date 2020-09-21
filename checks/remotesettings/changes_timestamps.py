"""
Timestamps of entries in monitoring endpoint should match collection timestamp.

For each collection the change `entry` timestamp is returned along with the
`collection` timestamp. The `datetime` is the human-readable version.
"""
import random

from poucave.typings import CheckResult
from poucave.utils import run_parallel, utcfromtimestamp

from .utils import KintoClient


EXPOSED_PARAMETERS = ["server"]


async def run(server: str) -> CheckResult:
    client = KintoClient(server_url=server, bucket="monitor", collection="changes")
    # Make sure we obtain the latest list of changes (bypass webhead microcache)
    random_cache_bust = random.randint(999999000000, 999999999999)
    entries = await client.get_records(_expected=random_cache_bust)
    futures = [
        client.get_records_timestamp(
            bucket=entry["bucket"],
            collection=entry["collection"],
            _expected=entry["last_modified"],
        )
        for entry in entries
    ]
    results = await run_parallel(*futures)

    collections = {}
    for (entry, collection_timestamp) in zip(entries, results):
        entry_timestamp = entry["last_modified"]
        collection_timestamp = int(collection_timestamp)
        dt = utcfromtimestamp(collection_timestamp).isoformat()

        if entry_timestamp != collection_timestamp:
            collections["{bucket}/{collection}".format(**entry)] = {
                "collection": collection_timestamp,
                "entry": entry_timestamp,
                "datetime": dt,
            }

    return len(collections) == 0, collections
