"""
The deployed `version` should be the latest tag of the specified `repo`.

The deployed version and the latest tag are returned.
"""
from poucave.typings import CheckResult
from poucave.utils import fetch_json

EXPOSED_PARAMETERS = ["server", "repo"]


async def run(server: str, repo: str) -> CheckResult:
    # Server __version__ (see mozilla-services/Dockerflow)
    version_info = await fetch_json(server + "/__version__")

    # Latest Github tag.
    releases = await fetch_json(f"https://api.github.com/repos/{repo}/releases")

    deployed_version = version_info["version"]
    latest_tag = releases[0]["tag_name"]

    return (
        deployed_version == latest_tag,
        {"latest_tag": latest_tag, "deployed_version": deployed_version},
    )
