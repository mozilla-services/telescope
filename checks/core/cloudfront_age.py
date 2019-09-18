"""
"""
import os

import aiohttp

from poucave.typings import CheckResult


EXPOSED_PARAMETERS = ["url", "max_age"]

REQUESTS_TIMEOUT_SECONDS = int(os.getenv("REQUESTS_TIMEOUT_SECONDS", 5))


async def run(url: str, max_age: str) -> CheckResult:
    age = 0

    timeout = aiohttp.ClientTimeout(total=REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.head(url) as response:
            if "Age" in response.headers:
                age = int(response.headers["Age"])

            elif "Miss" not in response.headers.get("X-Cache", ""):
                raise ValueError("URL does not have CloudFront CDN headers")

    return age < max_age, age
