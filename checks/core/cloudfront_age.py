"""
The age of the cache response should be less than the specified maximum.

The age is returned.
"""
from poucave.typings import CheckResult
from poucave.utils import ClientSession


EXPOSED_PARAMETERS = ["url", "max_age"]


async def run(url: str, max_age: str) -> CheckResult:
    age = 0

    async with ClientSession() as session:
        async with session.head(url) as response:
            if "Age" in response.headers:
                age = int(response.headers["Age"])

            elif "Miss" not in response.headers.get("X-Cache", ""):
                raise ValueError("URL does not have CloudFront CDN headers")

    return age < max_age, age
