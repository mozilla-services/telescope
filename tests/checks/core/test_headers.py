from checks.core.headers import run


async def test_positive(mock_aioresponses):
    url = "http://server.local"
    mock_aioresponses.head(url, status=200, headers={"Content-Encoding": "gzip"})

    status, data = await run(
        [url],
        request_headers={},
        response_headers={
            "Content-Encoding": "",
        },
    )

    assert status is True
    assert data == {}


async def test_positive_empty(mock_aioresponses):
    url = "http://server.local"
    mock_aioresponses.head(url, status=200, headers={"Content-Encoding": "gzip"})

    status, data = await run(
        [url],
        request_headers={},
        response_headers={
            "Content-Encoding": "",
        },
    )

    assert status is True
    assert data == {}


async def test_negative_missing(mock_aioresponses):
    url = "http://server.local"
    mock_aioresponses.head(url, status=200, headers={})

    status, data = await run(
        [url],
        request_headers={},
        response_headers={
            "Content-Encoding": "",
        },
    )

    assert status is False
    assert data == {url: {"missing": {"Content-Encoding": ""}}}


async def test_negative_different(mock_aioresponses):
    url = "http://server.local"
    mock_aioresponses.head(
        url,
        status=200,
        headers={
            "Content-Type": "application/json",
        },
    )

    status, data = await run(
        [url],
        request_headers={},
        response_headers={
            "Content-Encoding": "application/wasm",
        },
    )

    assert status is False
    assert data == {
        url: {
            "missing": {"Content-Encoding": "application/wasm"},
        }
    }
