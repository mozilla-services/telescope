import asyncio
import importlib
import json
import logging.config
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp_cors
import prometheus_client
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


METRICS = {
    "lock_wait_seconds": prometheus_client.Histogram(
        name=f"{config.METRICS_PREFIX}_lock_wait_seconds",
        documentation="Histogram of lock wait duration in seconds",
        labelnames=[
            "project",
            "check",
        ],
        buckets=[0.1, 0.5, 1.0, 3.0, 6.0, 12, 30, 60, float("inf")],
    ),
    "parallelism_gauge": prometheus_client.Gauge(
        name=f"{config.METRICS_PREFIX}_parallelism_gauge",
        documentation="Gauge of currently executed operations",
        labelnames=["type"],
    ),
    "event_loop_lag_seconds": prometheus_client.Histogram(
        name=f"{config.METRICS_PREFIX}_event_loop_lag_seconds",
        documentation="Event loop scheduling lag in seconds",
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 3.0, float("inf")],
        labelnames=["loop_name"],
    ),
    "event_loop_pending_tasks": prometheus_client.Gauge(
        name=f"{config.METRICS_PREFIX}_event_loop_pending_tasks",
        documentation="Approximate number of pending asyncio tasks in this process",
        labelnames=["loop_name"],
    ),
    "check_run_duration_seconds": prometheus_client.Histogram(
        name=f"{config.METRICS_PREFIX}_check_run_duration_seconds",
        documentation="Histogram of check run duration in seconds",
        labelnames=[
            "project",
            "check",
        ],
        buckets=[0.1, 0.5, 1.0, 3.0, 6.0, 12, 30, 60, float("inf")],
    ),
    "request_duration_seconds": prometheus_client.Histogram(
        name=f"{config.METRICS_PREFIX}_request_duration_seconds",
        documentation="Histogram of request duration in seconds",
        labelnames=[
            "method",
            "endpoint",
            "status",
            "project",
            "check",
        ],
        buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 3.0, 6.0, float("inf")],
    ),
    "request_summary": prometheus_client.Counter(
        name=f"{config.METRICS_PREFIX}_request_summary",
        documentation="Counter of requests",
        labelnames=[
            "method",
            "endpoint",
            "status",
            "project",
            "check",
        ],
    ),
}


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
    ) -> Tuple[str, bool, Any, float]:
        identifier = f"{self.project}/{self.name}"

        # Caution: the cache key may contain secrets and should never be exposed.
        # Cache implementations should take care of hashing/encrypting keys if needed.
        cache_key = f"{identifier}-" + ",".join(
            f"{k}:{v}" for k, v in sorted(self.params.items())
        )

        # First, check if we have a cached result.
        result = await cache.get(cache_key) if cache else None
        if result is not None and not force:
            # Return previously cached result, do not bother waiting
            # for the latest check run to finish.
            return result

        # Run the check code.
        # But wait for any other parallel run of this same check to finish
        # to avoid running the same check multiple times in parallel.
        with_cache_lock = config.CACHE_LOCK_ENABLED and cache is not None
        lock_before_ts = time.time()
        async with cache.lock(cache_key) if with_cache_lock else utils.DummyLock():
            lock_elapsed_sec = time.time() - lock_before_ts
            METRICS["lock_wait_seconds"].labels(self.project, self.name).observe(  # type: ignore
                lock_elapsed_sec
            )

            result = await cache.get(cache_key) if cache else None

            last_success = None
            if result is not None:
                # See last run info.
                _, last_success, _, _ = result

            if result is None or force:
                # Execute the check again.
                before = time.time()
                success, data = await self.func(**self.params)
                duration = time.time() - before
                METRICS["check_run_duration_seconds"].labels(
                    self.project, self.name
                ).observe(duration)  # type: ignore

                result = utils.utcnow().isoformat(), success, data, duration
                if cache:
                    await cache.set(cache_key, result, ttl=self.ttl)

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
        "settings": {
            "cache": request.app["telescope.cache"].__class__.__name__,
            "cache_lock_enabled": config.CACHE_LOCK_ENABLED,
            "limit_requests_concurrency": config.LIMIT_REQUEST_CONCURRENCY,
            "limit_global_concurrency": config.LIMIT_GLOBAL_CONCURRENCY,
            "request_max_retries": config.REQUESTS_MAX_RETRIES,
            "request_timeout_seconds": config.REQUESTS_TIMEOUT_SECONDS,
            "client_parallel_requests": config.CLIENT_PARALLEL_REQUESTS,
        },
    }
    return web.json_response(body)


@routes.get("/__lbheartbeat__")
async def lbheartbeat(request):
    return web.json_response({})


@routes.get("/__heartbeat__")
async def heartbeat(request):
    status = 200
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

    # Bugzilla ping test. Only informational.
    bz_ping = await request.app["telescope.tracker"].ping()
    checks["bugzilla"] = "ok" if bz_ping else "Bugzilla ping failed"

    # Cache backend test.
    cache_backend = request.app["telescope.cache"]
    ping = await cache_backend.ping()
    if ping:
        checks["cache"] = "ok"
    else:
        checks["cache"] = "cache failing"
        # Fail heartbeat if cache is down.
        status = 503

    return web.json_response(checks, status=status)


@routes.get("/__version__")
async def version(request):
    path = config.VERSION_FILE
    if not os.path.exists(path):
        raise FileNotFoundError(f"Version file {path} does not exist")

    with open(path) as f:
        content = json.load(f)
    return web.json_response(content)


@routes.get("/__metrics__")
async def metrics(request):
    response = web.Response(body=prometheus_client.generate_latest())
    response.content_type = prometheus_client.CONTENT_TYPE_LATEST
    return response


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
        datetimeiso, success, data, duration = result
        buglist = await tracker.fetch(check.project, check.name)
        scalar_history = await history.fetch(check.project, check.name)
        body.append(
            {
                **check.info,
                "datetime": datetimeiso,
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
        middlewares=[
            middleware.error_middleware,
            middleware.request_summary,
            middleware.metrics_middleware,
        ]
    )
    # Setup Sentry to catch exceptions.
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENV_NAME,
        integrations=[AioHttpIntegration()],
    )

    app["telescope.cache"] = (
        utils.RedisCache(url=config.REDIS_CACHE_URL, key_prefix=config.REDIS_KEY_PREFIX)
        if config.REDIS_CACHE_URL
        else utils.InMemoryCache()
    )
    app["telescope.checks"] = checks
    app["telescope.tracker"] = utils.BugTracker(cache=app["telescope.cache"])
    app["telescope.history"] = utils.History(cache=app["telescope.cache"])
    app["telescope.events"] = utils.EventEmitter()
    app["telescope.metrics"] = METRICS

    utils.setup_metrics(METRICS)

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


def run_check(loop, check, cache, events, force):
    cprint(check.description, "white")

    try:
        _, success, data, _ = loop.run_until_complete(
            check.run(cache=cache, events=events, force=force)
        )
        cprint(json.dumps(data, indent=2), "green" if success else "red")
    except Exception as e:
        cprint(f"Error running check '{check.project}/{check.name}': {e!r}", "red")
        success = False
    return success


async def observe_event_loop(
    loop: asyncio.AbstractEventLoop, loop_name: str, interval: float
):
    """
    Periodically measure:
    - event loop lag (how late our scheduled wake-up is)
    - number of pending tasks
    """
    while interval > 0:  # Do not run if configured as 0.
        scheduled = loop.time()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        actual = loop.time()
        lag = max(0, actual - (scheduled + interval))
        METRICS["event_loop_lag_seconds"].labels(loop_name).observe(lag)  # type: ignore

        # Count pending tasks (excluding done ones)
        pending = sum(1 for t in asyncio.all_tasks(loop) if not t.done())
        METRICS["event_loop_pending_tasks"].labels(loop_name).set(pending)  # type: ignore

        logger.debug(f"Event loop lag: {int(lag * 1000)}ms, pending tasks: {pending}")


async def background_tasks(app):
    """
    Start background tasks when the app starts, and cleanup when the app stops.
    """
    bg_task = asyncio.create_task(
        observe_event_loop(
            loop=app.loop,
            loop_name="main",
            interval=config.EVENT_LOOP_OBSERVE_INTERVAL_SECONDS,
        )
    )
    yield
    bg_task.cancel()
    await bg_task


def main(argv):
    logging.config.dictConfig(config.LOGGING)
    conf = config.load(config.CONFIG_FILE)

    checks = Checks.from_conf(conf)

    app = init_app(checks)
    cache = app["telescope.cache"]
    events = app["telescope.events"]
    app.cleanup_ctx.append(background_tasks)

    # If CLI arg is provided, run the check.
    if len(argv) >= 1 and argv[0] == "check":
        project = None
        name = None
        if len(argv) > 1:
            project = argv[1]
        if len(argv) > 2:
            name = argv[2]
        force = "--force" in argv
        try:
            selected = checks.lookup(project=project, name=name)
        except ValueError as e:
            cprint(f"{e} in '{config.CONFIG_FILE}'", "red")
            return 2

        loop = asyncio.get_event_loop()
        successes = []
        for check in selected:
            success = run_check(loop, check, cache, events, force=force)
            successes.append(success)

        return 0 if all(successes) else 1

    # Otherwise, run the Web app.
    logger.debug(f"Running at http://{config.HOST}:{config.PORT}")
    web.run_app(app, host=config.HOST, port=config.PORT, print=False)
