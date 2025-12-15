from unittest import mock

import pytest
from aiohttp import ClientResponseError

from checks.remotesettings.validate_signatures import run, validate_signature


MODULE = "checks.remotesettings.validate_signatures"
COLLECTION_URL = "/buckets/{}/collections/{}"
CHANGESET_URL = COLLECTION_URL + "/changeset"
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


async def test_positive(mock_aioresponses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("bid", "cid", 42),
        payload={
            "metadata": {
                "signatures": [{"x5u": "https://cert-chain/url", "signature": "sig"}]
            },
            "changes": [],
            "timestamp": 42,
        },
    )

    with mock.patch(f"{MODULE}.SignatureVerifier.verify", return_value=True):
        status, data = await run(server_url, ["bid"])

    assert status is True
    assert data == {}


async def test_negative(mock_aioresponses):
    server_url = "http://fake.local/v1"
    x5u_url = "http://fake-x5u-url/"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    mock_aioresponses.get(x5u_url, body=CERT)
    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("bid", "cid"),
        payload={
            "metadata": {"signatures": [{"x5u": x5u_url, "signature": ""}]},
            "changes": [],
            "timestamp": 42,
        },
    )

    status, data = await run(server_url, ["bid"])

    assert status is False
    assert data == {
        "bid/cid": "CertificateExpired(datetime.datetime(2019, 11, 11, 22, 44, 31, tzinfo=datetime.timezone.utc))"
    }


async def test_root_hash_is_decoded_if_specified(mock_aioresponses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("bid", "cid"),
        payload={
            "metadata": {
                "signatures": [{"x5u": "http://fake-x5u-url/", "signature": ""}]
            },
            "changes": [],
            "timestamp": 42,
        },
    )

    with mock.patch(f"{MODULE}.SignatureVerifier") as mocked:
        with mock.patch(f"{MODULE}.validate_signature"):
            await run(server_url, ["bid"], root_hash="00:FF")

    [[_, kwargs]] = mocked.call_args_list
    assert kwargs["root_hash"] == b"\x00\xff"


async def test_missing_signature():
    with pytest.raises(AssertionError) as exc_info:
        await validate_signature(verifier=None, metadata={}, records=[], timestamp=42)
    assert exc_info.value.args[0] == "Missing signature"


async def test_retry_fetch_records(mock_aioresponses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )

    records_url = server_url + CHANGESET_URL.format("bid", "cid")
    mock_aioresponses.get(records_url, status=500)
    mock_aioresponses.get(records_url, status=500)
    mock_aioresponses.get(
        records_url,
        payload={"metadata": {"signatures": [{}]}, "changes": [], "timestamp": 42},
    )

    with mock.patch(f"{MODULE}.validate_signature"):
        status, data = await run(server_url, ["bid"])

    assert status is True


async def test_retry_fetch_x5u(mock_aioresponses, no_sleep):
    server_url = "http://fake.local/v1"
    x5u_url = "http://fake-x5u-url/"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    mock_aioresponses.get(x5u_url, status=500)
    mock_aioresponses.get(x5u_url, status=500)
    mock_aioresponses.get(x5u_url, body=CERT)

    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("bid", "cid"),
        payload={
            "metadata": {"signatures": [{"x5u": x5u_url, "signature": ""}]},
            "changes": [],
            "timestamp": 42,
        },
    )

    status, data = await run(server_url, ["bid"])

    assert status is False
    # Here we can see that it fails for other reasons than x5u.
    assert data == {
        "bid/cid": "CertificateExpired(datetime.datetime(2019, 11, 11, 22, 44, 31, tzinfo=datetime.timezone.utc))"
    }


async def test_unexpected_error_raises(mock_aioresponses, no_sleep):
    server_url = "http://fake.local/v1"
    x5u_url = "http://fake-x5u-url/"
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    mock_aioresponses.get(x5u_url, status=500)
    mock_aioresponses.get(x5u_url, status=500)
    mock_aioresponses.get(x5u_url, status=500)

    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("bid", "cid"),
        payload={
            "metadata": {"signatures": [{"x5u": x5u_url, "signature": ""}]},
            "changes": [],
            "timestamp": 42,
        },
    )

    with pytest.raises(ClientResponseError):
        await run(server_url, ["bid"])
