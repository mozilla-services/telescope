from unittest import mock

import pytest

from telescope.app import Checks, init_app


async def test_sentry_setup(cli):
    with mock.patch("telescope.app.utils.InMemoryCache.get", side_effect=ValueError):
        with mock.patch("sentry_sdk.capture_event") as mocked:
            resp = await cli.get("/checks/testproject/hb")
            await resp.text()
    assert resp.status == 500
    mocked.assert_called()


async def test_json_errors(cli):
    with mock.patch(
        "telescope.app.utils.InMemoryCache.get", side_effect=ValueError("boom")
    ):
        resp = await cli.get("/checks/testproject/hb")
        body = await resp.json()
    assert not body["success"]
    assert body["data"] == "ValueError('boom')"


async def test_404_errors(cli):
    resp = await cli.get("/unknown")
    assert resp.status == 404
    assert "text/plain" in resp.headers["Content-Type"]


async def test_app_init_advanced_parameters():
    init_app(
        Checks.from_conf(
            {
                "checks": {
                    "test": {
                        "test": {
                            "module": "tests.conftest",
                            "description": "",
                            "params": {"from_conf": 0, "max_age": 0, "extras": ["a"]},
                        }
                    }
                }
            }
        )
    )


def test_unknown_configuration_parameter():
    with pytest.raises(ValueError):
        init_app(
            Checks.from_conf(
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
        )
