import os

import toml


HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", 8000))
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.toml")
DEFAULT_TTL = int(os.getenv("DEFAULT_TTL", 60))
VERSION_FILE = os.getenv("VERSION_FILE", "version.json")


def load(configfile):
    return toml.load(open(configfile, "r"))
