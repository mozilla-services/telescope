from unittest import mock

import pytest

from checks.core.http_versions import run


MODULE = "checks.core.http_versions"


@pytest.fixture
def mocked_curl():
    with mock.patch(f"{MODULE}.subprocess.run") as mocked_curl:
        yield mocked_curl


async def test_positive(mocked_curl):
    mocked_curl.side_effect = [
        mock.Mock(stdout=b"1\n"),
        mock.Mock(stdout=b"1.1\n"),
        mock.Mock(stdout=b"2\n"),
        mock.Mock(stdout=b"3\n"),
    ]

    status, data = await run("http://server.local")

    assert status is True
    assert sorted(data) == ["1", "1.1", "2", "3"]


async def test_negative_missing(mocked_curl):
    mocked_curl.side_effect = [
        mock.Mock(stdout=b"1\n"),
        mock.Mock(stdout=b"1.1\n"),
        mock.Mock(stdout=b"2\n"),
        mock.Mock(stdout=b"2\n"),
    ]

    status, data = await run("http://server.local")

    assert status is False
    assert data == "HTTP version(s) 3 unsupported"


async def test_negative_extra(mocked_curl):
    mocked_curl.side_effect = [
        mock.Mock(stdout=b"1\n"),
        mock.Mock(stdout=b"1.1\n"),
        mock.Mock(stdout=b"2\n"),
        mock.Mock(stdout=b"3\n"),
    ]

    status, data = await run("http://server.local", versions=["1", "1.1", "2"])

    assert status is False
    assert data == "HTTP version(s) 3 unexpectedly supported"
