import asyncio
import concurrent.futures
import importlib
import json
import logging.config
import os
import time
from typing import Any, Dict, Optional, Union

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
    def __init__(self, conf):
        self.all = []
        for project, checks in conf["checks"].items():
            for name, params in checks.items():
                check = Check(project, name, **params)
                self.all.append(check)

    def get(self, project=None, name=None):
        if project is None:
            return self.all

        selected = [c for c in self.all if c.project == project]
        if len(selected) == 0:
            raise ValueError(f"Unknown project '{project}'")

        if name is None:
            return selected

        selected = [c for c in selected if c.name == name]
        if len(selected) == 0:
            raise ValueError(f"Unknown check '{project}.{name}'")

        return selected


class Check:
    def __init__(
        self,
        project: str,
        name: str,
        description: str,
        module: Union[str, object],
        ttl: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        self.project = project
        self.name = name
        self.description = description
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
            self.params[param] = _type(value)

    async def run(self):
        return await self.func(**self.params)

    @property
    def cache_key(self):
        # Caution: the cache key may contain secrets and should never be exposed.
        # We're fine here since we the cache is in memory.
        return f"{self.project}/{self.name}-" + ",".join(
            f"{k}:{v}" for k, v in self.params.items()
        )

    @property
    def exposed_params(self):
        exposed_params = getattr(self.module, "EXPOSED_PARAMETERS", [])
        return {k: v for k, v in self.params.items() if k in exposed_params}

    @property
    def infos(self):
        return {
            "name": self.name,
            "project": self.project,
            "module": self.module.__name__,
            "description": self.description,
            "documentation": self.doc,
            "url": f"/checks/{self.project}/{self.name}",
            "ttl": self.ttl,
            "parameters": self.exposed_params,
        }

    def override_params(self, params: Dict[str, Any]):
        url_params = getattr(self.module, "URL_PARAMETERS", [])
        query_params = {p: v for p, v in params.items() if p in url_params}
        return Check(
            self.project,
            self.name,
            self.description,
            self.module,
            self.ttl,
            {**self.params, **query_params},
        )


@routes.get("/")
async def hello(request):
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
    infos = [c.infos for c in checks.get()]
    return web.json_response(infos)


@routes.get("/checks/{project}")
async def project_checkpoints(request):
    checks = request.app["poucave.checks"]
    cache = request.app["poucave.cache"]

    try:
        selected = checks.get(**request.match_info)
    except ValueError:
        raise web.HTTPNotFound()

    body = []
    for check in selected:
        result = cache.get(check.cache_key)
        if result is None:
            # This check never ran successfully.
            body.append(check.infos)
            continue

        # In this endpoint, we chose not to refresh the check results
        # for the seek of speed.
        # We return the last execution result.
        timestamp, success, data, duration = result
        body.append(
            {
                **check.infos,
                "datetime": timestamp.isoformat(),
                "duration": int(duration * 1000),
                "success": success,
                "data": data,
            }
        )

    all_success = all(c.get("success", True) for c in body)
    status_code = 200 if all_success else 503
    return web.json_response(body, status=status_code)


@routes.get("/checks/{project}/{name}")
async def checkpoint(request):
    checks = request.app["poucave.checks"]
    cache = request.app["poucave.cache"]

    try:
        selected = checks.get(**request.match_info)[0]
    except ValueError:
        raise web.HTTPNotFound()

    # Some parameters can be overriden in URL query.
    try:
        check = selected.override_params(request.query)
    except ValueError:
        raise web.HTTPBadRequest()

    # Each check result is cached.
    result = cache.get(check.cache_key)

    if result is None:
        # Never ran successfully. Consider expired.
        age = check.ttl + 1
        last_success = None
    else:
        # See last run infos.
        timestamp, last_success, _, _ = result
        age = (utils.utcnow() - timestamp).seconds

    if age > check.ttl:
        # Execute the check again.
        before = time.time()
        success, data = await check.run()
        duration = time.time() - before
        result = utils.utcnow(), success, data, duration
        cache.set(check.cache_key, result)

        # If different from last time, then alert on Sentry.
        is_first_failure = last_success is None and not success
        is_check_changed = last_success is not None and last_success != success
        if is_first_failure or is_check_changed:
            with configure_scope() as scope:
                scope.set_extra("data", data)
            capture_message(
                f"{check.project}/{check.name} "
                + ("recovered" if success else "is failing")
            )

    # Return check result data.
    timestamp, success, data, duration = result
    body = {
        **check.infos,
        "parameters": check.exposed_params,
        "datetime": timestamp.isoformat(),
        "duration": int(duration * 1000),
        "success": success,
        "data": data,
    }
    status_code = 200 if success else 503
    return web.json_response(body, status=status_code)


def init_app(checks: Checks):
    app = web.Application(
        middlewares=[middleware.error_middleware, middleware.request_summary]
    )
    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[AioHttpIntegration()])
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
    success, data = pool.submit(asyncio.run, check.run()).result()

    cprint(json.dumps(data, indent=2), "green" if success else "red")
    return success


def main(argv):
    logging.config.dictConfig(config.LOGGING)
    conf = config.load(config.CONFIG_FILE)

    checks = Checks(conf)

    # If CLI arg is provided, run the check.
    if len(argv) >= 1:
        project = argv[0]
        name = None
        if len(argv) > 1:
            name = argv[1]

        try:
            selected = checks.get(project, name)
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
