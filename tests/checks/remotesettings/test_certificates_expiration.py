from unittest import mock
from datetime import datetime, timedelta

import responses

from checks.remotesettings.certificates_expiration import run


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + "/buckets/monitor/collections/changes/records"
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    metadata_url = server_url + "/buckets/bid/collections/cid"
    mocked_responses.add(
        responses.GET,
        metadata_url,
        json={"data": {"signature": {"x5u": "http://fake-x5u"}}},
    )

    next_month = datetime.now() + timedelta(days=30)

    module = "checks.remotesettings.certificates_expiration"
    with mock.patch(
        f"{module}.fetch_certificate_expiration", return_value=next_month
    ) as mocked:
        status, data = await run(server_url, min_remaining_days=29)
        mocked.assert_called_with("http://fake-x5u")

    assert status is True
    assert data == {}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + "/buckets/monitor/collections/changes/records"
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {
                    "id": "abc",
                    "bucket": "bid",
                    "collection": "cid",
                    "last_modified": 42,
                },
                {
                    "id": "def",
                    "bucket": "bid",
                    "collection": "missing",
                    "last_modified": 41,
                },
            ]
        },
    )

    metadata_url = server_url + "/buckets/bid/collections/cid"
    mocked_responses.add(
        responses.GET,
        metadata_url,
        json={"data": {"signature": {"x5u": "http://fake-x5u"}}},
    )

    missing_signature_metadata_url = server_url + "/buckets/bid/collections/missing"
    mocked_responses.add(
        responses.GET, missing_signature_metadata_url, json={"data": {}}
    )

    next_month = datetime.now() + timedelta(days=30)

    module = "checks.remotesettings.certificates_expiration"
    with mock.patch(
        f"{module}.fetch_certificate_expiration", return_value=next_month
    ) as mocked:
        status, data = await run(server_url, min_remaining_days=31)
        mocked.assert_called_with("http://fake-x5u")

    assert status is False
    assert data == {
        "bid/cid": {"x5u": "http://fake-x5u", "expires": next_month.isoformat()},
        "bid/missing": {"x5u": None, "expires": None},
    }
