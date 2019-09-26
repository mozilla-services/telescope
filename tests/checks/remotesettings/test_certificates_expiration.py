from datetime import datetime, timedelta
from unittest import mock

from checks.remotesettings.certificates_expiration import run
from tests.utils import patch_async


def mock_http_calls(mock_responses, server_url):
    changes_url = server_url + "/buckets/monitor/collections/changes/records"
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    metadata_url = server_url + "/buckets/bid/collections/cid"
    mock_responses.get(
        metadata_url, payload={"data": {"signature": {"x5u": "http://fake-x5u"}}}
    )


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"

    mock_http_calls(mock_responses, server_url)

    next_month = datetime.now() + timedelta(days=30)
    fake_cert = mock.MagicMock(not_valid_after=next_month)

    module = "checks.remotesettings.certificates_expiration"
    with patch_async(f"{module}.fetch_cert", return_value=fake_cert) as mocked:
        status, data = await run(server_url, min_remaining_days=29)
        mocked.assert_called_with("http://fake-x5u")

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"

    mock_http_calls(mock_responses, server_url)

    next_month = datetime.now() + timedelta(days=30)
    fake_cert = mock.MagicMock(not_valid_after=next_month)

    module = "checks.remotesettings.certificates_expiration"
    with patch_async(f"{module}.fetch_cert", return_value=fake_cert) as mocked:
        status, data = await run(server_url, min_remaining_days=31)
        mocked.assert_called_with("http://fake-x5u")

    assert status is False
    assert data == {
        "bid/cid": {"x5u": "http://fake-x5u", "expires": next_month.isoformat()}
    }
