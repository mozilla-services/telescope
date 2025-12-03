import asyncio
import email.utils
import functools
import hashlib
import json
import logging
import textwrap
import threading
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from itertools import chain
from typing import Any, AsyncGenerator, Dict, List, Optional, Protocol, Tuple, Union

import aiohttp
import backoff
from aiohttp import web
from google.cloud import bigquery
from redis.asyncio import Redis

from telescope import config
from telescope.typings import BugInfo


logger = logging.getLogger(__name__)
threadlocal = threading.local()


class InstrumentedSemaphore(asyncio.Semaphore):
    """
    A semaphore that can be instrumented with a gauge/counter metric.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metric = None

    @property
    def metric(self):
        return self._metric

    @metric.setter
    def metric(self, value):
        self._metric = value

    async def acquire(self):
        if self.metric:
            self.metric.inc()
        return await super().acquire()

    def release(self):
        super().release()
        if self.metric:
            self.metric.dec()


# global semaphore to restrict parallel http requests
REQUEST_LIMIT = InstrumentedSemaphore(config.LIMIT_REQUEST_CONCURRENCY)
WORKER_LIMIT = InstrumentedSemaphore(config.LIMIT_WORKER_CONCURRENCY)


def setup_metrics(existing_metrics: Dict[str, Any]):
    """
    Link the semaphores to the existing appropriate metric.
    """
    REQUEST_LIMIT.metric = existing_metrics.get("semaphore_acquired_total").labels(  # type: ignore
        "request"
    )
    WORKER_LIMIT.metric = existing_metrics.get("semaphore_acquired_total").labels(  # type: ignore
        "worker"
    )


def limit_request_concurrency(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        async with REQUEST_LIMIT:
            return await func(*args, **kwargs)

    return wrapper


class Cache(Protocol):
    def lock(self, key: str):
        """Return an async-compatible context manager for locking 'key'."""
        ...

    async def set(self, key: str, value: Any, ttl: int):
        """Set a value with TTL in seconds."""
        ...

    async def get(self, key: str) -> Optional[Any]:
        """Get a value or None if missing/expired."""
        ...

    async def ping(self) -> bool:
        """Return True if the cache is reachable, False otherwise."""
        try:
            await self.set("__ping__", 1, ttl=10)
            value = await self.get("__ping__")
            if value != 1:
                raise Exception("Cache ping returned wrong value")
            return True
        except Exception:
            logger.exception("Cache ping failed")
            return False


class InMemoryCache(Cache):
    def __init__(self):
        self._content: dict[str, tuple[datetime, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, key: str):
        return self._locks.setdefault(key, asyncio.Lock())

    async def set(self, key: str, value: Any, ttl: int):
        expires = utcnow() + timedelta(seconds=ttl)
        self._content[key] = expires, value

    async def get(self, key: str) -> Optional[Any]:
        try:
            expires, value = self._content[key]
            if expires < utcnow():
                del self._content[key]
                return None
            return value

        except KeyError:
            # Unknown key.
            return None


class RedisCache(Cache):
    version = "v1"

    def __init__(self, url: str, key_prefix: str):
        self._r = Redis.from_url(url)
        self.prefix = f"{key_prefix}:{self.version}:"

    def _key(self, key: str) -> str:
        """Generate a safe Redis key from an arbitrary string."""
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()  # nosec
        return f"{self.prefix}:{digest}"

    def lock(self, key: str):
        return self._r.lock(
            name=f"{self._key(key)}:lock",
            # If the lock is not released (process crash, etc.), it will auto-expire after timeout.
            timeout=config.REDIS_LOCK_TIMEOUT_SECONDS,
            # How long to wait to acquire the lock before giving up.
            # It should be higher than the max expected duration of the run.
            blocking_timeout=config.REDIS_LOCK_BLOCKING_TIMEOUT_SECONDS,
        )

    async def set(self, key: str, value: Any, ttl: int):
        data = json.dumps(value)
        await self._r.set(f"{self._key(key)}:data", data, ex=ttl)

    async def get(self, key: str) -> Optional[Any]:
        data = await self._r.get(f"{self._key(key)}:data")
        if data is None:
            return None
        return json.loads(data)


class DummyLock:
    def __await__(self):
        yield

    def __aenter__(self):
        return self

    def __aexit__(self, *args):
        return self


retry_decorator = backoff.on_exception(
    backoff.expo,
    (aiohttp.ClientError, asyncio.TimeoutError),
    max_tries=config.REQUESTS_MAX_RETRIES + 1,  # + 1 because REtries.
)


def strip_authz_on_exception(func):
    """
    Decorator for async functions that may raise aiohttp exceptions.
    If an exception has a .request_info with headers containing 'Authorization',
    the header is replaced with '[secure]' to prevent leaking secrets.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            if request_info := getattr(exc, "request_info", None):
                exc.request_info = type(
                    "RequestInfo",
                    (),
                    {
                        **request_info.__dict__,
                        "headers": {
                            k: ("[secure]" if k == "Authorization" else v)
                            for k, v in request_info.headers.items()
                        },
                    },
                )
            raise

    return wrapper


@limit_request_concurrency
@strip_authz_on_exception
@retry_decorator
async def fetch_json(url: str, **kwargs) -> Any:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch JSON from '{human_url}'")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return await response.json()


@limit_request_concurrency
@strip_authz_on_exception
@retry_decorator
async def fetch_text(url: str, **kwargs) -> str:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch text from '{human_url}'")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return await response.text()


@limit_request_concurrency
@strip_authz_on_exception
@retry_decorator
async def fetch_head(url: str, **kwargs) -> Tuple[int, Dict[str, str]]:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch HEAD from '{human_url}'")
    async with ClientSession() as session:
        async with session.head(url, **kwargs) as response:
            return response.status, dict(response.headers)


@limit_request_concurrency
@strip_authz_on_exception
@retry_decorator
async def fetch_raw(url: str, **kwargs) -> tuple[int, dict[str, str], bytes]:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch from '{human_url}'")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            body = await response.read()
            return response.status, dict(response.headers), body


@asynccontextmanager
async def ClientSession() -> AsyncGenerator[aiohttp.ClientSession, None]:
    timeout = aiohttp.ClientTimeout(total=config.REQUESTS_TIMEOUT_SECONDS)
    headers = {"User-Agent": "telescope", **config.DEFAULT_REQUEST_HEADERS}
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        yield session


async def run_parallel(*futures):
    """
    Consume a list of futures from several workers, and return the list of
    results.
    """
    results_by_index = {}
    for i, future in enumerate(futures):
        async with WORKER_LIMIT:
            results_by_index[i] = await future

    return [results_by_index[k] for k in sorted(results_by_index.keys())]


def utcnow():
    # Tiny wrapper, used for mocking in tests.
    return datetime.now(timezone.utc)


def utcfromtimestamp(timestamp):
    return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)


def utcfromisoformat(iso8601):
    iso8601_tz = iso8601.replace("Z", "+00:00")
    return datetime.fromisoformat(iso8601_tz).replace(tzinfo=timezone.utc)


def utcfromhttpdate(httpdate):
    return email.utils.parsedate_to_datetime(httpdate).replace(tzinfo=timezone.utc)


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


def csv_quoted(values):
    """
    >>> csv_quoted([1, 2, 3])
    "'1','2','3'"
    """
    return ",".join(f"'{v}'" for v in values)


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
            try:
                data = data[istep]
            except IndexError:
                raise ValueError(str(ke))  # Original error with step as string
    return data


class BugTracker:
    """
    Fetch known bugs associated to checks.
    """

    HEAT_HOT_MAX_HOURS = 240
    HEAT_COLD_MIN_HOURS = 720

    def __init__(self, cache=None):
        self.cache = cache

    async def ping(self) -> bool:
        """
        Returns True if we can succesfully hit and parse the /rest/whoami endpoint.
        """
        url = f"{config.BUGTRACKER_URL}/rest/whoami"
        try:
            response = await fetch_json(
                url, headers={"X-BUGZILLA-API-KEY": config.BUGTRACKER_API_KEY}
            )
            return "name" in response
        except Exception as e:
            logger.exception(e)
            return False

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
            buglist = await self.cache.get(cache_key) if self.cache else None

            if buglist is None:
                # Fallback to an empty list when fetching fails. Caching this fallback value
                # will prevent every check to fail because of the bugtracker.
                default_buglist: Dict = {"bugs": []}
                env_name = config.ENV_NAME or ""
                url = f"{config.BUGTRACKER_URL}/rest/bug?whiteboard={config.SERVICE_NAME} {env_name}"
                try:
                    response = await fetch_json(
                        url, headers={"X-BUGZILLA-API-KEY": config.BUGTRACKER_API_KEY}
                    )
                    buglist = response if "bugs" in response else default_buglist
                except aiohttp.ClientError as e:
                    logger.exception(e)
                    buglist = default_buglist

                if self.cache:
                    await self.cache.set(cache_key, buglist, ttl=config.BUGTRACKER_TTL)

        def _heat(datestr):
            dt = utcfromisoformat(datestr)
            age_hours = (utcnow() - dt).total_seconds() / 3600
            return (
                "hot"
                if age_hours < self.HEAT_HOT_MAX_HOURS
                else ("cold" if age_hours > self.HEAT_COLD_MIN_HOURS else "")
            )

        check = f"{project}/{name}"
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


async def fetch_bigquery(sql):  # pragma: nocover
    """
    Execute specified SQL and return rows.
    """

    def job():
        bqclient = getattr(threadlocal, "bqclient", None)

        if bqclient is None:
            # Reads credentials from env and connects.
            bqclient = bigquery.Client(project=config.HISTORY_PROJECT_ID)

            setattr(threadlocal, "bqclient", bqclient)

        query = sql.format(__project__=bqclient.project, __env__=config.ENV_NAME)

        query_job = bqclient.query(query)  # API request
        rows = query_job.result()  # Waits for query to finish

        return rows

    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, lambda: job())
    # Consume the iterator into a list.
    return list(r for r in rows)


class History:
    """
    Fetch history of values from a table stored in Google BigQuery.
    """

    def __init__(self, cache=None):
        self.cache = cache

    async def fetch(self, project, name):
        cache_key = "scalar-history"
        async with self.cache.lock(cache_key) if self.cache else DummyLock():
            history = await self.cache.get(cache_key) if self.cache else None

            if history is None:
                rows = []
                if config.HISTORY_DAYS > 0:
                    try:
                        query = self.QUERY.format(interval=config.HISTORY_DAYS)
                        rows = await fetch_bigquery(query)
                    except Exception as e:
                        logger.exception(e)

                history = {}
                for row in rows:
                    history.setdefault(row.check, []).append(
                        {
                            "t": row.t,
                            "success": row.success,
                            "scalar": float(row.scalar),
                        }
                    )

                if self.cache:
                    await self.cache.set(cache_key, history, ttl=config.HISTORY_TTL)

        return history.get(f"{project}/{name}", [])

    QUERY = r"""
        WITH last_days AS (
            SELECT
              CONCAT(jsonPayload.fields.project, '/', jsonPayload.fields.check) AS check,
              TIMESTAMP(jsonPayload.fields.time) AS t,
              jsonPayload.fields.success,
              jsonPayload.fields.plot
            FROM `{{__project__}}.gke_telescope_{{__env__}}_log.stdout`
            WHERE jsonPayload.fields.plot IS NOT NULL
              AND TIMESTAMP_TRUNC(timestamp, DAY) IN (
                SELECT TIMESTAMP(last_days)
                FROM
                  UNNEST(
                    GENERATE_DATE_ARRAY(DATE_SUB(CURRENT_DATE(), INTERVAL {interval} DAY), CURRENT_DATE())
                  ) AS last_days
              )
            ORDER BY 1, 2
        ),
        plotgroups AS (
            SELECT
              check,
              t,
              success,
              plot,
              -- This will allow us to remove redundant plot adjacent values, by grouping rows on this column
              ROW_NUMBER() OVER(ORDER BY check, t) - ROW_NUMBER() OVER(PARTITION BY check, CAST(plot AS STRING) ORDER BY check, t) AS plotgroup
            FROM last_days
            ORDER BY check, t
        )
        SELECT
          check,
          FORMAT_TIMESTAMP('%F %T', MAX(t)) AS t, -- end of period
          LOGICAL_OR(success) AS success, -- agg func is no-op here
          ROUND(CAST(MAX(plot) AS FLOAT64), 2) AS scalar -- agg func is no-op here
        FROM plotgroups
        GROUP BY check, plotgroup
        ORDER BY check, 2
    """
