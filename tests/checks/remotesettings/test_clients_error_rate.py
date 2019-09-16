import asyncio
from unittest import mock

from checks.remotesettings.clients_error_rate import run, fetch_redash


async def test_fetch_redash(mock_aioresponse):
    url = "https://sql.telemetry.mozilla.org/api/queries/64808/results.json?api_key=abc"

    row = {
        "status": "network_error",
        "source": "blocklists/addons",
        "min_timestamp": "2019-09-16T01:36:12.348",
        "total": 1360,
        "max_timestamp": "2019-09-16T07:24:58.741",
    }

    mock_aioresponse.get(
        url, status=200, payload={"query_result": {"data": {"rows": [row]}}}
    )

    rows = await fetch_redash(api_key="abc")

    assert rows == [row]


MODULE = "checks.remotesettings.clients_error_rate"

FAKE_ROWS = [
    {
        "status": "success",
        "source": "blocklists/addons",
        "total": 20000,
        "min_timestamp": "2019-09-16T02:36:12.348",
        "max_timestamp": "2019-09-16T06:24:58.741",
    },
    {
        "status": "up_to_date",
        "source": "blocklists/addons",
        "total": 15000,
        "min_timestamp": "2019-09-16T03:36:12.348",
        "max_timestamp": "2019-09-16T05:24:58.741",
    },
    {
        "status": "network_error",
        "source": "blocklists/addons",
        "total": 5000,
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    },
]


async def test_positive():
    with mock.patch(f"{MODULE}.fetch_redash") as mocked:
        f = asyncio.Future()
        f.set_result(FAKE_ROWS)
        mocked.return_value = f

        status, data = await run(api_key="", max_percentage=100.0)

    assert status is True
    assert data == {
        "collections": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_negative():
    with mock.patch(f"{MODULE}.fetch_redash") as mocked:
        f = asyncio.Future()
        f.set_result(FAKE_ROWS)
        mocked.return_value = f

        status, data = await run(api_key="", max_percentage=0.1)

    assert status is False
    assert data == {
        "collections": {
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
    with mock.patch(f"{MODULE}.fetch_redash") as mocked:
        f = asyncio.Future()
        f.set_result(FAKE_ROWS)
        mocked.return_value = f

        status, data = await run(
            api_key="", max_percentage=0.1, ignore_status=["network_error"]
        )

    assert status is True
    assert data == {
        "collections": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }


async def test_min_total_events():
    with mock.patch(f"{MODULE}.fetch_redash") as mocked:
        f = asyncio.Future()
        f.set_result(FAKE_ROWS)
        mocked.return_value = f

        status, data = await run(api_key="", max_percentage=0.1, min_total_events=40001)

    assert status is True
    assert data == {
        "collections": {},
        "min_timestamp": "2019-09-16T01:36:12.348",
        "max_timestamp": "2019-09-16T07:24:58.741",
    }
