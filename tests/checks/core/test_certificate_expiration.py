from datetime import datetime, timedelta, timezone
from unittest import mock

from checks.core.certificate_expiration import fetch_cert, run
from telescope.utils import utcnow


MODULE = "checks.core.certificate_expiration"

CERT = """
-----BEGIN CERTIFICATE-----
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


async def test_positive():
    url = "https://fake.local"

    next_month = utcnow() + timedelta(days=30)
    fake_cert = mock.MagicMock(not_valid_before_utc=utcnow(), not_valid_after_utc=next_month)

    with mock.patch(f"{MODULE}.fetch_cert", return_value=fake_cert) as mocked:
        status, data = await run(url)
        mocked.assert_called_with(url)

    assert status is True
    assert data == {"expires": next_month.isoformat()}


async def test_negative():
    url = "https://fake.local"

    next_month = utcnow() + timedelta(days=30)
    fake_cert = mock.MagicMock(not_valid_before_utc=utcnow(), not_valid_after_utc=next_month)

    with mock.patch(f"{MODULE}.fetch_cert", return_value=fake_cert):
        status, data = await run(url, min_remaining_days=40)

    assert status is False
    assert data == {"expires": next_month.isoformat()}


async def test_positive_bounded_maximum():
    url = "https://fake.local"

    last_year = utcnow() - timedelta(days=365)
    next_month = utcnow() + timedelta(days=30)
    fake_cert = mock.MagicMock(not_valid_before_utc=last_year, not_valid_after_utc=next_month)

    with mock.patch(f"{MODULE}.fetch_cert", return_value=fake_cert):
        status, data = await run(url, max_remaining_days=7)

    assert status is True
    assert data == {"expires": next_month.isoformat()}


async def test_fetch_cert(mock_aioresponses):
    url = "https://fake.local"
    # The check will try to fetch the URL content first.
    mock_aioresponses.get(url, body="<html>Something</html>")
    # Then will try using SSL.
    with mock.patch(
        f"{MODULE}.ssl.get_server_certificate", return_value=CERT
    ) as mocked:
        cert = await fetch_cert(url)
        mocked.assert_called_with(("fake.local", 443))

    assert cert.not_valid_after_utc == datetime(2019, 11, 11, 22, 44, 31, tzinfo=timezone.utc)


async def test_fetch_cert_from_url(mock_aioresponses):
    url = "http://domain.tld/cert.pem"
    mock_aioresponses.get(url, body=CERT)

    cert = await fetch_cert(url)

    assert cert.not_valid_after_utc == datetime(2019, 11, 11, 22, 44, 31, tzinfo=timezone.utc)
