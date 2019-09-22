"""
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
        if metadata["status"] != "work-in-progress":
            continue

        last_edit = metadata["last_edit_date"]
        dt = datetime.fromisoformat(last_edit)
        delta = utcnow() - dt
        age = int(delta.days * 24 + delta.seconds / 3600)

        print(age, max_age)
        if age > max_age:
            cid = "{bucket}/{collection}".format(**resource["destination"])
            too_old[cid] = age

    return len(too_old) == 0, too_old
