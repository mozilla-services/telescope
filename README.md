# Telescope

[![CircleCI](https://circleci.com/gh/mozilla-services/telescope.svg?style=svg)](https://circleci.com/gh/mozilla-services/telescope)

*Telescope* is a small Web app that will act as a proxy between a monitoring service — like Pingdom or [Upptime](https://upptime.js.org/) — and a series of domain specific checks for your infrastructure.


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

* Request header ``Accept: plain/text``: renders the check(s) as a human readable table.


## Configure

The checks are defined in a `config.toml` file, and their module must be available in the current `PYTHONPATH`:

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
* ``CONTACT_EMAIL``: Contact email for this instance (default: ``postmaster@localhost``)
* ``DIAGRAM_FILE``: Path to SVG diagram file (default: ``"diagram.svg"``)
* ``CORS_ORIGIN``: Allowed requests origins (default: ``*``)
* ``ENV_NAME``: A string to identify the current environment name like ``"prod"`` or ``"stage"`` (default: None)
* ``HOST``: Bind to host (default: ``"localhost"``)
* ``PORT``: Listen on port (default: ``8000``)
* ``DEFAULT_TTL``: Default TTL for endpoints in seconds (default: ``60``)
* ``DEFAULT_REQUEST_HEADERS``: Default headers sent in every HTTP requests, as JSON dict format (example: ``{"Allow-Access": "CDN"}``, default: ``{}``)
* ``LOG_LEVEL``: One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL`` (default: ``INFO``)
* ``LOG_FORMAT``: Set to ``text`` for human-readable logs (default: ``json``)
* ``VERSION_FILE``: Path to version JSON file (default: ``"version.json"``)
* ``REFRESH_SECRET``: Secret to allow forcing cache refresh via querystring (default: ``""``)
* ``REQUESTS_TIMEOUT_SECONDS``: Timeout in seconds for HTTP requests (default: ``5``)
* ``REQUESTS_MAX_RETRIES``: Number of retries for HTTP requests (default: ``4``)
* ``SENTRY_DSN``: Report errors to the specified Sentry ``"https://<key>@sentry.io/<project>"`` (default: disabled)
* ``SERVICE_NAME``: Name of the running service, used to link known issues in bug tracker (default: ``telescope``)
* ``SERVICE_TITLE``: Title shown in the UI (default: capitalized service name)

* ``BUGTRACKER_URL``: Bug tracker URL. Set to empty string to disable. (default: ``https://bugzilla.mozilla.org``)
* ``BUGTRACKER_API_KEY``: Bug tracker API key to fetch non-public bugs (default: none)
* ``BUGTRACKER_TTL``: Default TTL for endpoints in seconds (default: ``3600``)

* ``HISTORY_DAYS``: Number of days to cover whening fetch history of checks (default: 0, disabled)
* ``HISTORY_TTL``: Default TTL for history refresh in seconds (default: ``3600``)

* ``GITHUB_TOKEN``: Github [Personal Access Token value](https://github.com/settings/tokens) to avoid rate-limiting (default: disabled)
* ``GOOGLE_APPLICATION_CREDENTIALS``: Absolute path to credentials file for BigQuery authentication (eg. `` `pwd`/key.json``, default: disabled)

Configuration can be stored in a ``.env`` file:

```
LOG_LEVEL=debug
# Disable JSON logs
LOG_FORMAT=text
```

## Run Web server

Using Docker, and a local config file:

```
docker run -p 8000:8000 -v `pwd`/config.toml:/app/config.toml mozilla/telescope
```

Or from source (*requires Python 3.10+ and Poetry*):

```
make serve
```

## Web UI

A minimalist Web page is accessible at ``/html/index.html`` and shows every check status,
along with the returned data and documentation.

A SVG diagram can be shown in the UI (see ``DIAGRAM_FILE``). Elements of the SVG diagram will be turned red or green based on check results.
Set the ``id`` attribute of relevant diagram elements to ``${project}--${name}`` (eg. ``remotesettings-uptake--error-rate``) and the app will toggle the ``fill`` attribute.


## Bug tracker integration

The list of known issues for each check can be obtained from the configured bug tracker (see configuration section to disable).

The default implementation is for Bugzilla, and retrieves the bugs which have a certain string in their ``whiteboard`` field.
For example, if the ``SERVICE_NAME`` is ``delivery-checks`` and ``ENV_NAME`` is ``prod``, the bugs for the check ``server/heartbeat`` should have ``delivery-checks prod server/heartbeat`` in their ``whiteboard`` field to be listed.

If the bugs are only readable by authenticated users, then set ``BUGTRACKER_API_KEY`` to retrieve them all.
Note that for security bugs only bug IDs are shown, summaries will be empty.


## CLI

Using Docker, and a local config file:

```
docker run -v `pwd`/config.toml:/app/config.toml mozilla/telescope check

docker run -v `pwd`/config.toml:/app/config.toml mozilla/telescope check myproject

docker run -v `pwd`/config.toml:/app/config.toml mozilla/telescope check myproject mycheck
```

Or from source (*requires Python 3.8+ and Poetry*):

```
make check

make check project=myproject

make check project=myproject check=mycheck
```

Return codes:

- `0`: all checks were successful
- `1`: some check failed
- `2`: some check crashed (ie. Python exception)


## Tests

```
make tests
```

## License

*Telescope* is licensed under the MPLv2. See the `LICENSE` file for details.
