from checks.core.heartbeat import run


async def test_positive(mock_aioresponse):
    url = "http://server.local/__heartbeat__"
    mock_aioresponse.get(url, status=200, payload={})

    status, data = await run(url)

    assert status is True
    assert data == {}


async def test_negative(mock_aioresponse):
    url = "http://server.local/__heartbeat__"
    mock_aioresponse.get(url, status=403, payload={})

    status, data = await run(url)

    assert status is False
    assert data == {}


async def test_unreachable(mock_aioresponse):
    status, data = await run("http://not-mocked")

    assert status is False
    assert data == "Connection refused: GET http://not-mocked"
