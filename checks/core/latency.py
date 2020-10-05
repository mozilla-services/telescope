"""
URL should respond under a certain number of milliseconds.

The latency is returned in milliseconds.
"""
import time

import aiohttp

from poucave.typings import CheckResult
from poucave.utils import ClientSession


EXPOSED_PARAMETERS = ["url", "max_milliseconds"]


async def run(url: str, max_milliseconds: int) -> CheckResult:
    async with ClientSession() as session:
        try:
            before = time.time()
            async with session.get(url):
                elapsed = round((time.time() - before) * 1000)
                return elapsed < max_milliseconds, elapsed
        except aiohttp.client_exceptions.ClientError as e:
            return False, str(e)
