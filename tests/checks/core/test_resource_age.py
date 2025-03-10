from datetime import datetime, timezone
from unittest import mock

from checks.core.resource_age import run


async def test_positive(mock_aioresponses):
    url = "http://cdn.server/foo"
    may8_http = "Mon, 08 May 1982 00:01:01 GMT"
    fake_now = datetime(1982, 5, 8, 10, 0, 0).replace(tzinfo=timezone.utc)
    mock_aioresponses.head(
        url,
        headers={"Last-Modified": may8_http},
    )

    with mock.patch("checks.core.resource_age.utcnow", return_value=fake_now):
        status, data = await run(url, max_age_hours=10)

    assert data == {"age_hours": 9}
    assert status is True


async def test_negative(mock_aioresponses):
    url = "http://cdn.server/foo"
    may8_http = "Mon, 08 May 1982 00:01:01 GMT"
    fake_now = datetime(1982, 5, 8, 11, 0, 0).replace(tzinfo=timezone.utc)
    mock_aioresponses.head(
        url,
        headers={"Last-Modified": may8_http},
    )

    with mock.patch("checks.core.resource_age.utcnow", return_value=fake_now):
        status, data = await run(url, max_age_hours=10)

    assert data == {"age_hours": 10}
    assert status is False


async def test_negative_missing(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(url)

    status, _ = await run(url, max_age_hours=10)

    assert status is False


async def test_negative_bad_format(mock_aioresponses):
    url = "http://cdn.server/foo"
    bad_format = "00:00:00 GMT"
    mock_aioresponses.head(
        url,
        headers={"Last-Modified": bad_format},
    )

    status, data = await run(url, max_age_hours=10)

    assert data == {"error": "Invalid Last-Modified header: '00:00:00 GMT'"}
    assert status is False
