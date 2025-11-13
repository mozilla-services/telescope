"""
The Remote Settings over git commit should be the latest commit of the specified `repo`.

The git reader commit and the repo latest commit details are returned.
"""

from telescope.typings import CheckResult
from telescope.utils import fetch_json, utcfromisoformat, utcnow


EXPOSED_PARAMETERS = ["server", "repo", "lag_margin_seconds"]

BRANCH = "v1/common"


async def run(
    server: str, repo: str, branch: str = "main", lag_margin_seconds: int = 3600
) -> CheckResult:
    server_info = await fetch_json(server + "/")
    git_info = server_info["git"]["common"]
    source_commit = git_info["id"]

    # Latest Github commit.
    details = await fetch_json(f"https://api.github.com/repos/{repo}/branches/{BRANCH}")
    latest_sha = details["commit"]["sha"]
    latest_datetime = details["commit"]["commit"]["author"]["date"]

    is_recent = (
        utcnow() - utcfromisoformat(latest_datetime)
    ).total_seconds() < lag_margin_seconds

    return (
        is_recent or source_commit == latest_sha,
        {
            "latest_commit": {
                "sha": latest_sha,
                "date": latest_datetime,
            },
            "source_commit": {
                "sha": source_commit,
                "date": git_info["datetime"],
            },
        },
    )
