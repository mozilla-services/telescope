import sys
from unittest import mock

from poucave.main import main, run_check


def test_run_check_cli(test_config_toml):
    sys_argv = ["poucave", "testproject", "hb"]
    with mock.patch.object(sys, "argv", sys_argv):
        with mock.patch("poucave.main.run_check") as mocked:
            # import side-effect of __main__
            from poucave import __main__  # noqa
    assert mocked.called


def test_run_cli_unknown(test_config_toml):
    result = main(["project", "unknown"])
    assert result == 2


def test_run_web(test_config_toml):
    with mock.patch("poucave.main.web.run_app") as mocked:
        main([])
    assert mocked.called


def test_run_check(mock_aioresponse):
    url = "http://server.local/__heartbeat__"
    mock_aioresponse.get(url, status=200, payload={"ok": True})

    assert run_check(
        {
            "project": "a-project",
            "name": "a-name",
            "module": "checks.core.heartbeat",
            "params": {"url": url},
        }
    )
