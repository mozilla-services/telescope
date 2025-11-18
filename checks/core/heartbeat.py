"""
URL should return a 200 response.

The remote response is returned.
"""

import json

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import fetch_raw


EXPOSED_PARAMETERS = ["url", "expected_status"]


async def run(url: str, expected_status: int = 200) -> CheckResult:
    try:
        status, headers, body = await fetch_raw(url)
        success = status == expected_status
        text = body.decode("utf-8", errors="strict")
        if "application/json" in headers["Content-Type"]:
            data = json.loads(text) if text else None
        else:
            data = text
        return success, data
    except aiohttp.client_exceptions.ClientError as e:
        return False, str(e)
