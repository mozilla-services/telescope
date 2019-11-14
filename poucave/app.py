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


class Check:
    def __init__(self, module: Union[str, object], params: Optional[Dict[str, Any]]):
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
    def exposed_params(self):
        exposed_params = getattr(self.module, "EXPOSED_PARAMETERS", [])
        return {k: v for k, v in self.params.items() if k in exposed_params}

    def override_params(self, params: Dict[str, Any]):
        url_params = getattr(self.module, "URL_PARAMETERS", [])
        query_params = {p: v for p, v in params.items() if p in url_params}
        return Check(self.module, {**self.params, **query_params})


class Handlers:
    def __init__(self):
        self._checkpoints = []

    async def hello(self, request):
        body = {"hello": "poucave"}
        return web.json_response(body)

    async def checkpoints(self, request):
        return web.json_response(self._checkpoints)

    async def lbheartbeat(self, request):
        return web.json_response({})

    async def heartbeat(self, request):
        return web.json_response({})

    async def version(self, request):
        path = config.VERSION_FILE
        if not os.path.exists(path):
            raise FileNotFoundError(f"Version file {path} does not exist")

        with open(path) as f:
            content = json.load(f)
        return web.json_response(content)

    def checkpoint(
        self,
        project: str,
        name: str,
        description: str,
        module: str,
        ttl: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        ttl = ttl or config.DEFAULT_TTL  # ttl=0 is not supported.

        chck = Check(module, params)

        infos = {
            "name": name,
            "project": project,
            "module": module,
            "description": description,
            "documentation": chck.doc,
            "url": f"/checks/{project}/{name}",
            "ttl": ttl,
            "parameters": chck.exposed_params,
        }
        self._checkpoints.append(infos)

        async def handler(request):
            cache = request.app["poucave.cache"]

            # Some parameters can be overriden in URL query.
            try:
                check = chck.override_params(request.query)
            except ValueError:
                raise web.HTTPBadRequest()

            # Each check has its own TTL.
            cache_key = f"{project}/{name}-" + ",".join(
                f"{k}:{v}" for k, v in check.params.items()
            )
            result = cache.get(cache_key)

            if result is None:
                # Never ran successfully. Consider expired.
                age = ttl + 1
                last_success = None
            else:
                timestamp, last_success, _, _ = result
                age = (utils.utcnow() - timestamp).seconds

            if age > ttl:
                # Execute the check again.
                before = time.time()
                success, data = await check.run()
                duration = time.time() - before
                result = utils.utcnow(), success, data, duration
                cache.set(cache_key, result)

                # If different from last time, then alert on Sentry.
                is_first_failure = last_success is None and not success
                is_check_changed = last_success is not None and last_success != success
                if is_first_failure or is_check_changed:
                    with configure_scope() as scope:
                        scope.set_extra("data", data)
                    capture_message(
                        f"{project}/{name} "
                        + ("recovered" if success else "is failing")
                    )

            # Return check result data.
            timestamp, success, data, duration = result
            body = {
                **infos,
                "datetime": timestamp.isoformat(),
                "duration": int(duration * 1000),
                "success": success,
                "data": data,
                "parameters": check.exposed_params,
            }
            status_code = 200 if success else 503
            return web.json_response(body, status=status_code)

        return handler


def init_app(conf):
    app = web.Application(
        middlewares=[middleware.error_middleware, middleware.request_summary]
    )
    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[AioHttpIntegration()])
    app["poucave.cache"] = utils.Cache()

    handlers = Handlers()
    routes = [
        web.get("/", handlers.hello),
        web.get("/checks", handlers.checkpoints),
        web.get("/__lbheartbeat__", handlers.lbheartbeat),
        web.get("/__heartbeat__", handlers.heartbeat),
        web.get("/__version__", handlers.version),
    ]

    for project, checks in conf["checks"].items():
        for check, params in checks.items():
            uri = f"/checks/{project}/{check}"
            handler = handlers.checkpoint(project, check, **params)
            routes.append(web.get(uri, handler))

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


def run_check(conf):
    cprint(conf["description"], "white")
    module = conf["module"]
    params = conf.get("params", {})
    check = Check(module, params)

    pool = concurrent.futures.ThreadPoolExecutor()
    success, data = pool.submit(asyncio.run, check.run()).result()

    cprint(json.dumps(data, indent=2), "green" if success else "red")
    return success


def main(argv):
    logging.config.dictConfig(config.LOGGING)
    conf = config.load(config.CONFIG_FILE)

    # If CLI arg is provided, run the check.
    if len(argv) >= 1:
        project = argv[0]
        if len(argv) > 1:
            checks = [argv[1]]
        else:
            checks = conf["checks"][project].keys()
        successes = []
        for check in checks:
            try:
                check_conf = conf["checks"][project][check]
            except KeyError:
                section = f"checks.{project}.{check}"
                cprint(f"Unknown check '{section}' in '{config.CONFIG_FILE}'", "red")
                return 2

            success = run_check(check_conf)
            successes.append(success)

        return 0 if all(successes) else 1

    # Otherwise, run the Web app.
    app = init_app(conf)
    web.run_app(app, host=config.HOST, port=config.PORT, print=False)
