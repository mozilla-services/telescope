from unittest import mock

import autograph_utils
import pytest

from checks.normandy.recipe_signatures import run, validate_signature
from telescope.utils import ClientSession
from tests.utils import patch_async


MODULE = "checks.normandy.recipe_signatures"
CHANGESET_URL = "/buckets/{}/collections/{}/changeset?_expected={}"

CERT = """-----BEGIN CERTIFICATE-----
MIIDBTCCAougAwIBAgIIFcbkDrCrHAkwCgYIKoZIzj0EAwMwgaMxCzAJBgNVBAYT
AlVTMRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMS8wLQYDVQQLEyZNb3pp
bGxhIEFNTyBQcm9kdWN0aW9uIFNpZ25pbmcgU2VydmljZTFFMEMGA1UEAww8Q29u
dGVudCBTaWduaW5nIEludGVybWVkaWF0ZS9lbWFpbEFkZHJlc3M9Zm94c2VjQG1v
emlsbGEuY29tMB4XDTE5MDgyMzIyNDQzMVoXDTE5MTExMTIyNDQzMVowgakxCzAJ
BgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlhMRYwFAYDVQQHEw1Nb3VudGFp
biBWaWV3MRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMRcwFQYDVQQLEw5D
bG91ZCBTZXJ2aWNlczE2MDQGA1UEAxMtcGlubmluZy1wcmVsb2FkLmNvbnRlbnQt
c2lnbmF0dXJlLm1vemlsbGEub3JnMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEX6Zd
vZ32rj9rDdRInp0kckbMtAdxOQxJ7EVAEZB2KOLUyotQL6A/9YWrMB4Msb4hfvxj
Nw05CS5/J4qUmsTkKLXQskjRe9x96uOXxprWiVwR4OLYagkJJR7YG1mTXmFzo4GD
MIGAMA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAzAfBgNVHSME
GDAWgBSgHUoXT4zCKzVF8WPx2nBwp8744TA4BgNVHREEMTAvgi1waW5uaW5nLXBy
ZWxvYWQuY29udGVudC1zaWduYXR1cmUubW96aWxsYS5vcmcwCgYIKoZIzj0EAwMD
aAAwZQIxAOi2Eusi6MtEPOARiU+kZIi1vPnzTI71cA2ZIpzZ9aYg740eoJml8Guz
3oC6yXiIDAIwSy4Eylf+/nSMA73DUclcCjZc2yfRYIogII+krXBxoLkbPJcGaitx
qvRy6gQ1oC/z
-----END CERTIFICATE-----
"""


@pytest.fixture()
def mock_randint():
    with mock.patch("checks.normandy.remotesettings_recipes.random.randint") as mocked:
        yield mocked


async def test_positive(mock_aioresponses, mock_randint):
    server_url = "http://fake.local/v1"
    mock_randint.return_value = 314
    changeset_url = server_url + CHANGESET_URL.format("main", "normandy-recipes", 314)
    mock_aioresponses.get(
        changeset_url,
        payload={
            "changes": [
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
        status, data = await run(server_url, "normandy-recipes")

    assert status is True
    assert data == {}


async def test_negative(mock_aioresponses, mock_randint):
    server_url = "http://fake.local/v1"
    mock_randint.return_value = 314
    changeset_url = server_url + CHANGESET_URL.format("main", "normandy-recipes", 314)
    mock_aioresponses.get(
        changeset_url,
        payload={
            "changes": [
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
        status, data = await run(server_url, "normandy-recipes")

    assert status is False
    assert data == {"12": "ValueError('boom')"}


async def test_invalid_x5u(mock_aioresponses):
    x5u = "http://fake-x5u-url"
    mock_aioresponses.get(x5u, body=CERT)
    cache = autograph_utils.MemoryCache()
    async with ClientSession() as session:
        verifier = autograph_utils.SignatureVerifier(session, cache, root_hash=None)

        recipe = {
            "signature": {"signature": "abc", "x5u": x5u},
            "recipe": {"id": 12},
        }

        with pytest.raises(autograph_utils.BadCertificate):
            await validate_signature(verifier, recipe)


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
