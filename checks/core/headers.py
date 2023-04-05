"""
Check that certain response headers are received when certain requests headers are sent.

Returns missing headers by URL if failing.
"""
import logging

from telescope.typings import CheckResult
from telescope.utils import fetch_head, run_parallel


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = [
    "urls",
    "request_headers",
    "response_headers",
]


async def run(
    urls: list[str],
    request_headers: dict[str, str],
    response_headers: dict[str, str],
) -> CheckResult:
    futures = [fetch_head(url, headers=request_headers) for url in urls]
    results = await run_parallel(*futures)

    missing: dict[str, dict[str, str]] = {}
    for url, (status, headers) in zip(urls, results):
        for name, value in response_headers.items():
            if name not in headers or (value and headers[name] != value):
                missing.setdefault(url, {})[name] = value

    """
    {
        "https://url.org": {
            "Content-Encoding": "gzip"
        }
    }
    """
    success = not missing
    return success, missing
