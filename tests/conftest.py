import os

import pytest
import responses
from aioresponses import aioresponses


from poucave.main import init_app


HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
async def cli(loop, test_client):
    config_file = os.path.join(HERE, "config.toml")
    os.environ["CONFIG_FILE"] = config_file

    app = init_app([])
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
