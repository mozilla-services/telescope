"""
When changes are approved, the Cloudfront CDN should be invalidated and
the content of source should match the cache.

The list of failing collections is returned, with the timestamps of source
and CDN for both the collection metadata and the records.
"""
from poucave.typings import CheckResult
from poucave.utils import run_parallel

from .utils import KintoClient


async def fetch_timestamps(client, bucket, collection):
    metadata = await client.get_collection(bucket=bucket, id=collection)
    collection_timestamp = metadata["data"]["last_modified"]
    records_timestamp = await client.get_records_timestamp(
        bucket=bucket, collection=collection
    )
    return collection_timestamp, records_timestamp


async def run(server: str, cdn: str) -> CheckResult:
    source_client = KintoClient(server_url=server)
    entries = await source_client.get_records(bucket="monitor", collection="changes")

    # Fetch timestamps on source server.
    source_futures = [
        fetch_timestamps(
            source_client, bucket=entry["bucket"], collection=entry["collection"]
        )
        for entry in entries
    ]
    source_results = await run_parallel(*source_futures)

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
    for entry, source_result, cdn_result in zip(entries, source_results, cdn_results):
        source_col_ts, source_records_ts = source_result
        cdn_col_ts, cdn_records_ts = cdn_result

        if source_col_ts != cdn_col_ts or source_records_ts != cdn_records_ts:
            collections["{bucket}/{collection}".format(**entry)] = {
                "source": {"collection": source_col_ts, "records": source_records_ts},
                "cdn": {"collection": cdn_col_ts, "records": cdn_records_ts},
            }

    return len(collections) == 0, collections
