import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

import aiohttp
import backoff

from poucave import config


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


retry_decorator = backoff.on_exception(
    backoff.expo,
    (aiohttp.ClientError, asyncio.TimeoutError),
    max_tries=config.REQUESTS_MAX_RETRIES,
)


@retry_decorator
async def fetch_json(*args, **kwargs):
    async with ClientSession() as session:
        async with session.get(*args, **kwargs) as response:
            return await response.json()


@asynccontextmanager
async def ClientSession():
    timeout = aiohttp.ClientTimeout(total=config.REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session
