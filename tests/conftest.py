import os
from typing import List, Union
from unittest import mock

import pytest
import responses
from aioresponses import aioresponses

from telescope import config as global_config
from telescope.app import Checks, init_app


HERE = os.path.dirname(os.path.abspath(__file__))


EXPOSED_PARAMETERS = ["max_age"]
URL_PARAMETERS = ["max_age"]


async def run(max_age: Union[int, float], from_conf: int, extras: List = []):
    """
    Fake check that returns the input parameters.
    Used for testing, from `tests/config.toml`.
    """
    return True, dict(max_age=max_age, from_conf=from_conf)


@pytest.fixture
def test_config_toml():
    config_file = os.path.join(HERE, "config.toml")
    backup = global_config.CONFIG_FILE
    global_config.CONFIG_FILE = config_file
    yield config_file
    global_config.CONFIG_FILE = backup


@pytest.fixture
async def cli(config, aiohttp_client, test_config_toml):
    config.BUGTRACKER_URL = None
    conf = global_config.load(test_config_toml)
    checks = Checks.from_conf(conf)
    app = init_app(checks)
    return await aiohttp_client(app)


@pytest.fixture
async def config():
    fields = dir(global_config)
    backup = {f: getattr(global_config, f) for f in fields}
    yield global_config
    for f in fields:
        setattr(global_config, f, backup[f])


@pytest.fixture
def mock_aioresponses(cli):
    test_server = f"http://{cli.host}:{cli.port}"
    with aioresponses(passthrough=[test_server]) as m:
        yield m


@pytest.fixture
def mock_bigquery_client():
    with mock.patch("telescope.utils.bigquery.Client") as mocked:
        yield mocked


class ResponsesWrapper:
    """A tiny wrapper to mimic the aioresponses API."""

    def __init__(self, rsps):
        self.rsps = rsps

    def get(self, *args, **kwargs):
        kwargs["json"] = kwargs.pop("payload", None)
        return self.rsps.add(responses.GET, *args, **kwargs)

    def head(self, *args, **kwargs):
        return self.rsps.add(responses.HEAD, *args, **kwargs)

    @property
    def calls(self):
        return self.rsps.calls


@pytest.fixture
def mock_responses():
    with responses.RequestsMock() as rsps:
        yield ResponsesWrapper(rsps)
