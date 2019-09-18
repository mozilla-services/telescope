from unittest import mock

import ecdsa
import pytest

from checks.remotesettings.validate_signatures import run, validate_signature
from tests.utils import patch_async


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    module = "checks.remotesettings.validate_signatures"
    with patch_async(
        f"{module}.download_collection_data", return_value=({"signature": {}}, [], 42)
    ):
        with patch_async(f"{module}.validate_signature"):

            status, data = await run(server_url, ["bid"])

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    module = "checks.remotesettings.validate_signatures"
    with patch_async(
        f"{module}.download_collection_data", return_value=({"signature": {}}, [], 42)
    ):
        with patch_async(
            f"{module}.validate_signature", side_effect=AssertionError("boom")
        ):

            status, data = await run(server_url, ["bid"])

    assert status is False
    assert data == {"bid/cid": "boom"}


async def test_missing_signature():
    with pytest.raises(AssertionError) as exc_info:
        await validate_signature({}, [], 0, {})
    assert exc_info.value.args[0] == "Missing signature"


async def test_invalid_signature():
    fake = {"signature": "abc", "public_key": "0efg"}
    with pytest.raises(Exception) as exc_info:
        await validate_signature({"signature": fake}, [], 0, {})
    assert type(exc_info.value) == ecdsa.der.UnexpectedDER
