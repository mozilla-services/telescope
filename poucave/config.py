import os

import toml


def load():
    configfile = os.getenv("CONFIG_FILE", "config.toml")
    return toml.load(open(configfile, "r"))
