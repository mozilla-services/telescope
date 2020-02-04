# Poucave

[![Dependabot Status](https://api.dependabot.com/badges/status?host=github&repo=mozilla-services/poucave)](https://dependabot.com) [![CircleCI](https://circleci.com/gh/mozilla-services/poucave.svg?style=svg)](https://circleci.com/gh/mozilla-services/poucave)

*Poucave* (*pronuncation*: /pu.kav/, french slang for «snitch») is a small Web app that will act as a proxy between a monitoring service like Pingdom and a series of domain specific checks for your infrastructure.


## Usage

Every check defined in your configuration file is exposed as an endpoint that returns `200` if successful or `5XX` otherwise:

```http
GET /checks/{a-project}/{a-check}

HTTP/1.1 200 OK
Content-Length: 260
Content-Type: application/json; charset=utf-8
Date: Fri, 16 Aug 2019 13:29:55 GMT
Server: Python/3.7 aiohttp/3.5.4

{
    "name": "a-check",
    "project": "a-project",
    "url": "/checks/a-project/a-check",
    "module": "checks.core.heartbeat",
    "documentation": "URL should return a 200 response.",
    "description": "Some check description.",
    "success": true,
    "parameters": {},
    "data": {
        "ok": true
    }
}

```

The response has some additional `"data"`, specific to each type of check.

Cache can be forced to be refreshed with the ``?refresh={s3cr3t}`` querystring. See *Environment variables* section.

### Other endpoints:

* ``/checks``: list all checks, without executing them.
* ``/checks/{a-project}``: execute all checks of project ``a-project``
* ``/checks/tags/{a-tag}``: execute all checks with tag ``a-tag``

Output format:

* ``Accept: plain/text``: renders the check(s) as a human readable table.


## Configure

The checks are defined in a `config.toml` file, and their module available in current `PYTHONPATH`:

```toml
[checks.a-project.a-check]
description = "Heartbeat of the public read-only instance."
module = "checks.core.heartbeat"
params.url = "https://firefox.settings.services.mozilla.com/v1/__heartbeat__"

[checks.normandy.published-recipes]
description = "Normandy over Remote Settings."
module = "checks.normandy.remotesettings_recipes"
params.normandy_server = "https://normandy.cdn.mozilla.net"
params.remotesettings_server = "https://firefox.settings.services.mozilla.com/v1"
ttl = 3600
tags = ["critical"]
```

* `description`: Some details about this check
* `module`: Path to Python module
* `params`: (*optional*) Parameters specific to the check
* `ttl`: (*optional*) Cache the check result for a number of seconds
* `tags`: (*optional*) List of strings allowing grouping of checks at `/tags/{tag}`


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
* ``DEFAULT_REQUEST_HEADERS``: Default headers sent in every HTTP requests, as JSON dict format (example: ``{"Allow-Access": "CDN"}``, default: ``{}``)
* ``LOG_LEVEL``: One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL`` (default: ``INFO``)
* ``LOG_FORMAT``: Set to ``text`` for human-readable logs (default: ``json``)
* ``VERSION_FILE``: Path to version JSON file (default: ``"version.json"``)
* ``REFRESH_SECRET``: Secret to allow forcing cache refresh via querystring (default: ``""``)
* ``REQUESTS_TIMEOUT_SECONDS``: Timeout in seconds for HTTP requests (default: ``5``)
* ``REQUESTS_MAX_RETRIES``: Number of retries for HTTP requests (default: ``4``)
* ``SENTRY_DSN``: Report errors to the specified Sentry ``"https://<key>@sentry.io/<project>"`` (default: disabled)


## Run Web server

Using Docker, and a local config file:

```
docker run -p 8000:8000 -v `pwd`/config.toml:/app/config.toml mozilla/poucave
```

Or from source:

```
make serve
```

## Web UI

A minimalist Web page is accessible at ``/html/index.html`` and shows every check status,
along with the returned data and documentation.


## CLI

Using Docker, and a local config file:

```
docker run -v `pwd`/config.toml:/app/config.toml mozilla/poucave check myproject

docker run -v `pwd`/config.toml:/app/config.toml mozilla/poucave check myproject mycheck
```

Or from source:

```
make check project=myproject

make check project=myproject check=mycheck
```

## Tests

```
make tests
```

# Tips

## Showing status of a group of checks

```
$ curl -s https://poucave.host/checks/tags/my-tag | jq -r  '.[] | "\(.project) \(.name) \(.success)"' | column -t

projectA    heartbeat    true
projectB    some-check   false
projectC    heartbeat    true
...
```

## License

*Poucave* is licensed under the MPLv2. See the `LICENSE` file for details.
