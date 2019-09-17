"""
The published PSL record should match the latest version available on Github.

The latest commit SHA of the http://github.com/publicsuffixlist/list repo and the
one published on Remote Settings are returned.
"""
import os

import aiohttp

from poucave.typings import CheckResult
from .utils import KintoClient as Client

EXPOSED_PARAMETERS = ["server"]

REQUESTS_TIMEOUT_SECONDS = int(os.getenv("REQUESTS_TIMEOUT_SECONDS", 5))

COMMITS_URI = f"https://api.github.com/repos/publicsuffix/list/commits?path=public_suffix_list.dat"


async def run(server: str) -> CheckResult:
    client = Client(server_url=server)

    record = client.get_record(
        bucket="main", collection="public-suffix-list", id="tld-dafsa"
    )
    published_sha = record["data"]["commit-hash"]

    timeout = aiohttp.ClientTimeout(total=REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Upstream version (commit hash)
        async with session.get(COMMITS_URI) as response:
            commits = await response.json()

    latest_sha = commits[0]["sha"]

    return (
        latest_sha == published_sha,
        {"latest-sha": latest_sha, "published-sha": published_sha},
    )
