from datetime import datetime
from unittest import mock

from checks.remotesettings.uptake_max_age import run


MODULE = "checks.remotesettings.uptake_max_age"

FAKE_ROWS = [
    {
        "channel": "release",
        "age_percentiles": [i**2 for i in range(100)],
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
]


async def test_positive():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_percentiles={"10": 101, "50": 2501})

    assert status is True
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348000",
        "max_timestamp": "2019-09-16T06:24:58.741000",
        "percentiles": {
            "10": {"value": 100, "max": 101},
            "50": {"value": 2500, "max": 2501},
        },
    }


async def test_positive_no_data():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=[]):
        status, data = await run(max_percentiles={"50": 42}, channels=["aurora"])

    assert status is True
    assert data["percentiles"] == "No broadcast data during this period."


async def test_positive_single_row():
    with mock.patch(
        f"{MODULE}.fetch_bigquery",
        return_value=[
            {
                "channel": "release",
                "age_percentiles": [23 for i in range(100)],
                "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
                "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
            },
        ],
    ):
        status, data = await run(max_percentiles={"50": 42}, channels=["aurora"])

    assert status is True
    assert data["percentiles"] == "Not enough data during this period."


async def test_negative():
    with mock.patch(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(max_percentiles={"10": 99})

    assert status is False
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348000",
        "max_timestamp": "2019-09-16T06:24:58.741000",
        "percentiles": {"10": {"value": 100, "max": 99}},
    }
