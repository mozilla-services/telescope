import os
import re
from typing import List, Union
from urllib.parse import urlsplit, urlunsplit

import pytest
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
        original_add = m.add

        def new_add(url, *args, **kwargs):
            # Leave non-string URLs (e.g. regex) untouched
            if isinstance(url, str):
                scheme, netloc, path, query, _ = urlsplit(url)
                if not query:
                    base_url = urlunsplit((scheme, netloc, path, "", ""))
                    # ^base(?:\?.*)?$  → base, optionally followed by ?...
                    url = re.compile(re.escape(base_url) + r"(?:\?.*)?$")
            return original_add(url, *args, **kwargs)

        m.add = new_add
        yield m
        m.add = original_add  # restore original method to avoid side-effects


@pytest.fixture
async def no_sleep(monkeypatch):
    async def caffeine(*args, **kwargs):
        return None

    monkeypatch.setattr("asyncio.sleep", caffeine)  # speed up tests
