import os

import toml


HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", 8080))
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.toml")
DEFAULT_TTL = int(os.getenv("DEFAULT_TTL", 60))


def load(configfile):
    return toml.load(open(configfile, "r"))
