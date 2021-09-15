import sys
from unittest import mock

from telescope.app import Check, main, run_check


async def test_run_check_cli(test_config_toml):
    sys_argv = ["telescope", "check", "testproject", "hb"]
    with mock.patch.object(sys, "argv", sys_argv):
        with mock.patch("telescope.app.run_check") as mocked:
            # import side-effect of __main__
            from telescope import __main__  # noqa
    assert mocked.called


async def test_run_check_cli_by_project(test_config_toml):
    with mock.patch("telescope.app.run_check") as mocked:
        main(["check", "testproject"])
    assert mocked.call_count == 2  # See tests/config.toml


async def test_run_cli_unknown(test_config_toml):
    result = main(["check", "testproject", "unknown"])
    assert result == 2
    result = main(["check", "unknown", "hb"])
    assert result == 2


async def test_run_web(test_config_toml):
    with mock.patch("telescope.app.web.run_app") as mocked:
        main([])
    assert mocked.called


def test_run_check(mock_aioresponses):
    url = "http://server.local/__heartbeat__"
    mock_aioresponses.get(url, status=200, payload={"ok": True})

    assert run_check(
        Check(
            project="a-project",
            name="a-name",
            description="My heartbeat",
            module="checks.core.heartbeat",
            params={"url": url},
        )
    )
