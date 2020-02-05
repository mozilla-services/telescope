import asyncio
import json
import logging
import textwrap
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from itertools import chain
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiohttp
import backoff
from aiohttp import web

from poucave import config


logger = logging.getLogger(__name__)


class Cache:
    def __init__(self):
        self._content: Dict[str, Any] = {}

    def set(self, key: str, value: Any):
        self._content[key] = value

    def get(self, key: str) -> Optional[Any]:
        try:
            cached = self._content[key]
            return cached

        except KeyError:
            # Unknown key.
            return None


REDASH_URI = "https://sql.telemetry.mozilla.org/api/queries/{}/results.json?api_key={}"


async def fetch_redash(query_id: int, api_key: str) -> List[Dict]:
    redash_uri = REDASH_URI.format(query_id, api_key)
    body = await fetch_json(redash_uri)
    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
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


def render_checks(func):
    async def wrapper(request):
        # First, check that client requests supported output format.
        is_text_output = False
        # Several Accept headers can be specified, and each of them can have
        # comma-separated values (eg. `Accept: text/html,application/xhtml+xml`).
        accepts = set(
            chain(*[a.split(",") for a in request.headers.getall("Accept", [])])
        )
        # Also some values can specify a "quantity" value that we can ignore here (eg. `*/*;q=0.8`)
        accepts = {a.split(";")[0] for a in accepts}
        # Text is rendered only if explicitly specified.
        if accepts.intersection({"text/*", "text/plain"}):
            is_text_output = True
        elif not accepts.intersection({"*/*", "application/json"}):
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
