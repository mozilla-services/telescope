"""
Age, in seconds, of the latest live main ping measured as the time since the submission_timestamp
of the ping.  This is meant to be used as an approximation of the time it takes for pings to
travel from the edge server to the live tables.

Return failure if more than `max_error_rate` of the last `value_count` values
are above `max_threshold`
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_redash


REDASH_QUERY_ID = 69148

EXPOSED_PARAMETERS = ["max_threshold", "value_count", "max_over_rate"]


async def run(
    api_key: str,
    max_threshold: float = 700,
    value_count: int = 4,
    max_over_rate: float = 0.5,
) -> CheckResult:
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    latest_rows = sorted(rows, key=lambda row: row["current_timestamp"])[-value_count:]

    over_count = len(
        list(filter(lambda row: row["seconds_since_last"] > max_threshold, latest_rows))
    )
    over_rate = over_count / value_count

    data_output = {
        "results": {
            row["current_timestamp"]: row["seconds_since_last"] for row in latest_rows
        },
        "over_count": over_count,
    }

    return over_rate <= max_over_rate, data_output
