"""
URL should respond under a certain number of milliseconds.

The latency is returned in milliseconds.
"""

import time

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import REQUEST_LIMIT, ClientSession


EXPOSED_PARAMETERS = ["url", "max_milliseconds"]
DEFAULT_PLOT = "."


async def run(url: str, max_milliseconds: int) -> CheckResult:
    async with ClientSession() as session:
        async with REQUEST_LIMIT:
            try:
                before = time.time()
                async with session.get(url):
                    elapsed = round((time.time() - before) * 1000)
                    return elapsed < max_milliseconds, elapsed
            except aiohttp.client_exceptions.ClientError as e:
                return False, str(e)
