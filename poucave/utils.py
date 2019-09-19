from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

import aiohttp


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

    async with aiohttp.ClientSession() as session:
        async with session.get(redash_uri) as response:
            body = await response.json()

    query_result = body["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    return rows
