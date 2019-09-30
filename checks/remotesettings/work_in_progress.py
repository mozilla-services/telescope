"""
Collections should not have very old pending changes.

The list of collections with pending changes is returned, with the age in days
and the list of responsible editors.
"""
import logging
from datetime import datetime

from poucave.typings import CheckResult
from poucave.utils import run_parallel, utcnow

from .utils import KintoClient, fetch_signed_resources

logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = ["max_age"]


async def run(server: str, auth: str, max_age: int) -> CheckResult:
    resources = await fetch_signed_resources(server, auth)

    client = KintoClient(server_url=server, auth=auth)

    futures = [
        client.get_collection(
            bucket=resource["source"]["bucket"], id=resource["source"]["collection"]
        )
        for resource in resources
    ]
    results = await run_parallel(*futures)

    too_old = {}
    for resource, resp in zip(resources, results):
        metadata = resp["data"]
        # For this check, since we want to detect pending changes,
        # we also consider work-in-progress a pending request review.
        if metadata["status"] not in ("work-in-progress", "to-review"):
            continue

        try:
            last_edit = metadata["last_edit_date"]
            dt = datetime.fromisoformat(last_edit)
            age = (utcnow() - dt).days
        except KeyError:
            # Never edited.
            age = float("inf")

        if age > max_age:
            # Fetch list of editors, if necessary to contact them.
            group = await client.get_group(
                bucket=resource["source"]["bucket"],
                id=resource["source"]["collection"] + "-editors",
            )
            editors = group["data"]["members"]

            cid = "{bucket}/{collection}".format(**resource["destination"])
            too_old[cid] = {
                "age": age,
                "status": metadata["status"],
                "editors": editors,
            }

    """
    {
      "security-state/cert-revocations": {
        "age": 82,
        "status": "to-review",
        "editors": [
          "ldap:user1@mozilla.com",
          "ldap:user2@mozilla.com",
          "account:crlite_publisher"
        ]
      }
    }
    """
    return len(too_old) == 0, too_old
