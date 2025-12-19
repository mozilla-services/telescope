"""
Compare the content of two Remote Settings servers.

The margin seconds will allow ignoring recent changes that may not
have yet propagated to the target server.

The list of outdated content is returned, with the related timestamps.
"""

from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcfromtimestamp, utcnow

from .utils import KintoClient


EXPOSED_PARAMETERS = ["source_server", "target_server", "margin_seconds"]


async def run(
    source_server: str, target_server: str, margin_seconds: int = 3600
) -> CheckResult:
    source_client = KintoClient(server_url=source_server)
    source_entries = await source_client.get_monitor_changes()

    target_client = KintoClient(server_url=target_server)
    target_entries = await target_client.get_monitor_changes()

    # Do a pre-check to make sure both servers monitor the same collections.
    age_latest_change_seconds = utcnow().timestamp() - (
        source_entries[0]["last_modified"] / 1000
    )
    if source_entries[0]["last_modified"] != target_entries[0]["last_modified"] and (
        age_latest_change_seconds > margin_seconds
    ):
        return (
            False,
            {
                "monitor/changes": {
                    "source": {
                        "timestamp": source_entries[0]["last_modified"],
                        "datetime": utcfromtimestamp(
                            source_entries[0]["last_modified"]
                        ).isoformat(),
                    },
                    "target": {
                        "timestamp": target_entries[0]["last_modified"],
                        "datetime": utcfromtimestamp(
                            target_entries[0]["last_modified"]
                        ).isoformat(),
                    },
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
                "source": {
                    "timestamp": source_metadata_timestamp,
                    "datetime": utcfromtimestamp(source_metadata_timestamp).isoformat(),
                },
                "target": {
                    "timestamp": target_metadata_timestamp,
                    "datetime": utcfromtimestamp(target_metadata_timestamp).isoformat(),
                },
            }

    # Sort entries by source timestamp descending.
    outdated = dict(
        sorted(
            outdated.items(),
            key=lambda entry: entry[1]["source"]["timestamp"],
            reverse=True,
        )
    )

    return len(outdated) == 0, outdated
