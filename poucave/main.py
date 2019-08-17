import importlib
import os

from aiohttp import web

from . import config
from . import utils


class Handlers:
    def __init__(self):
        self.cache = utils.Cache()
        self._checkpoints = []

    async def hello(self, request):
        body = {"hello": "poucave"}
        return web.json_response(body)

    async def checkpoints(self, request):
        return web.json_response(self._checkpoints)

    def checkpoint(self, project, name, description, module, ttl, params):
        mod = importlib.import_module(module)
        doc = mod.__doc__.strip()
        func = getattr(mod, "run")
        infos = {
            "name": name,
            "project": project,
            "module": module,
            "description": description,
            "documentation": doc,
        }
        self._checkpoints.append(infos)

        async def handler(request):
            # Each check has its own TTL.
            cache_key = f"{project}/{name}"
            result = self.cache.get(cache_key)
            if result is None:
                # Execute the check itself.
                result = await func(request, **params)
                self.cache.set(cache_key, result, ttl=ttl)

            # Return check result data.
            status, data = result
            body = {**infos, "data": data}
            status_code = 200 if status else 503
            return web.json_response(body, status=status_code)

        return handler


def init_app(argv):
    app = web.Application()
    handlers = Handlers()
    routes = [web.get("/", handlers.hello), web.get("/checks", handlers.checkpoints)]

    config_file = os.getenv("CONFIG_FILE", "config.toml")
    conf = config.load(config_file)
    for project, checks in conf["checks"].items():
        for check, params in checks.items():
            uri = f"/checks/{project}/{check}"
            handler = handlers.checkpoint(project, check, **params)
            routes.append(web.get(uri, handler))

    app.add_routes(routes)
    return app


def main(argv):
    app = init_app(argv)
    web.run_app(app)
