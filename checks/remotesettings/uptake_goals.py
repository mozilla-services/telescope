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
    goals: Dict[int, int] = {
        7200: 80,
    },
    channels: List[str] = [],
) -> CheckResult:
    goals = {int(k): v for k, v in goals.items()}
    period_seconds = max(goals.keys()) * 2  # Grow the studied period.

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

    real_period_start = utcfromtimestamp(oldest_change["last_modified"])
    real_period_end = real_period_start + timedelta(seconds=period_seconds)

    channel_condition = (
        f"AND LOWER(normalized_channel) IN ({csv_quoted(channels)})" if channels else ""
    )

    query = EVENTS_TELEMETRY_QUERY.format(
        timestamp=oldest_change["last_modified"],
        channel_condition=channel_condition,
        min_period=f"TIMESTAMP('{real_period_start.isoformat()}')",
        max_period=f"TIMESTAMP('{real_period_end.isoformat()}')",
    )

    rows = await fetch_bigquery(query)

    min_timestamp = min(r["min_timestamp"] for r in rows)
    max_timestamp = max(r["max_timestamp"] for r in rows)

    # We need to know the daily active users for the studied period.
    # We assume that the trafic is globally the same from one week to another.
    # Let's look at Daily Active Users a week before.
    week_before_start = real_period_start - timedelta(days=7)
    week_before_end = real_period_end - timedelta(days=7)
    query = """
    SELECT
      submission_date,
      approx_count_distinct(client_id) AS cohort_dau
    FROM
      `moz-fx-data-shared-prod`.telemetry.clients_daily
    WHERE
      submission_date >= '{start_day}'
      AND submission_date <= '{end_day}'
      {channel_condition}
    GROUP BY 1
    ORDER BY 1
    """.format(
        start_day=week_before_start.date().isoformat(),
        end_day=week_before_end.date().isoformat(),
        channel_condition=channel_condition,
    )
    dau_rows = await fetch_bigquery(query)
    dau_by_day = {r["submission_date"] + timedelta(days=7): r["cohort_dau"] for r in dau_rows}
    active_clients_by_goal = {}
    for goal in goals:
        goal_date = (min_timestamp + timedelta(seconds=goal)).date()
        active_clients_by_goal[goal] = dau_by_day[goal_date]

    # We will now count the number of clients reported for each goal.
    # cumulated = {
    #   600: 13000,
    #   3600: 75000,
    #   7200: 130000,
    # }
    cumulated = Counter()
    goal_buckets = list(goals.keys())
    for _, max_period, channel, total in rows:
        # ESR and Release are sampled at 1%.
        total = total * 100 if channel in ("esr", "release") else total
        age_seconds = (max_period - min_timestamp).seconds
        for goal_bucket in goal_buckets:
            if age_seconds < goal_bucket:
                cumulated[goal_bucket] += total

    result = {
        # In the query, we considered all clients reporting the oldest change and all other recent
        # timestamps.
        # This can lead to uptake rate superior to 100%, but seems to be the only way to handle
        # publications occuring close together.
        goal_age: round(
            cumulated[goal_age] * 100.0 / active_clients_by_goal[goal_age], 1
        )
        for goal_age in goals.keys()
    }

    success = all(r > g for (r, g) in zip(result.values(), goals.values()))

    return success, {
        "min_timestamp": min_timestamp.isoformat(),
        "max_timestamp": max_timestamp.isoformat(),
        "change": oldest_change,
        "uptake": result,
    }
