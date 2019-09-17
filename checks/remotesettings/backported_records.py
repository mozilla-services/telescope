"""
The collection timestamp of the destination, where the source records are backported,
shouldn't lag by more than some number of seconds. The default max lag is 5 minutes, which
is the run frequency of the backport lambda.

The source and destination collection timestamps are returned.
"""
from typing import Dict

from poucave.typings import CheckResult

from .utils import KintoClient as Client


EXPOSED_PARAMETERS = ["max_lag_seconds"]


async def run(
    server: str, backports: Dict[str, str], max_lag_seconds: int = 5 * 60
) -> CheckResult:
    client = Client(server_url=server)

    errors = []
    for source, dest in backports.items():
        source_bid, source_cid = source.split("/")
        dest_bid, dest_cid = dest.split("/")

        source_timestamp = await client.get_records_timestamp(
            bucket=source_bid, collection=source_cid
        )
        dest_timestamp = await client.get_records_timestamp(
            bucket=dest_bid, collection=dest_cid
        )

        diff_millisecond = abs(int(source_timestamp) - int(dest_timestamp))
        if (diff_millisecond / 1000) > max_lag_seconds:
            errors.append(
                {
                    f"{source_bid}/{source_cid}": source_timestamp,
                    f"{dest_bid}/{dest_cid}": dest_timestamp,
                }
            )

    return len(errors) == 0, errors
