"""
Compare the content of two Remote Settings servers.

The margin seconds will allow ignoring recent changes that may not
have yet propagated to the target server.

The list of outdated content is returned, with the related timestamps.
"""

from telescope.typings import CheckResult
from telescope.utils import ClientSession, run_parallel, utcnow

from .utils import KintoClient


EXPOSED_PARAMETERS = ["source_server", "target_server", "margin_seconds"]


async def run(
    source_server: str, target_server: str, margin_seconds: int = 3600
) -> CheckResult:
    async with ClientSession() as source_session:
        async with ClientSession() as target_session:
            source_client = KintoClient(
                server_url=source_server, session=source_session
            )
            target_client = KintoClient(
                server_url=target_server, session=target_session
            )

            source_entries = await source_client.get_monitor_changes()
            target_entries = await target_client.get_monitor_changes()

            # Do a pre-check to make sure both servers monitor the same collections.
            if source_entries[0]["last_modified"] != target_entries[0]["last_modified"]:
                return (
                    False,
                    {
                        "monitor/changes": {
                            "source": source_entries[0]["last_modified"],
                            "target": target_entries[0]["last_modified"],
                        },
                    },
                )

            # At this point we know both servers monitor the same collections.
            # Fetch timestamps on source.
            source_futures = [
                source_client.get_changeset(
                    bucket=entry["bucket"],
                    collection=entry["collection"],
                    params={"_expected": entry["last_modified"]},
                )
                for entry in source_entries
            ]
            source_changesets = await run_parallel(*source_futures)
            target_futures = [
                target_client.get_changeset(
                    bucket=entry["bucket"],
                    collection=entry["collection"],
                    params={"_expected": entry["last_modified"]},
                )
                for entry in source_entries  # Same as target_entries.
            ]
            target_changesets = await run_parallel(*target_futures)

    # Make sure everything matches.
    outdated = {}
    for entry, origin_changeset, target_changeset in zip(
        source_entries, source_changesets, target_changesets
    ):
        source_metadata_timestamp, target_metadata_timestamp = (
            origin_changeset["timestamp"],
            target_changeset["timestamp"],
        )

        source_age_seconds = utcnow().timestamp() - (source_metadata_timestamp / 1000)
        if source_age_seconds < margin_seconds:
            # The TTL hasn't elapsed, ignore differences between source and target.
            continue

        if source_metadata_timestamp != target_metadata_timestamp:
            outdated["{bucket}/{collection}".format(**entry)] = {
                "source": source_metadata_timestamp,
                "target": target_metadata_timestamp,
            }

    # Sort entries by source timestamp descending.
    outdated = dict(
        sorted(
            outdated.items(),
            key=lambda entry: entry[1]["source"],
            reverse=True,
        )
    )

    return len(outdated) == 0, outdated
