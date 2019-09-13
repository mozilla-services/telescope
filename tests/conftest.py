import os

import pytest
import responses
from aioresponses import aioresponses


from poucave import config
from poucave.main import init_app


HERE = os.path.dirname(os.path.abspath(__file__))


EXPOSED_PARAMETERS = ["max_age"]
URL_PARAMETERS = ["max_age"]


async def run(max_age: int, from_conf: int):
    """
    Fake check that returns the input parameters.
    Used for testing, from `tests/config.toml`.
    """
    return True, dict(max_age=max_age, from_conf=from_conf)


@pytest.fixture
async def cli(test_client):
    config_file = os.path.join(HERE, "config.toml")
    conf = config.load(config_file)
    app = init_app(conf)
    return await test_client(app)


@pytest.fixture
def mock_aioresponse(cli):
    test_server = f"http://{cli.host}:{cli.port}"
    with aioresponses(passthrough=[test_server]) as m:
        yield m


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps
