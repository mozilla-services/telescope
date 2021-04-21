from datetime import datetime

import pytest

from checks.remotesettings.uptake_max_duration import run
from tests.utils import patch_async


MODULE = "checks.remotesettings.uptake_max_duration"

FAKE_ROWS = [
    {
        "channel": "release",
        "source": "blocklists/addons",
        "duration_percentiles": [i ** 2 for i in range(100)],
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
    {
        "channel": "release",
        "source": "settings-sync",
        "duration_percentiles": [i ** 2 for i in range(100)],
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
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


async def test_negative():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(source="blocklists/addons", max_percentiles={"10": 99})

    assert status is False
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348000",
        "max_timestamp": "2019-09-16T06:24:58.741000",
        "percentiles": {"10": {"value": 100, "max": 99}},
    }


async def test_bad_source_or_channel():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=[]):
        with pytest.raises(ValueError):
            await run(source="unknown", max_percentiles={})
