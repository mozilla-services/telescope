"""
Source, preview and/or final collections should have consistent records and status.

If this check fails, this is very likely to be a software issue. Some insights about
the consistencies are returned for each concerned collection.
"""

import logging

from telescope.typings import CheckResult
from telescope.utils import run_parallel

from .utils import KintoClient, compare_collections, fetch_signed_resources, human_diff


EXPOSED_PARAMETERS = ["server"]


logger = logging.getLogger(__name__)


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

    message = f"status: '{status}'. "

    # Collection status is reset on any modification, so if status is ``to-review``,
    # then records in the source should be exactly the same as the records in the preview
    if status == "to-review":
        if "preview" not in resource:
            return "{bucket}/{collection} should not have 'to-review' status".format(
                **resource["source"]
            )

        source_records = await client.get_records(**source)
        preview_records = await client.get_records(**resource["preview"])
        diff = compare_collections(source_records, preview_records)
        if diff:
            return message + human_diff("source", "preview", *diff)

    # And if status is ``signed``, then records in the source and preview should
    # all be the same as those in the destination.
    elif status == "signed" or status is None:
        source_records = await client.get_records(**source)
        dest_records = await client.get_records(**resource["destination"])
        if "preview" in resource:
            # If preview is enabled, then compare source/preview and preview/dest
            preview_records = await client.get_records(**resource["preview"])

            diff_preview = compare_collections(preview_records, dest_records)
            if diff_preview:
                return message + human_diff("preview", "destination", *diff_preview)

            diff_source = compare_collections(source_records, preview_records)
            if diff_source:
                return message + human_diff("source", "preview", *diff_source)
        else:
            # Otherwise, just compare source/dest
            diff_source = compare_collections(source_records, dest_records)
            if diff_source:
                return message + human_diff("source", "destination", *diff_source)

    elif status == "work-in-progress":
        # And if status is ``work-in-progress``, we can't really check anything.
        # Source can differ from preview, and preview can differ from destination
        # if a review request was previously rejected.
        pass

    else:
        # Other statuses should never be encountered.
        return f"Unexpected status '{status}'"

    return None


async def run(server: str, auth: str) -> CheckResult:
    resources = await fetch_signed_resources(server, auth)

    futures = [has_inconsistencies(server, auth, resource) for resource in resources]
    results = await run_parallel(*futures)

    inconsistent = {
        "{bucket}/{collection}".format(**resource["destination"]): error_info.strip()
        for resource, error_info in zip(resources, results)
        if error_info
    }

    return len(inconsistent) == 0, inconsistent
