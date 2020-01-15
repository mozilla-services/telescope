from checks.remotesettings.uptake_error_rate import run
from tests.utils import patch_async


MODULE = "checks.remotesettings.uptake_error_rate"

FAKE_ROWS = [
    {
        "status": "success",
        "source": "blocklists/addons",
        "version": "68",
        "total": 10000,
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
    },
    {
        "status": "success",
        "source": "blocklists/addons",
        "version": "67",
        "total": 10000,
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
    },
    {
        "status": "up_to_date",
        "source": "blocklists/addons",
        "version": "70",
        "total": 15000,
        "min_timestamp": "2019-09-16T03:36:12.348",
        "max_timestamp": "2019-09-16T05:24:58.741",
    },
    {
        "status": "network_error",
        "source": "blocklists/addons",
        "version": "71",
        "total": 5000,
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_error_percentage=100.0)

    assert status is True
    assert data == {
        "sources": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_negative():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_error_percentage=0.1)

    assert status is False
    assert data == {
        "sources": {
            "blocklists/addons": {
                "error_rate": 12.5,
                "statuses": {
                    "success": 20000,
                    "up_to_date": 15000,
                    "network_error": 5000,
                },
                "ignored": {},
            }
        },
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_ignore_status():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, ignore_status=["network_error"]
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_ignore_version():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, ignore_versions=[68]
        )

    assert status is False
    assert data == {
        "sources": {
            "blocklists/addons": {
                "error_rate": 12.5,
                "ignored": {"success": 10000},
                "statuses": {
                    "network_error": 5000,
                    "success": 10000,
                    "up_to_date": 15000,
                },
            }
        },
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_min_total_events():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, min_total_events=40001
        )

    assert status is True
    assert data == {
        "sources": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_filter_sources():
    fake_rows = FAKE_ROWS + [
        {
            "status": "sync_error",
            "source": "settings-sync",
            "version": "71",
            "total": 50000,
            "min_timestamp": "2019-09-16T01:36:12.348",
            "max_timestamp": "2019-09-16T07:24:58.741",
        },
    ]
    with patch_async(f"{MODULE}.fetch_redash", return_value=fake_rows):
        status, data = await run(
            api_key="", max_error_percentage=1, sources=["settings-sync"]
        )

    assert status is False
    assert data == {
        "sources": {
            "settings-sync": {
                "error_rate": 100.0,
                "ignored": {},
                "statuses": {"sync_error": 50000},
            }
        },
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }
