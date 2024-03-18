"""
URL should return a 200 response.

The remote response is returned.
"""

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import ClientSession, retry_decorator


EXPOSED_PARAMETERS = ["url", "expected_status"]


@retry_decorator
async def run(url: str, expected_status: int = 200) -> CheckResult:
    async with ClientSession() as session:
        try:
            async with session.get(url) as response:
                success = response.status == expected_status
                if "application/json" in response.headers["Content-Type"]:
                    data = await response.json()
                else:
                    data = await response.text()
                return success, data
        except aiohttp.client_exceptions.ClientError as e:
            return False, str(e)
