"""
Measured time it takes for pings to move from edge server to live tables.
This is the sum of latencies of the relevant pubsub topics/subscriptions and dataflow jobs.

Return failure if more than `max_error_rate` of the last `value_count` values
are above `max_threshold`
"""
from collections import defaultdict

from poucave.typings import CheckResult
from poucave.utils import fetch_redash


REDASH_QUERY_ID = 69304

EXPOSED_PARAMETERS = ["max_threshold", "value_count", "max_over_rate"]


async def run(
    api_key: str,
    max_threshold: float = 2000,
    value_count: int = 6,
    max_over_rate: float = 0.5,
) -> CheckResult:
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    latest_timestamps = sorted({row["timestamp"] for row in rows}, reverse=True)[
        :value_count
    ]
    latest_rows = [row for row in rows if row["timestamp"] in latest_timestamps]

    latency_sums = defaultdict(float)
    for row in latest_rows:
        latency_sums[row["timestamp"]] += row["value"]

    over_count = len(
        list(filter(lambda latency: latency > max_threshold, latency_sums.values()))
    )
    over_rate = over_count / value_count

    data_output = {
        "results": latency_sums,
        "over_count": over_count,
    }

    return over_rate <= max_over_rate, data_output
