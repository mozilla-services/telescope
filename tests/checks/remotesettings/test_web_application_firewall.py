import urllib.parse
from datetime import datetime
from unittest import mock

import pytest

from checks.remotesettings.web_application_firewall import build_expectations, run


SERVER_URL = "https://fake.local"
CDN_URL = "http://cdn/"
CERT_URL = "http://cert/chain.pem"


@pytest.fixture(autouse=True)
def utcnow():
    with mock.patch("checks.remotesettings.web_application_firewall.utcnow") as mocked:
        mocked.return_value = datetime(2026, 7, 22)
        yield mocked


@pytest.fixture()
def mock_expectations(mock_aioresponses):
    expectations = build_expectations()

    status_by_url = {
        f"{SERVER_URL}{url}": expected for url, expected, _ in expectations
    }

    for url in status_by_url:
        mock_aioresponses.head(
            url, status=status_by_url.get(urllib.parse.unquote(str(url)), 200)
        )


async def test_positive(mock_expectations):
    status, data = await run(server=SERVER_URL)

    assert data == {}
    assert status is True


async def test_positive_strips_version_from_server_url(mock_expectations):
    # Passing a URL with a version suffix should behave like the base URL.
    status, data = await run(server=f"{SERVER_URL}/v1")

    assert status is True
    assert data == {}


async def test_negative_wrong_status(mock_expectations, mock_aioresponses):
    mock_aioresponses.head(f"{SERVER_URL}/", status=500, repeat=True)

    status, data = await run(server=SERVER_URL)

    assert status is False
    assert data[f"{SERVER_URL}/"]["expected"] == 307
    assert data[f"{SERVER_URL}/"]["status"] == 500
