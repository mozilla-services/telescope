import datetime

import ecdsa
import pytest

from checks.remotesettings.validate_signatures import (
    run,
    validate_signature,
    fetch_cert,
)
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


async def test_fetch_cert(mock_aioresponses):
    url = "http://some/cert"
    mock_aioresponses.get(
        url,
        body="""
-----BEGIN CERTIFICATE-----
MIIDBjCCAougAwIBAgIIFcCz5QIGv38wCgYIKoZIzj0EAwMwgaMxCzAJBgNVBAYT
AlVTMRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMS8wLQYDVQQLEyZNb3pp
bGxhIEFNTyBQcm9kdWN0aW9uIFNpZ25pbmcgU2VydmljZTFFMEMGA1UEAww8Q29u
dGVudCBTaWduaW5nIEludGVybWVkaWF0ZS9lbWFpbEFkZHJlc3M9Zm94c2VjQG1v
emlsbGEuY29tMB4XDTE5MDgwMzE4NTQyNloXDTE5MTAyMjE4NTQyNlowgakxCzAJ
BgNVBAYTAlVTMRMwEQYDVQQIEwpDYWxpZm9ybmlhMRYwFAYDVQQHEw1Nb3VudGFp
biBWaWV3MRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMRcwFQYDVQQLEw5D
bG91ZCBTZXJ2aWNlczE2MDQGA1UEAxMtcmVtb3RlLXNldHRpbmdzLmNvbnRlbnQt
c2lnbmF0dXJlLm1vemlsbGEub3JnMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEOleC
qENusPrvl0SAL+EeOBy/yfHFwCoN5hnZEiDoHzZhIqny5Cpm1r66lPPBygbVKSui
qvBii19e7Ug8wbnFZm96OcTgSC6Tw3TvSQfMCQSGe3fBmTJbRKpr3ZJ80NWoo4GD
MIGAMA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAzAfBgNVHSME
GDAWgBSgHUoXT4zCKzVF8WPx2nBwp8744TA4BgNVHREEMTAvgi1yZW1vdGUtc2V0
dGluZ3MuY29udGVudC1zaWduYXR1cmUubW96aWxsYS5vcmcwCgYIKoZIzj0EAwMD
aQAwZgIxALWEHtRF+fVyq0dV/zTJbHuglMFEuf+0vheT+pV6nfXxMpRscTQIkM3F
CIRn5k6VwwIxAPX1YhpG6cjoMdpLlsgYQop684IuM1FBjCrCrF8gHb/9a0vLu/9N
STWRsaoS+0ejbQ==
-----END CERTIFICATE-----
    """,
    )
    cert = await fetch_cert(url)
    assert cert.not_valid_after == datetime.datetime(2019, 10, 22, 18, 54, 26)
