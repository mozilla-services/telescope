import os
import sys

import toml


HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", 8000))
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.toml")
DEFAULT_TTL = int(os.getenv("DEFAULT_TTL", 60))
VERSION_FILE = os.getenv("VERSION_FILE", "version.json")
LOGGING = {
    "version": 1,
    "formatters": {
        "json": {"()": "dockerflow.logging.JsonLogFormatter", "logger_name": "poucave"}
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": sys.stdout,
        }
    },
    "loggers": {
        "poucave": {"handlers": ["console"], "level": "DEBUG"},
        "request.summary": {"handlers": ["console"], "level": "INFO"},
    },
}


def load(configfile):
    return toml.load(open(configfile, "r"))
