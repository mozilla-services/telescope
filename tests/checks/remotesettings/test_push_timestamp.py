import asyncio
from unittest import mock

from checks.remotesettings.push_timestamp import run


async def test_positive(mocked_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/records"
    mocked_responses.head(url, status=200, headers={"ETag": "abc"})

    module = "checks.remotesettings.push_timestamp"
    with mock.patch(f"{module}.get_push_timestamp") as mocked:
        f = asyncio.Future()
        f.set_result("abc")
        mocked.return_value = f

        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is True
    assert data == {"remotesettings": "abc", "push": "abc"}


async def test_negative(mocked_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/records"
    mocked_responses.head(url, status=200, headers={"ETag": "abc"})

    module = "checks.remotesettings.push_timestamp"
    with mock.patch(f"{module}.get_push_timestamp") as mocked:
        f = asyncio.Future()
        f.set_result("def")
        mocked.return_value = f

        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is False
    assert data == {"remotesettings": "abc", "push": "def"}
