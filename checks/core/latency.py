"""
URL should respond under a certain number of milliseconds.

The latency is returned in milliseconds.
"""

import time

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import fetch_head


EXPOSED_PARAMETERS = ["url", "max_milliseconds"]
DEFAULT_PLOT = "."


async def run(url: str, max_milliseconds: int) -> CheckResult:
    before = time.time()
    try:
        await fetch_head(url)
        elapsed = round((time.time() - before) * 1000)
        return elapsed < max_milliseconds, elapsed
    except aiohttp.client_exceptions.ClientError as e:
        return False, str(e)
