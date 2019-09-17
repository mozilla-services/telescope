import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional


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


async def run_parallel(func, input_args):
    loop = asyncio.get_event_loop()
    futures = [loop.run_in_executor(None, func, *args) for args in input_args]
    results = await asyncio.gather(*futures)
    return results
