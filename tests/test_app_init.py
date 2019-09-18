from unittest import mock

import pytest

from poucave.main import init_app


async def test_sentry_setup(cli):
    with mock.patch("poucave.main.utils.Cache.get", side_effect=ValueError):
        with mock.patch("sentry_sdk.hub.Hub.capture_event") as mocked:
            resp = await cli.get("/checks/testproject/hb")
            await resp.text()
    assert resp.status == 500
    assert len(mocked.call_args_list) > 0


async def test_json_errors(cli):
    with mock.patch("poucave.main.utils.Cache.get", side_effect=ValueError("boom")):
        resp = await cli.get("/checks/testproject/hb")
        body = await resp.json()
    assert not body["success"]
    assert body["data"] == "boom"


async def test_404_errors(cli):
    resp = await cli.get("/unknown")
    assert resp.status == 404
    assert "text/plain" in resp.headers["Content-Type"]


def test_invalid_configuration_parameter():
    with pytest.raises(ValueError):
        init_app(
            {
                "checks": {
                    "remotesettings": {
                        "hb": {
                            "module": "checks.core.heartbeat",
                            "description": "",
                            "params": {"unknown": 42},
                        }
                    }
                }
            }
        )
