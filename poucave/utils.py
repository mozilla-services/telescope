from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

import aiohttp

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


@asynccontextmanager
async def ClientSession():
    timeout = aiohttp.ClientTimeout(total=config.REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session
