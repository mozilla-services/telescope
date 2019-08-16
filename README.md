# Poucave

*Poucave* is a small Web app that will act as a proxy between a monitoring service like Pingdom and a series of domain specific checks for your infrastructure.


## Usage

Every check defined in your configuration file is exposed as an endpoint:

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
    "description": "Some check description.",
    "data": {
        "ok": true
    }
}

```

The response has:

* Status ``200`` if the check is positive
* Status ``503`` if the check fails
* Some additional `"data"`, specific to each check


## Configure

The checks are defined in a `config.toml` file:

```toml
[checks.remotesettings.public-heartbeat]
description = "Heartbeat of the public read-only instance."
module = "poucave.checks.heartbeat"
ttl = 60
params.url = "https://settings.prod.mozaws.net/v1/__heartbeat__"

```

* `description`: Some details about this check.
* `ttl`: Cache the check result for a number of seconds
* `module`: Path to Python module
* `params`: Parameters specific to the check

## Run

```
make serve
```

## Tests

```
make tests
```

## License

*Poucave* is licensed under the MPLv2. See the `LICENSE` file for details.
