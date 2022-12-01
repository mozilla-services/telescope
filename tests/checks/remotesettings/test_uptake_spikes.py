from datetime import datetime

from checks.remotesettings.uptake_spikes import run
from tests.utils import patch_async


MODULE = "checks.remotesettings.uptake_spikes"

FAKE_ROWS = [
    {
        "source": "main/whats-new-panel",
        "total": 500,
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
    {
        "source": "main/cfr",
        "total": 200,
        "min_timestamp": datetime.fromisoformat("2019-09-16T02:36:12.348"),
        "max_timestamp": datetime.fromisoformat("2019-09-16T06:24:58.741"),
    },
    {
        "source": "main/cfr",
        "total": 300,
        "min_timestamp": datetime.fromisoformat("2022-01-01T00:00:00.000"),
        "max_timestamp": datetime.fromisoformat("2022-01-01T00:00:10.000"),
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(status="sign_retry_error", max_total=1000)

    assert status is True
    assert data == {
        "min_timestamp": "2019-09-16T02:36:12.348000",
        "max_timestamp": "2022-01-01T00:00:10",
        "max_total": 700,
        "sources": {
            "main/whats-new-panel": {
                "total": 500,
                "min_timestamp": "2019-09-16T02:36:12.348000",
                "max_timestamp": "2019-09-16T06:24:58.741000",
            },
            "main/cfr": {
                "total": 300,
                "min_timestamp": "2022-01-01T00:00:00",
                "max_timestamp": "2022-01-01T00:00:10",
            },
        },
    }


async def test_negative():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS):
        status, data = await run(status="sign_retry_error", max_total=200)

    assert status is False
