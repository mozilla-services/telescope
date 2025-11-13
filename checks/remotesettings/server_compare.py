"""
Compare the content of two Remote Settings servers.

The margin seconds will allow ignoring recent changes that may not
have yet propagated to the target server.

The list of outdated content is returned, with the related timestamps.
"""

from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcnow

from .utils import KintoClient


EXPOSED_PARAMETERS = ["source_server", "target_server", "margin_seconds"]


async def run(
    source_server: str, target_server: str, margin_seconds: int = 3600
) -> CheckResult:
    origin_client = KintoClient(server_url=source_server)
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
    cdn_client = KintoClient(server_url=target_server)
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
    outdated = {}
    for entry, origin_changeset, cdn_changeset in zip(
        entries, origin_changesets, cdn_changesets
    ):
        origin_metadata_timestamp, cdn_metadata_timestamp = (
            origin_changeset["metadata"]["last_modified"],
            cdn_changeset["metadata"]["last_modified"],
        )

        origin_age_seconds = utcnow().timestamp() - (origin_metadata_timestamp / 1000)
        if origin_age_seconds < margin_seconds:
            # The TTL hasn't elapsed, ignore differences between origin and CDN.
            continue

        if origin_metadata_timestamp != cdn_metadata_timestamp:
            outdated["{bucket}/{collection}".format(**entry)] = {
                "source": origin_metadata_timestamp,
                "cdn": cdn_metadata_timestamp,
            }

    # Sort entries by timestamp descending.
    outdated = dict(
        sorted(
            outdated.items(),
            key=lambda entry: entry[1]["source"],
            reverse=True,
        )
    )

    return len(outdated) == 0, outdated
