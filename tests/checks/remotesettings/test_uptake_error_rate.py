from datetime import datetime
from unittest import mock

from checks.remotesettings.uptake_error_rate import run


MODULE = "checks.remotesettings.uptake_error_rate"
FAKE_ROWS = [
    {
        "period": datetime.fromisoformat("2026-02-23T21:30:00"),
        "status": "error",
        "row_count": 1,
    },
    {
        "period": datetime.fromisoformat("2026-02-23T21:30:00"),
        "status": "success",
        "row_count": 99,
    },
    {
        "period": datetime.fromisoformat("2026-02-23T21:20:00"),
        "status": "error",
        "row_count": 20,
    },
    {
        "period": datetime.fromisoformat("2026-02-23T21:20:00"),
        "status": "success",
        "row_count": 40,
    },
    {
        "period": datetime.fromisoformat("2026-02-23T21:10:00"),
        "status": "error",
        "row_count": 5,
    },
    {
        "period": datetime.fromisoformat("2026-02-23T21:10:00"),
        "status": "success",
        "row_count": 95,
    },
]


async def test_positive():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_error_percentage=5.1, min_total_events=100)

    assert status is True
    assert data == {
        "min_rate": 1,
        "min_rate_period": "2026-02-23T21:30:00",
        "max_rate": 5,
        "max_rate_period": "2026-02-23T21:10:00",
        "min_timestamp": "2026-02-23T21:10:00",
        "max_timestamp": "2026-02-23T21:30:00",
    }


async def test_negative():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_error_percentage=5, min_total_events=100)

    assert status is False
    assert data == {
        "min_rate": 1,
        "min_rate_period": "2026-02-23T21:30:00",
        "max_rate": 5,
        "max_rate_period": "2026-02-23T21:10:00",
        "min_timestamp": "2026-02-23T21:10:00",
        "max_timestamp": "2026-02-23T21:30:00",
    }


async def test_sql_params():
    with mock.patch("telescope.utils.bigquery.Client") as mocked:
        status, data = await run(
            max_error_percentage=0.1,
            ignore_status=["ignore_status_1", "ignore_status_2"],
            channels=["channel_1, channel_2"],
            sources=["source_1", "source_2"],
        )

    query_str = mocked.return_value.query.call_args_list[0][0][0]
    assert (
        "event_string_value not in ('ignore_status_1','ignore_status_2')" in query_str
    )
    assert "LOWER(normalized_channel) IN ('channel_1, channel_2')" in query_str
    assert (
        "`moz-fx-data-shared-prod`.udf.get_key(event_map_values, \"source\") IN ('source_1','source_2')"
        in query_str
    )


async def test_min_total_events_low():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            max_error_percentage=0.1,
            min_total_events=10,
            channels=["release"],
        )

    assert status is False
    assert data == {
        "min_rate": 1,
        "min_rate_period": "2026-02-23T21:30:00",
        "max_rate": 33.33,
        "max_rate_period": "2026-02-23T21:20:00",
        "min_timestamp": "2026-02-23T21:10:00",
        "max_timestamp": "2026-02-23T21:30:00",
    }


async def test_min_total_events_high():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(
            max_error_percentage=0.1,
            min_total_events=101,
            channels=["release"],
        )

    assert status is True
    assert data == {
        "min_rate": None,
        "min_rate_period": None,
        "max_rate": None,
        "max_rate_period": None,
        "min_timestamp": "2026-02-23T21:10:00",
        "max_timestamp": "2026-02-23T21:30:00",
    }
