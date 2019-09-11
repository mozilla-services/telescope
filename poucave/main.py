import asyncio
import concurrent.futures
import importlib
import json
import logging.config
import os
from datetime import datetime

import sentry_sdk
import aiohttp_cors
from aiohttp import web
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from termcolor import cprint

from . import config
from . import middleware
from . import utils


HTML_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "html")


class Handlers:
    def __init__(self):
        self.cache = utils.Cache()
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

    def checkpoint(self, project, name, description, module, ttl=None, params=None):
        ttl = ttl or config.DEFAULT_TTL  # ttl=0 is not supported.
        params = params or {}

        mod = importlib.import_module(module)
        doc = mod.__doc__.strip()
        func = getattr(mod, "run")

        exposed_params = getattr(mod, "EXPOSED_PARAMETERS", [])
        filtered_params = {k: v for k, v in params.items() if k in exposed_params}

        infos = {
            "name": name,
            "project": project,
            "module": module,
            "description": description,
            "documentation": doc,
            "parameters": filtered_params,
            "url": f"/checks/{project}/{name}",
        }
        self._checkpoints.append(infos)

        async def handler(request):
            # Each check has its own TTL.
            cache_key = f"{project}/{name}"
            result = self.cache.get(cache_key)
            if result is None:
                # Execute the check itself.
                success, data = await func(request, **params)
                result = datetime.now().isoformat(), success, data
                self.cache.set(cache_key, result, ttl=ttl)

            # Return check result data.
            dt, success, data = result
            body = {**infos, "datetime": dt, "success": success, "data": data}
            status_code = 200 if success else 503
            return web.json_response(body, status=status_code)

        return handler


def init_app(conf):
    app = web.Application(middlewares=[middleware.request_summary])
    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[AioHttpIntegration()])

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
    module = conf["module"]
    params = conf.get("params", {})
    func = getattr(importlib.import_module(module), "run")
    pool = concurrent.futures.ThreadPoolExecutor()
    success, data = pool.submit(asyncio.run, func(query={}, **params)).result()
    cprint(json.dumps(data, indent=2), "green" if success else "red")


def main(argv):
    logging.config.dictConfig(config.LOGGING)
    conf = config.load(config.CONFIG_FILE)

    # If CLI arg is provided, run the check.
    if len(argv) > 1:
        project, check = argv[:2]
        try:
            check_conf = conf["checks"][project][check]
        except KeyError:
            section = f"checks.{project}.{check}"
            cprint(f"Unknown check '{section}' in '{config.CONFIG_FILE}'", "red")
            return
        return run_check(check_conf)

    # Otherwise, run the Web app.
    app = init_app(conf)
    web.run_app(app, host=config.HOST, port=config.PORT, print=False)
