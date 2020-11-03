"""
The CRLite filter is automatically regenerated multiple times a day, so the
published filter should always be recent. This check makes sure the filter
isn't too old, and returns the current age of the filter in hours.
"""
from time import time

from poucave.typings import CheckResult

from .utils import KintoClient


EXPOSED_PARAMETERS = ["server", "bucket", "collection", "max_filter_age_hours"]
DEFAULT_PLOT = "."


async def run(
    server: str,
    bucket: str = "security-state",
    collection: str = "cert-revocations",
    max_filter_age_hours: int = 24,
) -> CheckResult:
    client = KintoClient(server_url=server)
    records = await client.get_records(bucket=bucket, collection=collection)
    filter_timestamp = max(r.get("effectiveTimestamp", 0) for r in records)
    filter_age_hours = (time() - filter_timestamp // 1000) / 3600
    return filter_age_hours <= max_filter_age_hours, filter_age_hours
