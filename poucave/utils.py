import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional, TypeVar, Generator

import aiohttp
import backoff

from poucave import config


logger = logging.getLogger(__name__)


class Cache:
    def __init__(self):
        self._content: Dict[str, Tuple[datetime, Any]] = {}

    def set(self, key: str, value: Any, ttl: int):
        # Store expiration datetime along data.
        expires = datetime.now() + timedelta(seconds=ttl)
        self._content[key] = (expires, value)

    def get(self, key: str) -> Optional[Any]:
        try:
            expires, cached = self._content[key]
            # Check if cached data has expired.
            if datetime.now() > expires:
                del self._content[key]
                return None
            # Cached valid data.
            return cached

        except KeyError:
            # Unknown key.
            return None


REDASH_URI = "https://sql.telemetry.mozilla.org/api/queries/{}/results.json?api_key={}"


async def fetch_redash(query_id, api_key):
    redash_uri = REDASH_URI.format(query_id, api_key)
    body = await fetch_json(redash_uri)
    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    return rows


retry_decorator = backoff.on_exception(
    backoff.expo,
    (aiohttp.ClientError, asyncio.TimeoutError),
    max_tries=config.REQUESTS_MAX_RETRIES,
)


@retry_decorator
async def fetch_json(url, *args, **kwargs) -> object:
    logger.debug(f"Fetch JSON from {url}")
    async with ClientSession() as session:
        async with session.get(url, *args, **kwargs) as response:
            return await response.json()


@retry_decorator
async def fetch_text(url, *args, **kwargs) -> str:
    logger.debug(f"Fetch text from {url}")
    async with ClientSession() as session:
        async with session.get(url, *args, **kwargs) as response:
            return await response.text()


@retry_decorator
async def fetch_head(url, *args, **kwargs) -> Tuple[int, Dict[str, str]]:
    logger.debug(f"Fetch HEAD from {url}")
    async with ClientSession() as session:
        async with session.head(url, *args, **kwargs) as response:
            return response.status, dict(response.headers)


@asynccontextmanager
async def ClientSession():
    timeout = aiohttp.ClientTimeout(total=config.REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session


T = TypeVar("T")


def chunker(seq: List[T], size: int) -> Generator[List[T], None, None]:
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))  # noqa
