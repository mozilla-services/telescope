"""
When changes are approved, the Cloudfront CDN should be invalidated and
the content of origin should match the cache.

The list of failing collections is returned, with the timestamps of origin
and CDN for both the collection metadata and the records.
"""
from telescope.typings import CheckResult
from telescope.utils import run_parallel, utcnow

from .utils import KintoClient


EXPOSED_PARAMETERS = ["server", "cdn", "min_age"]


async def fetch_timestamps(client, bucket, collection):
    metadata = await client.get_collection(bucket=bucket, id=collection)
    collection_timestamp = metadata["data"]["last_modified"]
    records_timestamp = await client.get_records_timestamp(
        bucket=bucket, collection=collection
    )
    return collection_timestamp, records_timestamp


async def run(server: str, cdn: str, min_age: int = 300) -> CheckResult:
    origin_client = KintoClient(server_url=server)
    entries = await origin_client.get_monitor_changes()

    # Fetch timestamps on source server.
    origin_futures = [
        fetch_timestamps(
            origin_client, bucket=entry["bucket"], collection=entry["collection"]
        )
        for entry in entries
    ]
    origin_results = await run_parallel(*origin_futures)

    # Do exactly the same with CDN.
    cdn_client = KintoClient(server_url=cdn)
    cdn_futures = [
        fetch_timestamps(
            cdn_client, bucket=entry["bucket"], collection=entry["collection"]
        )
        for entry in entries
    ]
    cdn_results = await run_parallel(*cdn_futures)

    # Make sure everything matches.
    collections = {}
    for entry, origin_result, cdn_result in zip(entries, origin_results, cdn_results):
        origin_col_ts, origin_records_ts = origin_result
        cdn_col_ts, cdn_records_ts = cdn_result

        age_seconds = utcnow().timestamp() - (origin_col_ts / 1000)
        if (
            age_seconds > min_age
            and origin_col_ts != cdn_col_ts
            or origin_records_ts != cdn_records_ts
        ):
            collections["{bucket}/{collection}".format(**entry)] = {
                "source": {"collection": origin_col_ts, "records": origin_records_ts},
                "cdn": {"collection": cdn_col_ts, "records": cdn_records_ts},
            }

    return len(collections) == 0, collections
