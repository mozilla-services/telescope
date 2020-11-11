import asyncio
import json
import logging
import textwrap
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from itertools import chain
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

import aiohttp
import backoff
from aiohttp import web

from poucave import config
from poucave.typings import BugInfo


logger = logging.getLogger(__name__)


class Cache:
    def __init__(self):
        self._content: Dict[str, Any] = {}
        self._locks = {}

    def lock(self, key: str):
        return self._locks.setdefault(key, asyncio.Lock())

    def set(self, key: str, value: Any):
        self._content[key] = value

    def get(self, key: str) -> Optional[Any]:
        try:
            cached = self._content[key]
            return cached

        except KeyError:
            # Unknown key.
            return None


class DummyLock:
    def __await__(self):
        yield

    def __aenter__(self):
        return self

    def __aexit__(self, *args):
        return self


REDASH_URI = "https://sql.telemetry.mozilla.org/api/queries/{}/results.json?api_key={}"


async def fetch_redash(query_id: int, api_key: str) -> List[Dict]:
    redash_uri = REDASH_URI.format(query_id, api_key)
    body = await fetch_json(redash_uri)
    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    logger.info("Fetched {} row(s) from Redash".format(len(rows)))
    return rows


retry_decorator = backoff.on_exception(
    backoff.expo,
    (aiohttp.ClientError, asyncio.TimeoutError),
    max_tries=config.REQUESTS_MAX_RETRIES + 1,  # + 1 because REtries.
)


@retry_decorator
async def fetch_json(url: str, **kwargs) -> object:
    logger.debug(f"Fetch JSON from {url}")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return await response.json()


@retry_decorator
async def fetch_text(url: str, **kwargs) -> str:
    logger.debug(f"Fetch text from {url}")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return await response.text()


@retry_decorator
async def fetch_head(url: str, **kwargs) -> Tuple[int, Dict[str, str]]:
    logger.debug(f"Fetch HEAD from {url}")
    async with ClientSession() as session:
        async with session.head(url, **kwargs) as response:
            return response.status, dict(response.headers)


@asynccontextmanager
async def ClientSession() -> AsyncGenerator[aiohttp.ClientSession, None]:
    timeout = aiohttp.ClientTimeout(total=config.REQUESTS_TIMEOUT_SECONDS)
    headers = {"User-Agent": "poucave", **config.DEFAULT_REQUEST_HEADERS}
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        yield session


async def run_parallel(*futures, parallel_workers=config.REQUESTS_MAX_PARALLEL):
    """
    Consume a list of futures from several workers, and return the list of
    results.
    """
    # Parallel means at least 2 :)
    if len(futures) == 1:
        return [await futures[0]]

    async def worker(results_by_index, queue):
        while True:
            i, future = await queue.get()
            try:
                result = await future
                results_by_index[i] = result
            finally:
                # Mark item as processed.
                queue.task_done()

    # Results dict will be populated by workers.
    results_by_index = {}

    # Build the queue of futures to consume.
    queue = asyncio.Queue()
    for i, future in enumerate(futures):
        queue.put_nowait((i, future))

    # Instantiate workers that will consume the queue.
    worker_tasks = []
    for i in range(parallel_workers):
        task = asyncio.create_task(worker(results_by_index, queue))
        worker_tasks.append(task)

    # Wait for the queue to be processed completely.
    await queue.join()

    # Stop workers and wait until done.
    for task in worker_tasks:
        task.cancel()
    errors = await asyncio.gather(*worker_tasks, return_exceptions=True)

    # If some errors happened in the workers, re-raise here.
    real_errors = [e for e in errors if not isinstance(e, asyncio.CancelledError)]
    if len(real_errors) > 0:
        raise real_errors[0]

    # Return the results in the same order as the list of futures.
    return [results_by_index[k] for k in sorted(results_by_index.keys())]


def utcnow():
    # Tiny wrapper, used for mocking in tests.
    return datetime.now(timezone.utc)


def utcfromtimestamp(timestamp):
    return datetime.utcfromtimestamp(int(timestamp) / 1000).replace(tzinfo=timezone.utc)


def utcfromisoformat(iso8601):
    iso8601_tz = iso8601.replace("Z", "+00:00")
    return datetime.fromisoformat(iso8601_tz).replace(tzinfo=timezone.utc)


def render_checks(func):
    async def wrapper(request):
        # First, check that client requests supported output format.
        is_text_output = False
        accepts = ",".join(request.headers.getall("Accept", []))
        # Text is rendered only if explicitly specified.
        if "text/plain" in accepts:
            is_text_output = True
        elif "*/*" not in accepts and "application/json" not in accepts:
            # Client is requesting an unknown format.
            raise web.HTTPNotAcceptable()

        # Execute the decorated view.
        view_result = await func(request)

        # Render the response.
        results = [view_result] if isinstance(view_result, dict) else view_result
        all_success = all(c["success"] for c in results)
        status_code = 200 if all_success else 503

        if is_text_output:
            # Multiple checks can be rendered as text to be easier
            # to read (eg. in Pingdom "Root cause" UI).
            max_project_length = max([len(c["project"]) for c in results])
            max_name_length = max([len(c["name"]) for c in results])
            text = "\n".join(
                [
                    (
                        check["project"].ljust(max_project_length + 2)
                        + check["name"].ljust(max_name_length + 2)
                        + repr(check["success"])
                    )
                    for check in results
                ]
            )
            # Let's add some details about each failing check at the bottom.
            fields = (
                "url",
                "description",
                "documentation",
                "parameters",
                "data",
                "troubleshooting",
            )
            for check in [c for c in results if not c["success"]]:
                text += "\n" * 2 + "\n{project}  {name}\n".format(**check)

                check = {
                    **check,
                    "parameters": repr(check["parameters"]),
                    "data": json.dumps(check["data"], indent=2),
                }
                text += "\n".join(
                    chain(
                        *[
                            (
                                "  " + field.capitalize() + ":",
                                textwrap.indent(check[field], "    "),
                            )
                            for field in fields
                        ]
                    )
                )

            return web.Response(text=text, status=status_code)

        # Default rendering is JSON.
        return web.json_response(view_result, status=status_code)

    return wrapper


def cast_value(_type, value):
    # Get back to original type (eg. List[str] -> list)
    raw_type = getattr(_type, "__origin__", _type)
    if raw_type is Union:
        types = [getattr(t, "__origin__", t) for t in _type.__args__]
    else:
        types = [raw_type]
    # Cast to the first compatible type.
    while t := types.pop():
        try:
            return t(value)
        except (TypeError, ValueError):
            # Wrong parameter type. Raise if no more type to try.
            if len(types) == 0:
                raise


def extract_json(path, data):
    """
    A very simple and dumb implementation of JSONPath
    to extract sub-fields from the specified `data` using
    a `path`.

    >>> extract_json(".", 12)
    12
    >>> extract_json(".foo.0", {"foo": [1, 2]})
    1
    """
    steps = [s for s in path.split(".") if s]
    for step in steps:
        try:
            data = data[step]
        except (TypeError, KeyError) as ke:
            try:
                istep = int(step)
            except ValueError:
                raise ValueError(str(ke))  # Original error with step as string
            data = data[istep]
    return data


class BugTracker:
    """
    Fetch known bugs associated to checks.
    """

    HEAT_HOT_MAX_HOURS = 24
    HEAT_COLD_MIN_HOURS = 240

    def __init__(self, cache=None):
        self.cache = cache

    async def fetch(self, project: str, name: str) -> List[BugInfo]:
        """
        Fetch the list of bugs associated with the specified {project}/{name}.

        The list of bugs is fetched and catched for all checks, entries are filtered locally
        for this {project}/{name}.

        Bug must have configured ``SERVICE_NAME`` and ``ENV_NAME`` ``whiteboard`` in its field
        (eg. ``delivery-checks prod`` ).
        Use ``BUGTRACKER_API_KEY`` to include non public bugs in results.
        """
        if not config.BUGTRACKER_URL:
            return []

        cache_key = "bugtracker-list"
        async with self.cache.lock(cache_key) if self.cache else DummyLock():
            cached = self.cache.get(cache_key) if self.cache else None

            if cached is not None:
                _, expires = cached
                if expires < utcnow():
                    cached = None

            if cached is None:
                env_name = config.ENV_NAME or ""
                url = f"{config.BUGTRACKER_URL}/rest/bug?whiteboard={config.SERVICE_NAME} {env_name}"
                try:
                    buglist = await fetch_json(
                        url, headers={"X-BUGZILLA-API-KEY": config.BUGTRACKER_API_KEY}
                    )
                except aiohttp.ClientError as e:
                    logger.exception(e)
                    # Fallback to an empty list when fetching fails. Caching this fallback value
                    # will prevent every check to fail because of the bugtracker.
                    buglist = {"bugs": []}

                expires = utcnow() + timedelta(seconds=config.BUGTRACKER_TTL)
                cached = (buglist, expires)
                if self.cache:
                    self.cache.set(cache_key, cached)

        def _heat(datestr):
            dt = utcfromisoformat(datestr)
            age_hours = (utcnow() - dt).total_seconds() / 3600
            return (
                "hot"
                if age_hours < self.HEAT_HOT_MAX_HOURS
                else ("cold" if age_hours > self.HEAT_COLD_MIN_HOURS else "")
            )

        check = f"{project}/{name}"
        buglist, _ = cached
        return [
            {
                "id": r["id"],
                # Hide summary if any confidential group set.
                "summary": "" if len(r["groups"]) > 0 else r["summary"],
                "open": r["is_open"],
                "status": r["status"],
                "last_update": r["last_change_time"],
                "heat": _heat(r["last_change_time"]),
                "url": f"{config.BUGTRACKER_URL}/{r['id']}",
            }
            for r in sorted(
                # Show open bugs first, sorted by last changed descending.
                buglist["bugs"],
                key=lambda r: (r["is_open"], r["last_change_time"]),
                reverse=True,
            )
            if check in r["whiteboard"]
        ]


class EventEmitter:
    """
    A very simple event emitter.
    """

    def __init__(self):
        self.callbacks = {}

    def emit(self, event, payload=None):
        for cb in self.callbacks.get(event, []):
            cb(event, payload)

    def on(self, event, callback):
        self.callbacks.setdefault(event, []).append(callback)


class History:
    """
    Fetch history of values from the ``HISTORY_URL`` endpoint.

    Can be a Redash query URL that will return the following columns:
    "check", "t", "success", "scalar".

    Or a generic JSON endpoint that returns the history in the following format:

    ```
    {
      "data": [
        {"check": "crlite/age", "t": "2020-10-16 08:51:50", "success": true, "scalar": 42.1},
        {"check": "crlite/age", "t": "2020-10-16 08:51:50", "success": false, "scalar": 49.0},
        {"check": "crlite/age", "t": "2020-10-16 08:51:50", "success": true, "scalar": 41.3},
      ]
    }
    ```
    """

    def __init__(self, cache=None):
        self.cache = cache

    async def fetch(self, project, name):
        if not config.HISTORY_URL:
            return []

        cache_key = "scalar-history"
        async with self.cache.lock(cache_key) if self.cache else DummyLock():
            cached = self.cache.get(cache_key) if self.cache else None

            if cached is not None:
                history, expires = cached
                if expires < utcnow():
                    cached = None

            if cached is None:
                try:
                    resp = await fetch_json(config.HISTORY_URL)
                except aiohttp.ClientError as e:
                    logger.exception(e)
                    return [2]

                # Only a Redash source.
                rows = resp["query_result"]["data"]["rows"]

                history = {}
                for row in rows:
                    history.setdefault(row["check"], []).append(
                        {
                            "t": row["t"],
                            "success": row["success"],
                            "scalar": row["scalar"],
                        }
                    )

                expires = utcnow() + timedelta(seconds=config.HISTORY_TTL)
                cached = (history, expires)
                if self.cache:
                    self.cache.set(cache_key, cached)

        return history.get(f"{project}/{name}", [])
