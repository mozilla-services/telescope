import os
from poucave import config


HERE = os.path.dirname(os.path.abspath(__file__))


def test_env_vars_are_expanded_in_values():
    config_file = os.path.join(HERE, "config.toml")
    os.environ["ENV_NAME"] = "dev"

    conf = config.load(config_file)

    assert (
        conf["checks"]["testproject"]["env"]["params"]["url"]
        == "http://dev.service.org"
    )
