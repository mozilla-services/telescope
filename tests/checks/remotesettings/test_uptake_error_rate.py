from checks.remotesettings.uptake_error_rate import run
from tests.utils import patch_async


MODULE = "checks.remotesettings.uptake_error_rate"

FAKE_ROWS = [
    {
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:20:00",
        "status": "success",
        "source": "blocklists/addons",
        "version": "68",
        "total": 10000,
    },
    {
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:20:00",
        "status": "success",
        "source": "blocklists/addons",
        "version": "67",
        "total": 10000,
    },
    {
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:20:00",
        "status": "up_to_date",
        "source": "blocklists/addons",
        "version": "70",
        "total": 15000,
    },
    {
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:20:00",
        "status": "network_error",
        "source": "blocklists/addons",
        "version": "70",
        "total": 2500,
    },
    {
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:20:00",
        "status": "network_error",
        "source": "blocklists/addons",
        "version": "71",
        "total": 2500,
    },
    {
        "min_timestamp": "2020-01-17T08:20:00",
        "max_timestamp": "2020-01-17T08:30:00",
        "status": "success",
        "source": "blocklists/addons",
        "version": "73",
        "total": 2000,
    },
    {
        "min_timestamp": "2020-01-17T08:20:00",
        "max_timestamp": "2020-01-17T08:30:00",
        "status": "custom_1_error",
        "source": "blocklists/addons",
        "version": "73",
        "total": 50,
    },
]


async def test_positive():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(api_key="", max_error_percentage=100.0)

    assert status is True
    assert data == {
        "sources": {},
        "max_rate": 2.44,
        "min_rate": 2.44,
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
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
                "min_timestamp": "2020-01-17T08:10:00",
                "max_timestamp": "2020-01-17T08:20:00",
            }
        },
        "max_rate": 2.44,
        "min_rate": 2.44,
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
    }


async def test_ignore_status():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="",
            max_error_percentage=0.1,
            ignore_status=["network_error", "custom_1_error"],
        )

    assert status is True
    assert data == {
        "sources": {},
        "max_rate": 0.0,
        "min_rate": 0.0,  # all ignored.
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
    }


async def test_ignore_status_on_version():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, ignore_status=["network_error@70"],
        )

    assert status is False
    assert data == {
        "sources": {
            "blocklists/addons": {
                "error_rate": 6.25,
                "ignored": {"network_error": 2500},
                "max_timestamp": "2020-01-17T08:20:00",
                "min_timestamp": "2020-01-17T08:10:00",
                "statuses": {
                    "network_error": 2500,
                    "success": 20000,
                    "up_to_date": 15000,
                },
            }
        },
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
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
                "min_timestamp": "2020-01-17T08:10:00",
                "max_timestamp": "2020-01-17T08:20:00",
            }
        },
        "max_rate": 2.44,
        "min_rate": 2.44,
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
    }


async def test_min_total_events():
    with patch_async(f"{MODULE}.fetch_redash", return_value=FAKE_ROWS):
        status, data = await run(
            api_key="", max_error_percentage=0.1, min_total_events=40001
        )

    assert status is True
    assert data == {
        "sources": {},
        "max_rate": 0.0,
        "min_rate": 100.0,
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
    }


async def test_filter_sources():
    fake_rows = FAKE_ROWS + [
        {
            "min_timestamp": "2020-01-17T08:10:00",
            "max_timestamp": "2020-01-17T08:20:00",
            "status": "sync_error",
            "source": "settings-sync",
            "version": "71",
            "total": 50000,
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
                "min_timestamp": "2020-01-17T08:10:00",
                "max_timestamp": "2020-01-17T08:20:00",
            }
        },
        "min_rate": 100.0,
        "max_rate": 100.0,
        "min_timestamp": "2020-01-17T08:10:00",
        "max_timestamp": "2020-01-17T08:30:00",
    }
