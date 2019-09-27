from checks.remotesettings.uptake_max_age import run
from tests.utils import patch_async

MODULE = "checks.remotesettings.uptake_max_age"

FAKE_ROWS = [
    {
        "age_percentiles": [i ** 2 for i in range(100)],
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
    }
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_percentiles={"10": 101, "50": 2501})

    assert status is True
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
        "percentiles": {
            "10": {"value": 100, "max": 101},
            "50": {"value": 2500, "max": 2501},
        },
    }


async def test_negative():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_percentiles={"10": 99})

    assert status is False
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
        "percentiles": {"10": {"value": 100, "max": 99}},
    }
