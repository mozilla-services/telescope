import re
from unittest import mock

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


# /checks


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
            "tags": ["ops", "test"],
            "ttl": 60,
            "parameters": {"url": "http://server.local/__heartbeat__"},
        }
    ]


# /checks/{project}


async def test_project_unknown(cli):
    response = await cli.get("/checks/unknown")
    assert response.status == 404


async def test_project_returns_only_cached(mock_aioresponses, cli):
    mock_aioresponses.get("http://server.local/__heartbeat__", status=200, payload={})

    await cli.get("/checks/testproject/fake")

    response = await cli.get("/checks/testproject")
    assert response.status == 200
    body = await response.json()

    assert body[0]["project"] == "testproject"
    assert body[0]["name"] == "hb"
    assert body[0]["success"]

    assert body[1]["name"] == "fake"
    assert body[1]["success"]
    assert body[1]["data"] == {"max_age": 999, "from_conf": 100}


# /tags/{tag}


async def test_check_tag_unknown(cli):
    response = await cli.get("/tags/foo")
    assert response.status == 404


async def test_check_by_tag(cli, mock_aioresponses):
    mock_aioresponses.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )
    response = await cli.get("/tags/ops")
    assert response.status == 200


# /checks/{project}/{name}


async def test_check_unknown(cli):
    response = await cli.get("/checks/testproject/unknown")
    assert response.status == 404


async def test_check_run_queryparams(cli):
    response = await cli.get("/checks/testproject/fake")
    body = await response.json()
    assert body["parameters"]["max_age"] == 999
    assert body["data"] == {"max_age": 999, "from_conf": 100}


async def test_check_run_queryparams_overriden(cli):
    response = await cli.get("/checks/testproject/fake?max_age=42")
    body = await response.json()
    assert body["parameters"]["max_age"] == 42
    assert body["data"] == {"max_age": 42, "from_conf": 100}


async def test_check_run_bad_value(cli):
    response = await cli.get("/checks/testproject/fake?max_age=abc")
    assert response.status == 400


async def test_check_positive(cli, mock_aioresponses):
    mock_aioresponses.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200
    body = await response.json()
    assert re.compile("....-..-..T..:..:..\\.......+..:..").match(body["datetime"])
    assert body["duration"] > 0
    assert body["success"]
    assert body["project"] == "testproject"
    assert body["name"] == "hb"
    assert body["description"] == "Test HB"
    assert "URL should return" in body["documentation"]
    assert body["data"] == {"ok": True}


async def test_check_negative(cli, mock_aioresponses):
    mock_aioresponses.get("http://server.local/__heartbeat__", status=503)

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 503
    body = await response.json()
    assert not body["success"]
    assert body["data"] is None


async def test_check_cached(cli, mock_aioresponses):
    mock_aioresponses.get(
        "http://server.local/__heartbeat__", status=200, payload={"ok": True}
    )

    await cli.get("/checks/testproject/hb")

    mock_aioresponses.clear()

    response = await cli.get("/checks/testproject/hb")

    assert response.status == 200


async def test_check_cached_by_queryparam(cli, mock_aioresponses):
    resp = await cli.get("/checks/testproject/fake")
    dt_no_params = (await resp.json())["datetime"]

    resp = await cli.get("/checks/testproject/fake?unknown=1")
    dt_unknown = (await resp.json())["datetime"]
    assert dt_no_params == dt_unknown

    resp = await cli.get("/checks/testproject/fake?max_age=2")
    dt_known = (await resp.json())["datetime"]
    resp = await cli.get("/checks/testproject/fake?max_age=2")
    dt_known_same = (await resp.json())["datetime"]
    assert dt_known == dt_known_same

    resp = await cli.get("/checks/testproject/fake?max_age=3")
    dt_different = (await resp.json())["datetime"]
    assert dt_known != dt_different


async def test_cors_enabled(cli):
    response = await cli.get("/", headers={"Origin": "http://example.org"})

    assert "Access-Control-Allow-Origin" in response.headers


async def test_sentry_event_on_negative(cli, mock_aioresponses):
    mock_aioresponses.get("http://server.local/__heartbeat__", status=503)

    with mock.patch("sentry_sdk.hub.Hub.capture_message") as mocked:
        await cli.get("/checks/testproject/hb")

    assert mocked.call_args_list[0][0][0] == "testproject/hb is failing"
