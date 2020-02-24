"""

The min/max timestamps give the datetime range of the dataset obtained from
https://sql.telemetry.mozilla.org/queries/68462/
"""
import json
from datetime import datetime
from typing import Dict, List

from poucave.typings import CheckResult
from poucave.utils import fetch_redash, parse_rfc3339, utcfromtimestamp


REDASH_QUERY_ID = 68462


async def run(api_key: str, channels: List[str] = []) -> CheckResult:
    # Fetch latest results from Redash JSON API.
    rows = await fetch_redash(REDASH_QUERY_ID, api_key)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # Search a change on Remote Settings that was published
    # after this.

    cumulated = {}

    for row in rows:
        # Filter by channel if parameter is specified.
        channel = row["channel"].lower()
        if channels and channel not in channels:
            continue

        total = row["total"] if channel not in ("esr", "release") else row["total"]

        etag = row["received_timestamp"][1:-1]
        if etag not in cumulated:
            cumulated[etag] = {
                "start": row["min_timestamp"],
                "published": utcfromtimestamp(int(etag)).isoformat(),
                "total": 0,
            }
        cumulated[etag]["duration"] = (
            datetime.fromisoformat(row["max_timestamp"])
            - datetime.fromisoformat(cumulated[etag]["start"])
        ).seconds / 60
        for e in cumulated.keys():
            if e <= etag:
                cumulated[etag]["total"] += total

    print(
        json.dumps(
            dict(
                sorted(
                    cumulated.items(), key=lambda item: item[1]["total"], reverse=True
                )[:10]
            ),
            indent=2,
        )
    )

    data = {
        "min_timestamp": min_timestamp,
        "max_timestamp": max_timestamp,
    }

    """
    {
      "min_timestamp": "2019-09-26T10:46:09.079",
      "max_timestamp": "2019-09-27T10:38:55.064",
    }
    """
    return True, data
