import pytest

from checks.core.cloudfront_age import run


async def test_positive(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(
        url, status=200, headers={"Age": "23", "X-Cache": "Hit from cloudfront"}
    )

    status, data = await run(url, max_age=30)

    assert status is True
    assert data == 23


async def test_negative(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(
        url, status=200, headers={"Age": "33", "X-Cache": "Hit from cloudfront"}
    )

    status, data = await run(url, max_age=30)

    assert status is False
    assert data == 33


async def test_positive_fresh_hit(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(url, status=200, headers={"X-Cache": "Hit from cloudfront"})

    status, data = await run(url, max_age=30)

    assert status is True
    assert data == 0


async def test_positive_miss(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(url, status=200, headers={"X-Cache": "Miss from cloudfront"})

    status, data = await run(url, max_age=30)

    assert status is True
    assert data == 0


async def test_missing_headers(mock_aioresponses):
    url = "http://cdn.server/foo"
    mock_aioresponses.head(url, status=200)

    with pytest.raises(ValueError):
        await run(url, max_age=30)
