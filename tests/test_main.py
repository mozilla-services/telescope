import asyncio
import sys
from unittest import mock

from telescope.app import Check, background_tasks, main, run_check


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
        loop=asyncio.get_event_loop(),
        check=Check(
            project="a-project",
            name="a-name",
            description="My heartbeat",
            module="checks.core.heartbeat",
            params={"url": url},
        ),
        cache=None,
        events=None,
        force=False,
    )


def test_run_failing_check(mock_aioresponses):
    url = "http://server.local/__heartbeat__"
    mock_aioresponses.get(url, exception=RuntimeError("Weird error"))

    assert (
        run_check(
            loop=asyncio.get_event_loop(),
            check=Check(
                project="a-project",
                name="a-name",
                description="My heartbeat",
                module="checks.core.heartbeat",
                params={"url": url},
            ),
            cache=None,
            events=None,
            force=False,
        )
        is False
    )


async def test_observe_event_loop(cli, config):
    config.EVENT_LOOP_OBSERVE_INTERVAL_SECONDS = 0.05
    pending_tasks_metric = cli.app["telescope.metrics"]["event_loop_pending_tasks"]
    assert pending_tasks_metric.labels("main")._value.get() == 0

    gen = background_tasks(cli.app)
    # Start the background tasks (until first yield)
    await gen.asend(None)
    # Let some time for the observe_event_loop to run a few times.
    await asyncio.sleep(0.2)
    # Stop the background tasks.
    try:
        await gen.asend(None)
    except StopAsyncIteration:
        pass
    assert pending_tasks_metric.labels("main")._value.get() >= 0
