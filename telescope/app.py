import asyncio
import importlib
import json
import logging.config
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp_cors
import sentry_sdk
from aiohttp import web
from sentry_sdk import capture_message
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from termcolor import cprint

from . import config, middleware, utils


HTML_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "html")

logger = logging.getLogger(__name__)
results_logger = logging.getLogger("check.result")

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
        tags: Optional[str] = None,
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

        elif tags is not None:
            taglist: List[str] = tags.split("+")
            selected = [c for c in selected if set(taglist).issubset(set(c.tags))]
            if len(selected) == 0:
                raise ValueError(f"No check with tags '{tags}'")

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
        plot: Optional[str] = None,
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

        self._plot = plot

    async def run(
        self, cache=None, events=None, force=False
    ) -> Tuple[Any, bool, Any, float]:
        identifier = f"{self.project}/{self.name}"

        # Caution: the cache key may contain secrets and should never be exposed.
        # We're fine here since the cache is in memory.
        cache_key = f"{identifier}-" + ",".join(
            f"{k}:{v}" for k, v in self.params.items()
        )

        # Wait for any other parallel run of this same check to finish
        # in order to get its result value from the cache.
        async with cache.lock(cache_key) if cache else utils.DummyLock():
            result = cache.get(cache_key) if cache else None

            last_success = None
            if result is not None:
                # See last run info.
                _, last_success, _, _ = result

            if result is None or force:
                # Execute the check again.
                before = time.time()
                success, data = await self.func(**self.params)
                duration = time.time() - before
                result = utils.utcnow(), success, data, duration
                if cache:
                    cache.set(cache_key, result, ttl=self.ttl)

                # Notify listeners about check run/state.
                if events:
                    payload = {
                        "check": self,
                        "result": {
                            "success": success,
                            "data": data,
                        },
                    }
                    events.emit("check:run", payload=payload)
                    is_first_failure = last_success is None and not success
                    is_check_changed = (
                        last_success is not None and last_success != success
                    )
                    if is_first_failure or is_check_changed:
                        events.emit("check:state:changed", payload=payload)

        return result

    @property
    def plot(self):
        default_plot = getattr(self.module, "DEFAULT_PLOT", None)
        return self._plot or default_plot

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
            plot=self._plot,
        )


@routes.get("/")
async def hello(request):
    # When visiting the root URL with a browser, redirect to
    # the HTML UI.
    if "text/html" in ",".join(request.headers.getall("Accept", [])):
        raise web.HTTPFound(location="html/index.html")

    body = {
        "hello": "telescope",
        "service": config.SERVICE_NAME,
        "title": config.SERVICE_TITLE or config.SERVICE_NAME.capitalize(),
        "environment": config.ENV_NAME,
    }
    return web.json_response(body)


@routes.get("/__lbheartbeat__")
async def lbheartbeat(request):
    return web.json_response({})


@routes.get("/__heartbeat__")
async def heartbeat(request):
    checks = {}

    # Check that `curl` has HTTP2 and HTTP3 for `checks.core.http_versions`
    curl_cmd = subprocess.run(
        [config.CURL_BINARY_PATH, "--version"],
        capture_output=True,
    )
    output = curl_cmd.stdout.strip().decode()
    missing_features = [f for f in ("HTTP2", "HTTP3", "SSL") if f not in output]
    checks["curl"] = (
        "ok"
        if not missing_features
        else f"missing features {', '.join(missing_features)}"
    )

    # Bugzilla
    bz_ping = await request.app["telescope.tracker"].ping()
    checks["bugzilla"] = "ok" if bz_ping else "Bugzilla ping failed"

    # Big Query
    try:
        checks["bigquery"] = (await utils.fetch_bigquery("SELECT 'ok';"))[0]
    except Exception as exc:
        checks["bigquery"] = str(exc)

    status = 200 if all(v == "ok" for v in checks.values()) else 503
    return web.json_response(checks, status=status)


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
    checks = request.app["telescope.checks"]
    info = [c.info for c in checks.all]
    return web.json_response(info)


@routes.get("/checks/{project}")
@utils.render_checks
async def project_checkpoints(request):
    checks = request.app["telescope.checks"]
    cache = request.app["telescope.cache"]
    tracker = request.app["telescope.tracker"]
    history = request.app["telescope.history"]
    events = request.app["telescope.events"]

    try:
        selected = checks.lookup(**request.match_info)
    except ValueError:
        raise web.HTTPNotFound()

    return await _run_checks_parallel(
        checks=selected, cache=cache, tracker=tracker, history=history, events=events
    )


@routes.get("/checks/tags/{tags}")
@utils.render_checks
async def tags_checkpoints(request):
    checks = request.app["telescope.checks"]
    cache = request.app["telescope.cache"]
    tracker = request.app["telescope.tracker"]
    history = request.app["telescope.history"]
    events = request.app["telescope.events"]

    try:
        selected = checks.lookup(**request.match_info)
    except ValueError:
        raise web.HTTPNotFound()

    return await _run_checks_parallel(
        checks=selected, cache=cache, tracker=tracker, history=history, events=events
    )


@routes.get("/checks/{project}/{name}")
@utils.render_checks
async def checkpoint(request):
    checks = request.app["telescope.checks"]
    cache = request.app["telescope.cache"]
    tracker = request.app["telescope.tracker"]
    history = request.app["telescope.history"]
    events = request.app["telescope.events"]

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

    return (
        await _run_checks_parallel(
            checks=[check],
            cache=cache,
            tracker=tracker,
            history=history,
            events=events,
            force=force,
        )
    )[0]


@routes.get("/diagram.svg")
async def svg_diagram(request):
    path = config.DIAGRAM_FILE
    try:
        with open(path, "r") as f:
            return web.Response(text=f.read(), content_type="image/svg+xml")
    except IOError:
        raise web.HTTPNotFound(reason=f"{path} could not be found.")


async def _run_checks_parallel(checks, cache, tracker, history, events, force=False):
    futures = [check.run(cache=cache, events=events, force=force) for check in checks]
    results = await utils.run_parallel(*futures)

    body = []
    for check, result in zip(checks, results):
        timestamp, success, data, duration = result
        buglist = await tracker.fetch(check.project, check.name)
        scalar_history = await history.fetch(check.project, check.name)
        body.append(
            {
                **check.info,
                "datetime": timestamp.isoformat(),
                "duration": int(duration * 1000),
                "success": success,
                "data": data,
                "buglist": buglist,
                "history": scalar_history,
            }
        )
    return body


def _send_sentry(event, payload):
    """
    Send a Sentry message when the check state changes.
    """
    check = payload["check"]
    data = payload["result"]["data"]
    success = payload["result"]["success"]

    scope = sentry_sdk.get_current_scope()
    scope.set_extra("data", data)
    scope.set_tag("source", "check")
    # Group check failures (and not by message).
    identifier = f"{check.project}/{check.name}"
    scope.fingerprint = [identifier]
    capture_message(
        f"{identifier} " + ("recovered" if success else "is failing"),
        level="info" if success else "error",
    )


def _log_result(event, payload):
    """
    Log check result data to stdout.

    Our logging setup stores JSON MozLog output into BigQuery, and
    this allows us to keep track of checks history.
    """
    check = payload["check"]
    result = payload["result"]

    infos = {
        "time": utils.utcnow().isoformat(),
        "project": check.project,
        "check": check.name,
        "tags": check.tags,
        "success": result["success"],
        # Convert result data to string (for type consistency).
        "data": json.dumps(result["data"]),
        # An optional scalar value (see below)
        "plot": None,
    }
    # Extract the float value to plot, defined in check module or conf.
    if check.plot is not None:
        try:
            infos["plot"] = round(
                float(utils.extract_json(check.plot, result["data"])), 2
            )
        except (ValueError, TypeError) as e:
            # Ignore errors on checks which return error string in data on failure.
            logger.warning(e)

    results_logger.info("", extra=infos)


def init_app(checks: Checks):
    app = web.Application(
        middlewares=[middleware.error_middleware, middleware.request_summary]
    )
    # Setup Sentry to catch exceptions.
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENV_NAME,
        integrations=[AioHttpIntegration()],
    )

    app["telescope.cache"] = utils.Cache()
    app["telescope.checks"] = checks
    app["telescope.tracker"] = utils.BugTracker(cache=app["telescope.cache"])
    app["telescope.history"] = utils.History(cache=app["telescope.cache"])
    app["telescope.events"] = utils.EventEmitter()

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

    # React to check run / state changes.
    app["telescope.events"].on("check:run", _log_result)
    app["telescope.events"].on("check:state:changed", _send_sentry)

    return app


def run_check(check):
    cprint(check.description, "white")

    _, success, data, _ = asyncio.run(check.run())

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
    logger.debug(f"Running at http://{config.HOST}:{config.PORT}")
    web.run_app(app, host=config.HOST, port=config.PORT, print=False)
