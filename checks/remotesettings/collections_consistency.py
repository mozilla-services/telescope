"""
Preview and final collections have consistent records and status.

Some insights about the consistencies are returned for each concerned collection.
"""
import logging

from poucave.typings import CheckResult
from poucave.utils import run_parallel

from .utils import KintoClient, fetch_signed_resources


logger = logging.getLogger(__name__)


def records_equal(a, b):
    """Compare records, ignoring timestamps."""
    ignored_fields = ("last_modified", "schema")
    ra = {k: v for k, v in a.items() if k not in ignored_fields}
    rb = {k: v for k, v in b.items() if k not in ignored_fields}
    return ra == rb


def compare_collections(a, b):
    """Compare two lists of records. Returns empty list if equal."""
    b_by_id = {r["id"]: r for r in b}
    diff = []
    for ra in a:
        rb = b_by_id.pop(ra["id"], None)
        if rb is None:
            diff.append(ra)
        elif not records_equal(ra, rb):
            diff.append(ra)
    diff.extend(b_by_id.values())
    return diff


async def has_inconsistencies(server_url, auth, resource):
    source = resource["source"]

    client = KintoClient(server_url=server_url, auth=auth)

    collection = await client.get_collection(
        bucket=source["bucket"], id=source["collection"]
    )
    source_metadata = collection["data"]

    try:
        status = source_metadata["status"]
    except KeyError:
        return '"status" attribute missing'

    # Collection status is reset on any modification, so if status is ``to-review``,
    # then records in the source should be exactly the same as the records in the preview
    if status == "to-review":
        source_records = await client.get_records(**source)
        preview_records = await client.get_records(**resource["preview"])
        diff = compare_collections(source_records, preview_records)
        if diff:
            return "to-review: source and preview differ"

    # And if status is ``signed``, then records in the source and preview should
    # all be the same as those in the destination.
    elif status == "signed" or status is None:
        source_records = await client.get_records(**source)
        dest_records = await client.get_records(**resource["destination"])
        if "preview" in resource:
            # If preview is enabled, then compare source/preview and preview/dest
            preview_records = await client.get_records(**resource["preview"])
            diff_source = compare_collections(source_records, preview_records)
            diff_preview = compare_collections(preview_records, dest_records)
        else:
            # Otherwise, just compare source/dest
            diff_source = compare_collections(source_records, dest_records)
            diff_preview = []
        # If difference detected, report it!
        if diff_source or diff_preview:
            return "signed: source, preview, and/or destination differ"

    elif status == "work-in-progress":
        # And if status is ``work-in-progress``, we can't really check anything.
        # Source can differ from preview, and preview can differ from destination
        # if a review request was previously rejected.
        pass

    else:
        # Other statuses should never be encountered.
        return f"unexpected status '{status}'"

    return None


async def run(server: str, auth: str) -> CheckResult:
    resources = await fetch_signed_resources(server, auth)

    futures = [has_inconsistencies(server, auth, resource) for resource in resources]
    results = await run_parallel(*futures)

    inconsistent = {
        "{bucket}/{collection}".format(**resource["destination"]): error_info
        for resource, error_info in zip(resources, results)
        if error_info
    }

    return len(inconsistent) == 0, inconsistent
