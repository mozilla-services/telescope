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


async def test_filter_on_legacy_versions_by_default(mock_aioresponses):
    url_versions = "https://product-details.mozilla.org/1.0/firefox_versions.json"
    mock_aioresponses.get(
        url_versions,
        payload={
            "FIREFOX_DEVEDITION": "127.0b4",
            "FIREFOX_ESR": "115.0.1esr",
            "FIREFOX_NIGHTLY": "128.0a1",
        },
    )
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS) as mocked:
        await run(status="sign_retry_error", max_total=1000)

    [[call_args, _]] = mocked.call_args_list
    assert "WHERE SAFE_CAST(version AS INTEGER) >= 115" in call_args[0]


async def test_can_include_legacy_versions():
    with patch_async(f"{MODULE}.fetch_bigquery", return_value=FAKE_ROWS) as mocked:
        await run(
            status="sign_retry_error", max_total=1000, include_legacy_versions=True
        )

    [[call_args, _]] = mocked.call_args_list
    assert "WHERE SAFE_CAST(version AS INTEGER) >= 91" in call_args[0]
