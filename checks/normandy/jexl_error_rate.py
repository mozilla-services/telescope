"""
The percentage of JEXL filter expressions errors in Normandy should be under the specified
maximum.

The error rate percentage is returned. The min/max timestamps give the datetime range of the
obtained dataset.
"""
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from poucave.typings import CheckResult, Datetime

from .uptake_error_rate import fetch_normandy_uptake


EXPOSED_PARAMETERS = ["max_error_percentage"]
DEFAULT_PLOT = ".error_rate"


async def run(
    max_error_percentage: float, channels: List[str] = [], period_hours: int = 6
) -> CheckResult:
    rows = await fetch_normandy_uptake(channels=channels, period_hours=period_hours)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # The query returns statuses by periods (eg. 10min).
    # First, agregate totals by period and status.
    periods: Dict[Tuple[Datetime, Datetime], Counter] = defaultdict(Counter)
    for row in rows:
        period: Tuple[Datetime, Datetime] = (row["min_timestamp"], row["max_timestamp"])
        status = row["status"]
        periods[period][status] += row["total"]

    # Then, keep the period with highest error rate.
    max_error_rate = 0.0
    for period, all_statuses in periods.items():
        total = sum(all_statuses.values())
        classify_errors = all_statuses.get("content_error", 0)
        error_rate = classify_errors * 100.0 / total
        max_error_rate = max(max_error_rate, error_rate)
        # If this period is over threshold, show it in check result.
        if max_error_rate > max_error_percentage:
            min_timestamp, max_timestamp = period

    data = {
        "error_rate": round(max_error_rate, 2),
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
    }
    """
    {
      "error_rate": 2.11,
      "min_timestamp": "2019-09-19T03:47:42.773",
      "max_timestamp": "2019-09-19T09:43:26.083"
    }
    """
    return error_rate <= max_error_percentage, data
