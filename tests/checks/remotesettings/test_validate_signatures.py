import ecdsa
import pytest

from checks.remotesettings.validate_signatures import run, validate_signature
from tests.utils import patch_async


COLLECTION_URL = "/buckets/{}/collections/{}"
RECORDS_URL = COLLECTION_URL + "/records"

FAKE_CERT = """-----BEGIN CERTIFICATE-----
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
-----BEGIN CERTIFICATE-----
MIIFezCCA2OgAwIBAgIDEAAEMA0GCSqGSIb3DQEBDAUAMH0xCzAJBgNVBAYTAlVT
MRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMS8wLQYDVQQLEyZNb3ppbGxh
IEFNTyBQcm9kdWN0aW9uIFNpZ25pbmcgU2VydmljZTEfMB0GA1UEAxMWcm9vdC1j
YS1wcm9kdWN0aW9uLWFtbzAeFw0xOTAyMDEyMjA2NDVaFw0yMTAxMzEyMjA2NDVa
MIGjMQswCQYDVQQGEwJVUzEcMBoGA1UEChMTTW96aWxsYSBDb3Jwb3JhdGlvbjEv
MC0GA1UECxMmTW96aWxsYSBBTU8gUHJvZHVjdGlvbiBTaWduaW5nIFNlcnZpY2Ux
RTBDBgNVBAMMPENvbnRlbnQgU2lnbmluZyBJbnRlcm1lZGlhdGUvZW1haWxBZGRy
ZXNzPWZveHNlY0Btb3ppbGxhLmNvbTB2MBAGByqGSM49AgEGBSuBBAAiA2IABCSV
pyWrz0Eo9xgh9R1VLgkX+lnGNNU6VhV2PhAnnGikcCeBeRSCBiSQePS2ZlURytes
JWrWoS0H+TvBdeRTgc32tftZxSSSwKUMmZRDappvM/uLbSrd6kY2rntETaneEqOC
AYkwggGFMAwGA1UdEwQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMBYGA1UdJQEB/wQM
MAoGCCsGAQUFBwMDMB0GA1UdDgQWBBSgHUoXT4zCKzVF8WPx2nBwp8744TCBqAYD
VR0jBIGgMIGdgBSzvOpYdKvhbngqsqucIx6oYyyXt6GBgaR/MH0xCzAJBgNVBAYT
AlVTMRwwGgYDVQQKExNNb3ppbGxhIENvcnBvcmF0aW9uMS8wLQYDVQQLEyZNb3pp
bGxhIEFNTyBQcm9kdWN0aW9uIFNpZ25pbmcgU2VydmljZTEfMB0GA1UEAxMWcm9v
dC1jYS1wcm9kdWN0aW9uLWFtb4IBATAzBglghkgBhvhCAQQEJhYkaHR0cDovL2Fk
ZG9ucy5hbGxpem9tLm9yZy9jYS9jcmwucGVtME4GA1UdHgRHMEWgQzAggh4uY29u
dGVudC1zaWduYXR1cmUubW96aWxsYS5vcmcwH4IdY29udGVudC1zaWduYXR1cmUu
bW96aWxsYS5vcmcwDQYJKoZIhvcNAQEMBQADggIBAG519ZvKmtUWL6+3CaU1n6L+
y0EIueOH+PjZX6ZToj6baPtQgWSCGKsEjZtpystkvLh2DCEdQIlBjuUEQ11atPaG
96Xp4l7VbaOUYEfoZxi3kpMLEOXUGvdcNFkj4KZY6rhYNhXV9lCkj1JCV+6iUpps
8yIE5vykGtQPRSWIH/bqvLD4U1Qy7gzxqBK2pV+YkzrA7d2bfwDpnz8gZYhb7e7p
EUvT7W+vJlrhrGLMTQ0A1jMEc+daiePr6/r/pSbXgHIdwUCgbRH2MPWje1ciXrHp
Xw6cJz8Iw73564AMBI3FaCV1iqouuMF54Tfk3zyyfGQs6+xEhQBbaHHGN+NdwE+U
3yfiTtgHwblxv/B7bVtvoGGfXd2SrTZtPxsdD8MwllNaAsdMhFDhkJ9Mufhxb6QF
+nxG9Qxn0+eJayoUHwe8XIXAW89s8uibv+zMiidrq9Dr5VJkhXZ6mvQTC9RPu/UE
at2t/z+FKIZOSBwpjIvr0hJbUhZJewKfW9ivCwhTstjcit9ZaTW/7Iml+zS657P0
fhygYvD/FczJD80MjMsrV3a+2H+oyL8yFuSMr1NO3G0e1BY4OKaLknto4ch6Qiqg
e45q0ccPgC24r5RhShwXRMK88Vt0f/d8+KH8OBztqBuhzAzrZXL2BHFuChf1e1Ql
tHN7fk4u+dLUHYv0ulzu
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIGYTCCBEmgAwIBAgIBATANBgkqhkiG9w0BAQwFADB9MQswCQYDVQQGEwJVUzEc
MBoGA1UEChMTTW96aWxsYSBDb3Jwb3JhdGlvbjEvMC0GA1UECxMmTW96aWxsYSBB
TU8gUHJvZHVjdGlvbiBTaWduaW5nIFNlcnZpY2UxHzAdBgNVBAMTFnJvb3QtY2Et
cHJvZHVjdGlvbi1hbW8wHhcNMTUwMzE3MjI1MzU3WhcNMjUwMzE0MjI1MzU3WjB9
MQswCQYDVQQGEwJVUzEcMBoGA1UEChMTTW96aWxsYSBDb3Jwb3JhdGlvbjEvMC0G
A1UECxMmTW96aWxsYSBBTU8gUHJvZHVjdGlvbiBTaWduaW5nIFNlcnZpY2UxHzAd
BgNVBAMTFnJvb3QtY2EtcHJvZHVjdGlvbi1hbW8wggIgMA0GCSqGSIb3DQEBAQUA
A4ICDQAwggIIAoICAQC0u2HXXbrwy36+MPeKf5jgoASMfMNz7mJWBecJgvlTf4hH
JbLzMPsIUauzI9GEpLfHdZ6wzSyFOb4AM+D1mxAWhuZJ3MDAJOf3B1Rs6QorHrl8
qqlNtPGqepnpNJcLo7JsSqqE3NUm72MgqIHRgTRsqUs+7LIPGe7262U+N/T0LPYV
Le4rZ2RDHoaZhYY7a9+49mHOI/g2YFB+9yZjE+XdplT2kBgA4P8db7i7I0tIi4b0
B0N6y9MhL+CRZJyxdFe2wBykJX14LsheKsM1azHjZO56SKNrW8VAJTLkpRxCmsiT
r08fnPyDKmaeZ0BtsugicdipcZpXriIGmsZbI12q5yuwjSELdkDV6Uajo2n+2ws5
uXrP342X71WiWhC/dF5dz1LKtjBdmUkxaQMOP/uhtXEKBrZo1ounDRQx1j7+SkQ4
BEwjB3SEtr7XDWGOcOIkoJZWPACfBLC3PJCBWjTAyBlud0C5n3Cy9regAAnOIqI1
t16GU2laRh7elJ7gPRNgQgwLXeZcFxw6wvyiEcmCjOEQ6PM8UQjthOsKlszMhlKw
vjyOGDoztkqSBy/v+Asx7OW2Q7rlVfKarL0mREZdSMfoy3zTgtMVCM0vhNl6zcvf
5HNNopoEdg5yuXo2chZ1p1J+q86b0G5yJRMeT2+iOVY2EQ37tHrqUURncCy4uwIB
A6OB7TCB6jAMBgNVHRMEBTADAQH/MA4GA1UdDwEB/wQEAwIBBjAWBgNVHSUBAf8E
DDAKBggrBgEFBQcDAzCBkgYDVR0jBIGKMIGHoYGBpH8wfTELMAkGA1UEBhMCVVMx
HDAaBgNVBAoTE01vemlsbGEgQ29ycG9yYXRpb24xLzAtBgNVBAsTJk1vemlsbGEg
QU1PIFByb2R1Y3Rpb24gU2lnbmluZyBTZXJ2aWNlMR8wHQYDVQQDExZyb290LWNh
LXByb2R1Y3Rpb24tYW1vggEBMB0GA1UdDgQWBBSzvOpYdKvhbngqsqucIx6oYyyX
tzANBgkqhkiG9w0BAQwFAAOCAgEAaNSRYAaECAePQFyfk12kl8UPLh8hBNidP2H6
KT6O0vCVBjxmMrwr8Aqz6NL+TgdPmGRPDDLPDpDJTdWzdj7khAjxqWYhutACTew5
eWEaAzyErbKQl+duKvtThhV2p6F6YHJ2vutu4KIciOMKB8dslIqIQr90IX2Usljq
8Ttdyf+GhUmazqLtoB0GOuESEqT4unX6X7vSGu1oLV20t7t5eCnMMYD67ZBn0YIU
/cm/+pan66hHrja+NeDGF8wabJxdqKItCS3p3GN1zUGuJKrLykxqbOp/21byAGog
Z1amhz6NHUcfE6jki7sM7LHjPostU5ZWs3PEfVVgha9fZUhOrIDsyXEpCWVa3481
LlAq3GiUMKZ5DVRh9/Nvm4NwrTfB3QkQQJCwfXvO9pwnPKtISYkZUqhEqvXk5nBg
QCkDSLDjXTx39naBBGIVIqBtKKuVTla9enngdq692xX/CgO6QJVrwpqdGjebj5P8
5fNZPABzTezG3Uls5Vp+4iIWVAEDkK23cUj3c/HhE+Oo7kxfUeu5Y1ZV3qr61+6t
ZARKjbu1TuYQHf0fs+GwID8zeLc2zJL7UzcHFwwQ6Nda9OJN4uPAuC/BKaIpxCLL
26b24/tRam4SJjqpiq20lynhUrmTtt6hbG3E1Hpy3bmkt2DYnuMFwEx2gfXNcnbT
wNuvFqc=
-----END CERTIFICATE-----
"""


FAKE_SIGNATURE = (
    "ZtN8SKGhuydx6vr7lmKKX7Erln-42ICCo192KqI54-1nloBMEm2-h6bytNtg7RzwUQ8"
    "GkBpEAf6AlWmFT6G4REA6Zu8dp2eOjY9e5Oo2MkZ59iDySbbChNVaKu3jVb0h"
)


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

    mock_responses.get(
        server_url + RECORDS_URL.format("bid", "cid"),
        payload={"data": []},
        headers={"ETag": '"42"'},
    )

    mock_responses.get(
        server_url + COLLECTION_URL.format("bid", "cid"),
        payload={"data": {"signature": {}}},
    )

    module = "checks.remotesettings.validate_signatures"
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


async def test_valid_signature(mock_aioresponses):
    url = "http://some/cert"
    mock_aioresponses.get(url, body=FAKE_CERT)
    fake = {"signature": FAKE_SIGNATURE, "x5u": url}

    # Not raising.
    await validate_signature({"signature": fake}, [], 1485794868067, {})


async def test_invalid_signature(mock_aioresponses):
    url = "http://some/cert"
    mock_aioresponses.get(url, body=FAKE_CERT)
    fake = {"signature": "_" + FAKE_SIGNATURE[1:], "x5u": url}

    with pytest.raises(Exception) as exc_info:
        await validate_signature({"signature": fake}, [], 1485794868067, {})

    assert type(exc_info.value) == ecdsa.keys.BadSignatureError
