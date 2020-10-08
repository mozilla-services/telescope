"""
The age of the cache response should be less than the specified maximum.

The age is returned.
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_head


EXPOSED_PARAMETERS = ["url", "max_age"]
DEFAULT_PLOT = "."


async def run(url: str, max_age: int) -> CheckResult:
    age = 0

    _, headers = await fetch_head(url)

    if "X-Cache" not in headers:
        raise ValueError("URL does not have CloudFront CDN headers")

    age = int(headers.get("Age", 0))

    return age < max_age, age
