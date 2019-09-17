from checks.remotesettings.push_timestamp import run

from tests.utils import patch_async


async def test_positive(mock_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/records"
    mock_responses.head(url, status=200, headers={"ETag": "abc"})

    module = "checks.remotesettings.push_timestamp"
    with patch_async(f"{module}.get_push_timestamp", return_value="abc"):
        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is True
    assert data == {"remotesettings": "abc", "push": "abc"}


async def test_negative(mock_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/records"
    mock_responses.head(url, status=200, headers={"ETag": "abc"})

    module = "checks.remotesettings.push_timestamp"
    with patch_async(f"{module}.get_push_timestamp", return_value="def"):
        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is False
    assert data == {"remotesettings": "abc", "push": "def"}
