from unittest import mock

import responses

from checks.remotesettings.validate_signatures import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    module = "checks.remotesettings.validate_signatures"
    with mock.patch(
        f"{module}.download_collection_data", return_value=({"signature": {}}, [], 42)
    ):
        with mock.patch(f"{module}.validate_signature"):

            status, data = await run(None, server_url, ["bid"])

    assert status is True
    assert data == {}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    module = "checks.remotesettings.validate_signatures"
    with mock.patch(
        f"{module}.download_collection_data", return_value=({"signature": {}}, [], 42)
    ):
        with mock.patch(
            f"{module}.validate_signature", side_effect=AssertionError("boom")
        ):

            status, data = await run(None, server_url, ["bid"])

    assert status is False
    assert data == {"bid/cid": "boom"}
