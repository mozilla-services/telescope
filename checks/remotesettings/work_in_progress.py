"""
Collections should not have very old pending changes.

The list of collections with pending changes is returned, with the age in days
and the list of responsible editors.
"""

import logging
import sys
from datetime import datetime

from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcnow

from .utils import KintoClient, compare_collections, fetch_signed_resources


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = ["max_age"]


def last_edit_age(metadata):
    try:
        last_edit = metadata["last_edit_date"]
        dt = datetime.fromisoformat(last_edit)
        return (utcnow() - dt).days
    except KeyError:
        # Never edited.
        return sys.maxsize


async def run(server: str, auth: str, max_age: int) -> CheckResult:
    resources = await fetch_signed_resources(server, auth)

    client = KintoClient(server_url=server, auth=auth)

    futures = [
        client.get_collection(
            bucket=resource["source"]["bucket"], id=resource["source"]["collection"]
        )
        for resource in resources
    ]
    results_metadata = await run_parallel(*futures)

    too_old = {}
    for resource, collection_metadata in zip(resources, results_metadata):
        metadata = collection_metadata["data"]

        # For this check, since we want to detect pending changes,
        # we also consider work-in-progress a pending request review.
        if metadata["status"] not in ("work-in-progress", "to-review"):
            continue

        # Ignore collections changed recently.
        if last_edit_age(metadata) <= max_age:
            continue

        # Ignore collections in WIP with no pending changes.
        if metadata["status"] == "work-in-progress":
            # These collections are worth introspecting.
            source_records = await client.get_records(**resource["source"])
            destination_records = await client.get_records(**resource["destination"])
            if not compare_collections(source_records, destination_records):
                continue

        # Fetch list of editors, if necessary to contact them.
        group = await client.get_group(
            bucket=resource["source"]["bucket"],
            id=resource["source"]["collection"] + "-editors",
        )
        editors = group["data"]["members"]

        cid = "{bucket}/{collection}".format(**resource["destination"])

        last_edit_by = metadata.get("last_edit_by", "N/A")
        too_old[cid] = {
            "age": last_edit_age(metadata),
            "status": metadata["status"],
            "last_edit_by": last_edit_by,
            "editors": editors,
        }

    """
    {
      "security-state/cert-revocations": {
        "age": 82,
        "status": "to-review",
        "last_edit_by": "ldap:user1@mozilla.com",
        "editors": [
          "ldap:user1@mozilla.com",
          "ldap:user2@mozilla.com",
          "account:crlite_publisher"
        ]
      }
    }
    """
    data = dict(sorted(too_old.items(), key=lambda item: item[1]["age"], reverse=True))
    return len(data) == 0, data
