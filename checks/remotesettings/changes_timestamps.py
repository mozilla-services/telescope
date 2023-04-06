"""
Timestamps of entries in monitoring endpoint should match collection timestamp.

For each collection the change `entry` timestamp is returned along with the
`collection` timestamp. The `datetime` is the human-readable version.
"""
from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcfromtimestamp

from .utils import KintoClient


EXPOSED_PARAMETERS = ["server"]


async def run(server: str) -> CheckResult:
    client = KintoClient(server_url=server)

    # Make sure we obtain the latest list of changes (bypass webhead microcache)
    entries = await client.get_monitor_changes(bust_cache=True)
    futures = [
        client.get_changeset(
            bucket=entry["bucket"],
            collection=entry["collection"],
            _expected=entry["last_modified"],
            _limit=1,
        )
        for entry in entries
    ]
    results = await run_parallel(*futures)

    collections = {}
    for entry, changeset in zip(entries, results):
        entry_timestamp = entry["last_modified"]
        collection_timestamp = changeset["timestamp"]
        dt = utcfromtimestamp(collection_timestamp).isoformat()

        if entry_timestamp != collection_timestamp:
            collections["{bucket}/{collection}".format(**entry)] = {
                "collection": collection_timestamp,
                "entry": entry_timestamp,
                "datetime": dt,
            }

    return len(collections) == 0, collections
