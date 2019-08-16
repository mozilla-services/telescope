async def test_hello(cli):
    response = await cli.get("/")
    assert response.status == 200
    body = await response.json()
    assert body["hello"] == "poucave"


async def test_check_positive(cli, mock_aioresponse):
    mock_aioresponse.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200
    body = await response.json()
    assert body["project"] == "testproject"
    assert body["name"] == "hb"
    assert body["description"] == "Test HB"
    assert "URL should return" in body["documentation"]
    assert body["data"] == {"ok": True}


async def test_check_negative(cli, mock_aioresponse):
    mock_aioresponse.get("http://server.local/__heartbeat__", status=503)

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 503
    body = await response.json()
    assert body["data"] is None


async def test_check_cached(cli, mock_aioresponse):
    mock_aioresponse.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    await cli.get("/checks/testproject/hb")

    mock_aioresponse.clear()

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200
