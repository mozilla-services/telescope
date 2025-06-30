"""
The deployed `commit` should be the latest commit of the specified `branch` on the specified `repo`.

The deployed commit and the branch latest commit details are returned.
"""

from telescope.typings import CheckResult
from telescope.utils import fetch_json, utcfromisoformat, utcnow


EXPOSED_PARAMETERS = ["server", "repo", "branch", "lag_margin_seconds"]


async def run(
    server: str, repo: str, branch: str = "main", lag_margin_seconds: int = 3600
) -> CheckResult:
    # Server __version__ (see mozilla-services/Dockerflow)
    version_info = await fetch_json(server + "/__version__")
    deployed_commit = version_info["commit"]

    # Latest Github tag.
    details = await fetch_json(f"https://api.github.com/repos/{repo}/branches/{branch}")
    latest_sha = details["commit"]["sha"]
    latest_author = details["commit"]["author"]["login"]
    latest_message = details["commit"]["commit"]["message"].splitlines()[0]
    latest_datetime = details["commit"]["commit"]["author"]["date"]

    is_recent = (
        utcnow() - utcfromisoformat(latest_datetime)
    ).total_seconds() < lag_margin_seconds

    return (
        is_recent or deployed_commit == latest_sha,
        {
            "latest_commit": {
                "sha": latest_sha,
                "author": latest_author,
                "message": latest_message,
                "date": latest_datetime,
            },
            "deployed_commit": deployed_commit,
        },
    )
