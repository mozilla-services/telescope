"""
When changes are approved, the collection metadata change. When the
CDN TTL has elapsed, the content of origin should match the cached content.

The list of failing collections is returned, with the collection metadata
timestamps of the origin and the CDN.
"""

from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcnow

from .utils import KintoClient


EXPOSED_PARAMETERS = ["origin_server", "cdn_server", "ttl_seconds"]


async def run(
    origin_server: str, cdn_server: str, ttl_seconds: int = 3600
) -> CheckResult:
    origin_client = KintoClient(server_url=origin_server)
    entries = await origin_client.get_monitor_changes()

    # Fetch timestamps on source server.
    origin_futures = [
        origin_client.get_changeset(
            entry["bucket"],
            collection=entry["collection"],
            _expected=entry["last_modified"],
        )
        for entry in entries
    ]
    origin_changesets = await run_parallel(*origin_futures)

    # Do exactly the same with CDN.
    cdn_client = KintoClient(server_url=cdn_server)
    cdn_futures = [
        cdn_client.get_changeset(
            entry["bucket"],
            collection=entry["collection"],
            _expected=entry["last_modified"],
        )
        for entry in entries
    ]
    cdn_changesets = await run_parallel(*cdn_futures)

    # Make sure everything matches.
    collections = {}
    for entry, origin_changeset, cdn_changeset in zip(
        entries, origin_changesets, cdn_changesets
    ):
        origin_metadata_timestamp, cdn_metadata_timestamp = (
            origin_changeset["metadata"]["last_modified"],
            cdn_changeset["metadata"]["last_modified"],
        )

        origin_age_seconds = utcnow().timestamp() - (origin_metadata_timestamp / 1000)
        if origin_age_seconds < ttl_seconds:
            # The TTL hasn't elapsed, ignore differences between origin and CDN.
            continue

        if origin_metadata_timestamp != cdn_metadata_timestamp:
            collections["{bucket}/{collection}".format(**entry)] = {
                "source": origin_metadata_timestamp,
                "cdn": cdn_metadata_timestamp,
            }

    return len(collections) == 0, collections
