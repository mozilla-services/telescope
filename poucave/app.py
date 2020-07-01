import asyncio
import concurrent.futures
import importlib
import json
import logging.config
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp_cors
import sentry_sdk
from aiohttp import web
from sentry_sdk import capture_message, configure_scope
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from termcolor import cprint

from . import config, middleware, utils


HTML_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "html")

routes = web.RouteTableDef()


class Checks:
    @classmethod
    def from_conf(cls, conf):
        checks = []
        for project, entries in conf["checks"].items():
            for name, attrs in entries.items():
                check = Check(project=project, name=name, **attrs)
                checks.append(check)
        return Checks(checks)

    def __init__(self, checks):
        self.all = checks

    def lookup(
        self,
        project: Optional[str] = None,
        name: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        selected = self.all

        if project is not None:
            selected = [c for c in selected if c.project == project]
            if len(selected) == 0:
                raise ValueError(f"Unknown project '{project}'")

        if name is not None:
            selected = [c for c in selected if c.name == name]
            if len(selected) == 0:
                raise ValueError(f"Unknown check '{project}.{name}'")

        elif tag is not None:
            selected = [c for c in selected if tag in c.tags]
            if len(selected) == 0:
                raise ValueError(f"No check with tag '{tag}'")

        return selected


class Check:
    def __init__(
        self,
        project: str,
        name: str,
        description: str,
        module: Union[str, object],
        tags: Optional[List[str]] = None,
        ttl: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        self.project = project
        self.name = name
        self.description = description
        self.tags = tags or []
        self.ttl = ttl or config.DEFAULT_TTL  # ttl=0 is not supported.

        self.module = (
            importlib.import_module(module) if isinstance(module, str) else module
        )
        self.doc = (self.module.__doc__ or "").strip()
        self.func = getattr(self.module, "run")

        self.params: Dict[str, Any] = {}
        for param, value in (params or {}).items():
            # Make sure the specified parameters in configuration are known.
            if param not in self.func.__annotations__:
                raise ValueError(f"Unknown parameter '{param}' for '{module}'")
            # Make sure specifed value matches function param type.
            _type = self.func.__annotations__[param]
            self.params[param] = utils.cast_value(_type, value)

    async def run(self, cache=None, force=False) -> Tuple[Any, bool, Any, int]:
        identifier = f"{self.project}/{self.name}"

        # Caution: the cache key may contain secrets and should never be exposed.
        # We're fine here since we the cache is in memory.
        cache_key = f"{identifier}-" + ",".join(
            f"{k}:{v}" for k, v in self.params.items()
        )
        result = cache.get(cache_key) if cache else None

        if result is None:
            # Never ran successfully. Consider expired.
            age = self.ttl + 1
            last_success = None
        else:
            # See last run info.
            timestamp, last_success, _, _ = result
            age = (utils.utcnow() - timestamp).seconds

        if age > self.ttl or force:
            # Execute the check again.
            before = time.time()
            success, data = await self.func(**self.params)
            duration = time.time() - before
            result = utils.utcnow(), success, data, duration
            if cache:
                cache.set(cache_key, result)

            # If different from last time, then alert on Sentry.
            is_first_failure = last_success is None and not success
            is_check_changed = last_success is not None and last_success != success
            if is_first_failure or is_check_changed:
                with configure_scope() as scope:
                    scope.set_extra("data", data)
                    scope.set_tag("source", "check")
                    # Group check failures (and not by message).
                    scope.fingerprint = [identifier]
                capture_message(
                    f"{identifier} " + ("recovered" if success else "is failing"),
                    level="info" if success else "error",
                )

        return result

    @property
    def exposed_params(self):
        exposed_params = getattr(self.module, "EXPOSED_PARAMETERS", [])
        return {k: v for k, v in self.params.items() if k in exposed_params}

    @property
    def info(self):
        troubleshooting_url = config.TROUBLESHOOTING_LINK_TEMPLATE.format(
            project=self.project, check=self.name
        )
        return {
            "name": self.name,
            "project": self.project,
            "module": self.module.__name__,
            "tags": self.tags,
            "description": self.description,
            "documentation": self.doc,
            "url": f"/checks/{self.project}/{self.name}",
            "ttl": self.ttl,
            "parameters": self.exposed_params,
            "troubleshooting": troubleshooting_url,
        }

    def override_params(self, params: Dict[str, Any]):
        url_params = getattr(self.module, "URL_PARAMETERS", [])
        query_params = {p: v for p, v in params.items() if p in url_params}
        return Check(
            project=self.project,
            name=self.name,
            description=self.description,
            module=self.module,
            tags=self.tags,
            ttl=self.ttl,
            params={**self.params, **query_params},
        )


@routes.get("/")
async def hello(request):
    # When visiting the root URL with a browser, redirect to
    # the HTML UI.
    if "text/html" in ",".join(request.headers.getall("Accept", [])):
        return web.HTTPFound(location="html/index.html")

    body = {"hello": "poucave"}
    return web.json_response(body)


@routes.get("/__lbheartbeat__")
async def lbheartbeat(request):
    return web.json_response({})


@routes.get("/__heartbeat__")
async def heartbeat(request):
    return web.json_response({})


@routes.get("/__version__")
async def version(request):
    path = config.VERSION_FILE
    if not os.path.exists(path):
        raise FileNotFoundError(f"Version file {path} does not exist")

    with open(path) as f:
        content = json.load(f)
    return web.json_response(content)


@routes.get("/checks")
async def checkpoints(request):
    checks = request.app["poucave.checks"]
    info = [c.info for c in checks.all]
    return web.json_response(info)


@routes.get("/checks/{project}")
@utils.render_checks
async def project_checkpoints(request):
    checks = request.app["poucave.checks"]
    cache = request.app["poucave.cache"]

    try:
        selected = checks.lookup(**request.match_info)
    except ValueError:
        raise web.HTTPNotFound()

    return await _run_checks_parallel(selected, cache)


@routes.get("/checks/tags/{tag}")
@utils.render_checks
async def tags_checkpoints(request):
    checks = request.app["poucave.checks"]
    cache = request.app["poucave.cache"]

    try:
        selected = checks.lookup(**request.match_info)
    except ValueError:
        raise web.HTTPNotFound()

    return await _run_checks_parallel(selected, cache)


@routes.get("/checks/{project}/{name}")
@utils.render_checks
async def checkpoint(request):
    checks = request.app["poucave.checks"]
    cache = request.app["poucave.cache"]

    try:
        selected = checks.lookup(**request.match_info)[0]
    except ValueError:
        raise web.HTTPNotFound()

    # Refresh cache?
    force = "refresh" in request.query
    if force and request.query["refresh"] != config.REFRESH_SECRET:
        raise web.HTTPBadRequest(reason="Invalid refresh secret")

    # Some parameters can be overriden in URL query.
    try:
        check = selected.override_params(request.query)
    except ValueError:
        raise web.HTTPBadRequest()

    return (await _run_checks_parallel([check], cache, force))[0]


@routes.get("/diagram.svg")
async def svg_diagram(request):
    path = config.DIAGRAM_FILE
    try:
        with open(path, "r") as f:
            return web.Response(text=f.read(), content_type="image/svg+xml")
    except IOError:
        raise web.HTTPNotFound(reason=f"{path} could not be found.")


async def _run_checks_parallel(checks, cache, force=False):
    futures = [check.run(cache=cache, force=force) for check in checks]
    results = await utils.run_parallel(*futures)

    body = []
    for check, result in zip(checks, results):
        timestamp, success, data, duration = result
        body.append(
            {
                **check.info,
                "datetime": timestamp.isoformat(),
                "duration": int(duration * 1000),
                "success": success,
                "data": data,
            }
        )
    return body


def init_app(checks: Checks):
    app = web.Application(
        middlewares=[middleware.error_middleware, middleware.request_summary]
    )
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENV_NAME,
        integrations=[AioHttpIntegration()],
    )
    app["poucave.cache"] = utils.Cache()
    app["poucave.checks"] = checks

    app.add_routes(routes)

    app.router.add_static("/html/", path=HTML_DIR, name="html", show_index=True)

    # Enable CORS on all routes.
    cors = aiohttp_cors.setup(
        app,
        defaults={
            config.CORS_ORIGINS: aiohttp_cors.ResourceOptions(
                allow_credentials=True, expose_headers="*", allow_headers="*"
            )
        },
    )
    for route in list(app.router.routes()):
        cors.add(route)

    return app


def run_check(check):
    cprint(check.description, "white")

    pool = concurrent.futures.ThreadPoolExecutor()
    _, success, data, _ = pool.submit(asyncio.run, check.run()).result()

    cprint(json.dumps(data, indent=2), "green" if success else "red")
    return success


def main(argv):
    logging.config.dictConfig(config.LOGGING)
    conf = config.load(config.CONFIG_FILE)

    checks = Checks.from_conf(conf)

    # If CLI arg is provided, run the check.
    if len(argv) >= 1 and argv[0] == "check":
        project = None
        name = None
        if len(argv) > 1:
            project = argv[1]
        if len(argv) > 2:
            name = argv[2]
        try:
            selected = checks.lookup(project=project, name=name)
        except ValueError as e:
            cprint(f"{e} in '{config.CONFIG_FILE}'", "red")
            return 2

        successes = []
        for check in selected:
            success = run_check(check)
            successes.append(success)

        return 0 if all(successes) else 1

    # Otherwise, run the Web app.
    app = init_app(checks)
    web.run_app(app, host=config.HOST, port=config.PORT, print=False)
