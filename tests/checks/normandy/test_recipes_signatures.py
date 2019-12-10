from unittest import mock

import autograph_utils
import pytest

from checks.normandy.recipes_signatures import run, validate_signature
from tests.utils import patch_async


MODULE = "checks.normandy.recipes_signatures"
RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_aioresponses):
    server_url = "http://fake.local/v1"
    records_url = server_url + RECORDS_URL.format("main", "normandy-recipes")
    mock_aioresponses.get(
        records_url,
        payload={
            "data": [
                {
                    "id": "12",
                    "last_modified": 42,
                    "signature": {"signature": "abc", "x5u": "http://fake-x5u-url"},
                    "recipe": {"id": 12},
                }
            ]
        },
    )

    with patch_async(f"{MODULE}.validate_signature", return_value=True):
        status, data = await run(server_url, "normandy-recipes", root_hash="AA")

    assert status is True
    assert data == {}


async def test_negative(mock_aioresponses):
    server_url = "http://fake.local/v1"
    records_url = server_url + RECORDS_URL.format("main", "normandy-recipes")
    mock_aioresponses.get(
        records_url,
        payload={
            "data": [
                {
                    "id": "12",
                    "last_modified": 42,
                    "signature": {"signature": "abc", "x5u": "http://fake-x5u-url"},
                    "recipe": {"id": 12},
                }
            ]
        },
    )

    with patch_async(f"{MODULE}.validate_signature", side_effect=ValueError("boom")):
        status, data = await run(server_url, "normandy-recipes", root_hash="AA")

    assert status is False
    assert data == {"12": "ValueError('boom')"}


async def test_invalid_signature():
    verifier = mock.MagicMock()
    verifier.verify.side_effect = autograph_utils.BadSignature

    recipe = {
        "signature": {"signature": "abc", "x5u": "http://fake-x5u-url"},
        "recipe": {"id": 12},
    }

    with pytest.raises(autograph_utils.BadSignature):
        await validate_signature(verifier, recipe)

    verifier.verify.assert_called_with(b'{"id":12}', "abc", "http://fake-x5u-url")
