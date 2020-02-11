"""
The percentage of JEXL filter expressions errors in Normandy should be under the specified
maximum.

The error rate percentage is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/67658/
"""
from collections import defaultdict
from typing import Dict, Tuple

from poucave.typings import CheckResult
from poucave.utils import fetch_redash


EXPOSED_PARAMETERS = ["max_error_percentage"]

REDASH_QUERY_ID = 67658


async def run(api_key: str, max_error_percentage: float) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # The Redash query returns statuses by periods (eg. 10min).
    # First, agregate totals by period.
    periods: Dict[Tuple[str, str], Dict] = {}
    for row in rows:
        period: Tuple[str, str] = (row["min_timestamp"], row["max_timestamp"])
        if period not in periods:
            periods[period] = defaultdict(int)
        status = row["status"]
        periods[period][status] += row["total"]

    # Then, keep the period with highest error rate.
    max_error_rate = 0.0
    for period, all_statuses in periods.items():
        total = sum(all_statuses.values())
        classify_errors = all_statuses.get("content_error", 0)
        error_rate = classify_errors * 100.0 / total
        if max_error_rate < error_rate:
            max_error_rate = error_rate
        if max_error_rate >= max_error_percentage:
            min_timestamp, max_timestamp = period

    data = {
        "error_rate": round(max_error_rate, 2),
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }
    """
    {
      "error_rate": 2.11,
      "min_timestamp": "2019-09-19T03:47:42.773",
      "max_timestamp": "2019-09-19T09:43:26.083"
    }
    """
    return error_rate <= max_error_percentage, data
