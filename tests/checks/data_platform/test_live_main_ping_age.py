from checks.data_platform.live_main_ping_age import run
from tests.utils import patch_async


MODULE = "checks.data_platform.live_main_ping_age"

INPUT_ROWS = [
    {
        "current_timestamp": "2020-03-19T22:00:00",
        "latest_timestamp": "2020-03-19T21:57:00",
        "seconds_since_last": 180,
    },
    {
        "current_timestamp": "2020-03-19T21:50:00",
        "latest_timestamp": "2020-03-19T21:44:00",
        "seconds_since_last": 360,
    },
    {
        "current_timestamp": "2020-03-19T21:40:00",
        "latest_timestamp": "2020-03-19T21:38:00",
        "seconds_since_last": 120,
    },
    {
        "current_timestamp": "2020-03-19T21:30:00",
        "latest_timestamp": "2020-03-19T21:29:00",
        "seconds_since_last": 60,
    },
    {
        "current_timestamp": "2020-03-19T21:20:00",
        "latest_timestamp": "2020-03-19T21:18:00",
        "seconds_since_last": 120,
    },
]


async def test_success():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=120, value_count=4, max_over_rate=0.5
        )

        assert success
        assert data["results"] == {
            "2020-03-19T22:00:00": 180,
            "2020-03-19T21:50:00": 360,
            "2020-03-19T21:40:00": 120,
            "2020-03-19T21:30:00": 60,
        }
        assert data["over_count"] == 2


async def test_max_threshold():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=100, value_count=4, max_over_rate=0.5
        )

        assert success is False
        assert len(data["results"]) == 4


async def test_value_count():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=120, value_count=2, max_over_rate=0.5
        )

        assert success is False
        assert len(data["results"]) == 2


async def test_max_over_rate():
    with patch_async(f"{MODULE}.fetch_redash", return_value=INPUT_ROWS):
        success, data = await run(
            api_key="", max_threshold=120, value_count=2, max_over_rate=0.499
        )

        assert success is False
        assert len(data["results"]) == 2
