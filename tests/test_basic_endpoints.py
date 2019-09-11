from poucave import config


async def test_hello(cli):
    response = await cli.get("/")
    assert response.status == 200
    body = await response.json()
    assert body["hello"] == "poucave"


async def test_lbheartbeat(cli):
    response = await cli.get("/__lbheartbeat__")
    assert response.status == 200


async def test_heartbeat(cli):
    response = await cli.get("/__heartbeat__")
    assert response.status == 200


async def test_version(cli):
    response = await cli.get("/__version__")
    assert response.status == 200
    body = await response.json()
    assert body["name"] == "poucave"

    # Raises if file is missing
    config.VERSION_FILE = "missing.json"
    response = await cli.get("/__version__")
    assert response.status == 500


async def test_checks(cli):
    response = await cli.get("/checks")
    assert response.status == 200
    body = await response.json()
    assert len(body) >= 1
    assert body[:1] == [
        {
            "name": "hb",
            "project": "testproject",
            "module": "checks.core.heartbeat",
            "description": "Test HB",
            "documentation": "URL should return a 200 response.\n\nThe remote response is returned.",
            "url": "/checks/testproject/hb",
            "parameters": {},
        }
    ]


async def test_check_positive(cli, mock_aioresponse):
    mock_aioresponse.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200
    body = await response.json()
    assert "datetime" in body
    assert body["success"]
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
    assert not body["success"]
    assert body["data"] is None


async def test_check_cached(cli, mock_aioresponse):
    mock_aioresponse.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    await cli.get("/checks/testproject/hb")

    mock_aioresponse.clear()

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200


async def test_cors_enabled(cli):
    response = await cli.get("/", headers={"Origin": "http://example.org"})

    assert "Access-Control-Allow-Origin" in response.headers
