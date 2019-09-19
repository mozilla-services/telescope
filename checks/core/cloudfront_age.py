"""
The age of the cache response should be less than the specified maximum.

The age is returned.
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_head


EXPOSED_PARAMETERS = ["url", "max_age"]


async def run(url: str, max_age: str) -> CheckResult:
    age = 0

    _, headers = await fetch_head(url)

    if "Age" in headers:
        age = int(headers["Age"])

    elif "Miss" not in headers.get("X-Cache", ""):
        raise ValueError("URL does not have CloudFront CDN headers")

    return age < max_age, age
