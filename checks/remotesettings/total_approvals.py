"""
Dummy-check to obtain information about the total number of approvals in the last days.

For each day, the total number of approvals is returned, with details per collection.
"""

from collections import Counter
from datetime import datetime, timezone

from telescope.typings import CheckResult
from telescope.utils import ClientSession, run_parallel, utcfromtimestamp, utcnow

from .utils import KintoClient, fetch_signed_resources


ONE_DAY_MSEC = 24 * 3600 * 1000

DEFAULT_PLOT = "0.totals"


async def get_approvals(client, bucket, min_timestamp, max_timestamp):
    changes = await client.get_history(
        bucket=bucket,
        params={
            "resource_name": "collection",
            "action": "update",
            "target.data.status": "to-sign",
            "_since": min_timestamp,
            "_before": max_timestamp,
        },
    )
    by_collection = Counter(change["collection_id"] for change in changes)
    return by_collection


async def run(server: str, auth: str, period_days: int = 3) -> CheckResult:
    # Compute the list of timestamps couples of the past full days,
    # starting from today at midnight (last night).
    today_00h00_timestamp = (
        datetime.combine(utcnow(), datetime.min.time(), tzinfo=timezone.utc).timestamp()
        * 1000
    )
    days_min_max = []
    for iday in range(period_days):
        iday_00h00_timestamp = today_00h00_timestamp - (iday + 1) * ONE_DAY_MSEC
        iday_23h59_timestamp = today_00h00_timestamp - iday * ONE_DAY_MSEC
        days_min_max.append((iday_00h00_timestamp, iday_23h59_timestamp))

    async with ClientSession() as session:
        client = KintoClient(server_url=server, auth=auth, session=session)

        # Get the list of bucket names used as source (eg. main-workspace, ...)
        resources = await fetch_signed_resources(client=client)
        source_buckets = {r["source"]["bucket"] for r in resources}

        for min_day, max_day in days_min_max:
            # Approvals for each bucket on this day.
            futures = [
                get_approvals(client, bucket, min_day, max_day)
                for bucket in source_buckets
            ]
            results = await run_parallel(*futures)

    # Prepare an array with information about each of the last days.
    days = []
    approvals_per_bucket = zip(source_buckets, days_min_max, results)
    # Sum the totals and show counters per collection on each day
    for bucket, (min_day, max_day), counter in approvals_per_bucket:
        day = {
            "date": utcfromtimestamp(min_day).date().isoformat(),
            "totals": 0,
        }
        for cid, total in counter.items():
            day[f"{bucket}/{cid}"] = total
            day["totals"] += total
    days.append(day)

    # [
    #   {
    #     "date": "2022-05-17",
    #     "totals": 112,
    #     "main-workspace/nimbus-preview": 98,
    #     "main-workspace/normandy-recipes-capabilities": 2,
    #     "main-workspace/nimbus-mobile-experiments": 5,
    #     "main-workspace/nimbus-desktop-experiments": 2,
    #     "security-state-staging/cert-revocations": 4,
    #     "security-state-staging/intermediates": 1
    #   },
    #   ...
    return True, days
