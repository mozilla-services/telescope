"""
The deployed `version` should be the latest tag of the specified `repo`.

The deployed version and the latest tag are returned.
"""
import os

import aiohttp

from poucave.typings import CheckResult


EXPOSED_PARAMETERS = ["server", "repo"]

REQUESTS_TIMEOUT_SECONDS = int(os.getenv("REQUESTS_TIMEOUT_SECONDS", 5))


async def run(server: str, repo: str) -> CheckResult:
    timeout = aiohttp.ClientTimeout(total=REQUESTS_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Server __version__ (see mozilla-services/Dockerflow)
        async with session.get(server + "/__version__") as response:
            version_info = await response.json()

        # Latest Github tag.
        async with session.get(
            f"https://api.github.com/repos/{repo}/releases"
        ) as response:
            releases = await response.json()

    deployed_version = version_info["version"]
    latest_tag = releases[0]["tag_name"]

    return (
        deployed_version == latest_tag,
        {"latest_tag": latest_tag, "deployed_version": deployed_version},
    )
