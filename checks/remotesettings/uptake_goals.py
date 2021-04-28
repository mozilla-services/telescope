"""
"""
import re
from collections import Counter, defaultdict
from datetime import timedelta
from operator import itemgetter
from typing import Dict, List, Tuple, Union

from poucave.typings import CheckResult
from poucave.utils import (
    csv_quoted,
    fetch_bigquery,
    fetch_json,
    utcfromtimestamp,
    utcnow,
)

from .utils import KintoClient


EXPOSED_PARAMETERS = ["goals"]
DEFAULT_PLOT = ".uptake.7200"


EVENTS_TELEMETRY_QUERY = r"""
WITH event_uptake_telemetry AS (
    SELECT
      client_id,
      normalized_channel,
      UNIX_SECONDS(timestamp) - MOD(UNIX_SECONDS(timestamp), 600) AS period,
    FROM
      `moz-fx-data-shared-prod.telemetry_derived.events_live`
    WHERE
      timestamp > {min_period}
      AND timestamp < {max_period}
      AND event_category = 'uptake.remotecontent.result'
      AND event_object = 'remotesettings'
      AND `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "source") = 'settings-sync'
      AND `moz-fx-data-shared-prod`.udf.get_key(event_map_values, "timestamp") > '"{timestamp}"'
      AND event_string_value = 'success'
      {channel_condition}
),
unique_by_client AS (
    SELECT
        MIN(period) AS period,
        normalized_channel,
    FROM event_uptake_telemetry
    GROUP BY client_id, normalized_channel
)
SELECT
    -- Min/Max timestamps of this period
    PARSE_TIMESTAMP('%s', CAST(period AS STRING)) AS min_timestamp,
    PARSE_TIMESTAMP('%s', CAST(period + 600 AS STRING)) AS max_timestamp,
    normalized_channel,
    COUNT(*) AS total
FROM unique_by_client
GROUP BY period, normalized_channel
ORDER BY period, normalized_channel
"""


async def run(
    server: str,
    total_clients: int,
    goals: Dict[int, int] = {
        7200: 80,
    },
    channels: List[str] = [],
) -> CheckResult:
    goals = {int(k): v for k, v in goals.items()}
    period_seconds = max(goals.keys())

    # Identify the oldest change closest to start of the studied period
    client = KintoClient(server_url=server)
    entries = await client.get_monitor_changes(bust_cache=True)
    changes = sorted(entries, key=itemgetter("last_modified"))
    period_start = utcnow() - timedelta(seconds=period_seconds)
    period_start_timestamp = period_start.timestamp() * 1000

    oldest_change = None
    for change in changes:
        if "-preview" in change["bucket"]:
            continue
        if oldest_change is None or change["last_modified"] < period_start_timestamp:
            oldest_change = change

    channel_condition = (
        f"AND LOWER(normalized_channel) IN ({csv_quoted(channels)})" if channels else ""
    )

    real_period_start = utcfromtimestamp(oldest_change["last_modified"])
    real_period_end = real_period_start + timedelta(seconds=period_seconds + 3600)

    query = EVENTS_TELEMETRY_QUERY.format(
        timestamp=oldest_change["last_modified"],
        channel_condition=channel_condition,
        min_period=f"TIMESTAMP('{real_period_start.isoformat()}')",
        max_period=f"TIMESTAMP('{real_period_end.isoformat()}')",
    )

    rows = await fetch_bigquery(query)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    cumulated = Counter()
    buckets = list(goals.keys())
    for _, max_period, channel, total in rows:
        age_seconds = (max_period - min_timestamp).seconds
        for bucket in buckets:
            if age_seconds < bucket:
                # ESR and Release are sampled at 1%.
                cumulated[bucket] += (
                    total * 100 if channel in ("esr", "release") else total
                )

    result = {
        # In the query, we considered all clients reporting the oldest change and all other recent
        # timestamps.
        # This can lead to uptake rate superior to 100%, but seems to be the only way to handle
        # publications occuring close together.
        goal_age: round(cumulated[goal_age] * 100.0 / total_clients, 1)
        for goal_age in goals.keys()
    }

    success = all(r > g for (r, g) in zip(result.values(), goals.values()))

    return success, {
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
        "change": oldest_change,
        "uptake": result,
    }
