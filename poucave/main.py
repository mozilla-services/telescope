import importlib

from aiohttp import web

from . import config
from . import utils


class Handlers:

    def __init__(self):
        self.cache = utils.Cache()

    def checkpoint(self, project, name, description, module, ttl, params):
        mod = importlib.import_module(module)
        func = getattr(mod, "run")

        async def handler(request):
            # Each check has its own TTL.
            cache_key = f"{project}/{name}"
            result = self.cache.get(cache_key)
            if result is None:
                # Execute the check itself.
                result = await func(**params)
                self.cache.set(cache_key, result, ttl=ttl)

            # Return check result data.
            status, data = result
            body = {
                'name': name,
                'project': project,
                'description': description,
                'data': data,
            }
            status_code = 200 if status else 503
            return web.json_response(body, status=status_code)

        return handler

    async def hello(self, request):
        body = {'hello': 'poucave'}
        return web.json_response(body)


def main(argv):
    app = web.Application()
    handlers = Handlers()
    routes = [web.get("/", handlers.hello)]

    conf = config.load()
    for project, checks in conf["checks"].items():
        for check, params in checks.items():
            uri = f"/checks/{project}/{check}"
            handler = handlers.checkpoint(project, check, **params)
            routes.append(web.get(uri, handler))

    app.add_routes(routes)
    web.run_app(app)
