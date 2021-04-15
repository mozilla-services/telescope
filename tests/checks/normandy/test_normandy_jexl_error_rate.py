from datetime import datetime

from checks.normandy.jexl_error_rate import run
from tests.utils import patch_async


MODULE = "checks.normandy.jexl_error_rate"

FAKE_ROWS = [
    {
        "status": "success",
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 1800,
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
    {
        "status": "success",
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 9000,
        "min_timestamp": datetime.fromisoformat("2019-09-16T03:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T05:24:58.741"),
    },
    {
        "status": "content_error",
        "source": "normandy/recipe/123",
        "channel": "release",
        "total": 1000,
        "min_timestamp": datetime.fromisoformat("2019-09-16T03:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T05:24:58.741"),
    },
    {
        "status": "success",
        "source": "normandy/recipe/456",
        "channel": "release",
        "total": 900,
        "min_timestamp": datetime.fromisoformat("2019-09-16T01:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T07:24:58.741"),
    },
    {
        "status": "content_error",
        "source": "normandy/recipe/456",
        "channel": "release",
        "total": 100,
        "min_timestamp": datetime.fromisoformat("2019-09-16T01:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T07:24:58.741"),
    },
    {
        "status": "success",
        "source": "normandy/recipe/531",
        "channel": "beta",
        "total": 100,
        "min_timestamp": datetime.fromisoformat("2019-09-16T01:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T07:24:58.741"),
    },
    {
        "status": "content_error",
        "source": "normandy/recipe/531",
        "channel": "beta",
        "total": 100,
        "min_timestamp": datetime.fromisoformat("2019-09-16T01:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T07:24:58.741"),
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_error_percentage=100.0, channels=["release"])

    assert status is True
    assert data == {
        "error_rate": 10.0,
        "min_timestamp": "2019-09-16T01:36:12.348000",
        "max_timestamp": "2019-09-16T07:24:58.741000",
    }


async def test_filter_by_channel():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_error_percentage=100.0, channels=["beta"])

    assert status is True
    assert data == {
        "error_rate": 50.0,
        "min_timestamp": "2019-09-16T01:36:12.348000",
        "max_timestamp": "2019-09-16T07:24:58.741000",
    }


async def test_negative():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_error_percentage=1.0, channels=["release"])

    assert status is False
    assert data == {
        "error_rate": 10.0,
        "min_timestamp": "2019-09-16T01:36:12.348000",
        "max_timestamp": "2019-09-16T07:24:58.741000",
    }
