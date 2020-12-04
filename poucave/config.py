import json
import re
import sys

import toml
from decouple import config


# Since we run the app in a container, binding to all interfaces is fine.
HOST = config("HOST", default="0.0.0.0")  # nosec
PORT = config("PORT", default=8000, cast=int)
SERVICE_NAME = config("SERVICE_NAME", default="poucave")
BUGTRACKER_URL = config("BUGTRACKER_URL", default="https://bugzilla.mozilla.org")
BUGTRACKER_API_KEY = config("BUGTRACKER_API_KEY", default="")
BUGTRACKER_TTL = config("BUGTRACKER_TTL", default=3600, cast=int)
CONFIG_FILE = config("CONFIG_FILE", default="config.toml")
DIAGRAM_FILE = config("DIAGRAM_FILE", default="diagram.svg")
CORS_ORIGINS = config("CORS_ORIGINS", default="*")
DEFAULT_TTL = config("DEFAULT_TTL", default=60, cast=int)
DEFAULT_REQUEST_HEADERS = config(
    "DEFAULT_REQUEST_HEADERS", default="{}", cast=lambda v: json.loads(v)
)
ENV_NAME = config("ENV_NAME", default=None)
HISTORY_DAYS = config("HISTORY_DAYS", default=0)
HISTORY_TTL = config("HISTORY_TTL", default=3600, cast=int)
REFRESH_SECRET = config("REFRESH_SECRET", default="")
REQUESTS_TIMEOUT_SECONDS = config("REQUESTS_TIMEOUT_SECONDS", default=5, cast=int)
REQUESTS_MAX_RETRIES = config("REQUESTS_MAX_RETRIES", default=2, cast=int)
REQUESTS_MAX_PARALLEL = config("REQUESTS_MAX_PARALLEL", default=16, cast=int)
SENTRY_DSN = config("SENTRY_DSN", default="")
TROUBLESHOOTING_LINK_TEMPLATE = config(
    "TROUBLESHOOTING_LINK_TEMPLATE",
    default=(
        "https://mana.mozilla.org/wiki/pages/viewpage.action?pageId=126619112"
        "#TroubleshootingRemoteSettings&Normandy-{project}/{check}"
    ),
)
VERSION_FILE = config("VERSION_FILE", default="version.json")
LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
LOG_FORMAT = config("LOG_FORMAT", default="json")
LOGGING = {
    "version": 1,
    "formatters": {
        "text": {"()": "logging_color_formatter.ColorFormatter"},
        "json": {"()": "dockerflow.logging.JsonLogFormatter", "logger_name": "poucave"},
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "stream": sys.stdout,
        }
    },
    "loggers": {
        "poucave": {"handlers": ["console"], "level": "DEBUG"},
        "checks": {"handlers": ["console"], "level": "DEBUG"},
        "backoff": {"handlers": ["console"], "level": "DEBUG"},
        "kinto_http": {"handlers": ["console"], "level": "DEBUG"},
        "request.summary": {"handlers": ["console"], "level": "INFO"},
        "check.result": {"handlers": ["console"], "level": "INFO"},
    },
}


def interpolate_env(d):
    new = {}
    for k, v in d.items():
        if isinstance(v, str):
            search = re.search("\\$\\{(.+)\\}", v)
            if search:
                for g in search.groups():
                    v = v.replace(f"${{{g}}}", config(g, ""))
            new[k] = v
        elif isinstance(v, dict):
            new[k] = interpolate_env(v)
        else:
            new[k] = v
    return new


def load(configfile):
    conf = toml.load(open(configfile, "r"))
    conf = interpolate_env(conf)
    return conf
