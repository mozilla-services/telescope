"""
The percentage of JEXL filter expressions errors in Normandy should be under the specified
maximum.

The error rate percentage is returned. The min/max timestamps give the datetime range of the
dataset obtained from https://sql.telemetry.mozilla.org/queries/67658/
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_redash


EXPOSED_PARAMETERS = ["max_error_percentage"]

REDASH_QUERY_ID = 67658


async def run(api_key: str, max_error_percentage: float) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    total = sum(row["total"] for row in rows)
    classify_errors = sum(
        row["total"] for row in rows if row["status"] == "content_error"
    )
    error_rate = classify_errors * 100.0 / total
    data = {
        "error_rate": round(error_rate, 2),
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
