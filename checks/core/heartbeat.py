"""
URL should return a 200 response.

The remote response is returned.
"""
import aiohttp

from poucave.typings import CheckResult
from poucave.utils import ClientSession, retry_decorator


EXPOSED_PARAMETERS = ["url", "expected_status"]


@retry_decorator
async def run(url: str, expected_status: int = 200) -> CheckResult:
    async with ClientSession() as session:
        try:
            async with session.get(url) as response:
                success = response.status == expected_status
                return success, await response.json()
        except aiohttp.client_exceptions.ClientError as e:
            return False, str(e)
