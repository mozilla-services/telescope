from checks.core.heartbeat import run


async def test_positive(mock_aioresponses):
    url = "http://server.local/__heartbeat__"
    mock_aioresponses.get(url, status=200, payload={})

    status, data = await run(url)

    assert status is True
    assert data == {}


async def test_negative(mock_aioresponses):
    url = "http://server.local/__heartbeat__"
    mock_aioresponses.get(url, status=403, payload={})

    status, data = await run(url)

    assert status is False
    assert data == {}


async def test_unreachable(mock_aioresponses, config):
    config.REQUESTS_MAX_RETRIES = 0
    status, data = await run("http://not-mocked")

    assert status is False
    assert data == "Connection refused: GET http://not-mocked"


async def test_xml_response(mock_aioresponses):
    url = "http://some.cdn/chains/"
    some_xml = '<?xml version="1.0"?>\n<Error><Code>AccessDenied</Code></Error>'
    mock_aioresponses.get(
        url, status=403, body=some_xml, content_type="application/xml"
    )

    status, data = await run(url, expected_status=403)

    assert data == some_xml
    assert status is True
