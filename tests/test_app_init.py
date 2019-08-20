from unittest import mock

import pytest

from poucave import main


async def test_sentry_setup(cli):
    with mock.patch("poucave.main.utils.Cache.get", side_effect=ValueError):
        with mock.patch("sentry_sdk.hub.Hub.capture_event") as mocked:
            resp = await cli.get("/checks/testproject/hb")
            await resp.text()
    assert resp.status == 500
    assert len(mocked.call_args_list) > 0
