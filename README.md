# Poucave

*Poucave* (*pronuncation*: /pu.kav/, french slang for «snitch») is a small Web app that will act as a proxy between a monitoring service like Pingdom and a series of domain specific checks for your infrastructure.


## Usage

Every check defined in your configuration file is exposed as an endpoint that returns `200` if successful or `5XX` otherwise:

```json
GET /checks/{a-project}/{a-name}

HTTP/1.1 200 OK
Content-Length: 260
Content-Type: application/json; charset=utf-8
Date: Fri, 16 Aug 2019 13:29:55 GMT
Server: Python/3.7 aiohttp/3.5.4

{
    "name": "a-name",
    "project": "a-project",
    "module": "checks.core.heartbeat",
    "documentation": "URL should return a 200 response.",
    "description": "Some check description.",
    "data": {
        "ok": true
    }
}

```

The response has some additional `"data"`, specific to each type of check.


## Configure

The checks are defined in a `config.toml` file:

```toml
[checks.remotesettings.public-heartbeat]
description = "Heartbeat of the public read-only instance."
module = "checks.core.heartbeat"
ttl = 60
params.url = "https://firefox.settings.services.mozilla.com/v1/__heartbeat__"

[checks.normandy.published-recipes]
description = "Normandy over Remote Settings."
module = "checks.normandy.remotesettings_recipes"
ttl = 3600
params.normandy_server = "https://normandy.cdn.mozilla.net"
params.remotesettings_server = "https://firefox.settings.services.mozilla.com/v1"

```

* `description`: Some details about this check
* `ttl`: Cache the check result for a number of seconds
* `module`: Path to Python module
* `params`: Parameters specific to the check

### Environment variables

The config file values can refer to environment variables (eg. secrets) using the ``${}`` syntax.

```toml
[checks.myproject.mycheck]
module = "checks.remotesettings.collections_consistency"
params.url = "http://${ENV_NAME}.service.org"
params.auth = "Bearer ${AUTH}"
```

### Server configuration

Server configuration is done via environment variables:

* ``CONFIG_FILE``: Path to configuration file (default: ``"config.toml"``)
* ``CORS_ORIGIN``: Allowed requests origins (default: ``*``)
* ``HOST``: Bind to host (default: ``"localhost"``)
* ``PORT``: Listen on port (default: ``8080``)
* ``DEFAULT_TTL``: Default TTL for endpoints in seconds (default: ``60``)
* ``LOG_LEVEL``: One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL`` (default: ``INFO``)
* ``LOG_FORMAT``: Set to ``text`` for human-readable logs (default: ``json``)
* ``VERSION_FILE``: Path to version JSON file (default: ``"version.json"``)
* ``SENTRY_DSN``: Report errors to the specified Sentry ``"https://<key>@sentry.io/<project>"`` (default: disabled)


## Run Web server

Using Docker, and a local config file:

```
docker run -p 8000:8000 -v `pwd`/config.toml:/app/config.toml leplatrem/poucave
```

Or from source:

```
make serve
```

## CLI

Using Docker, and a local config file:

```
docker run -v `pwd`/config.toml:/app/config.toml leplatrem/poucave check myproject mycheck
```

Or from source:

```
make check project=myproject check=mycheck
```

## Tests

```
make tests
```

## License

*Poucave* is licensed under the MPLv2. See the `LICENSE` file for details.
