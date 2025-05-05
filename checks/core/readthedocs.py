"""
Latest version and build from ReadTheDocs must match Github.

The details of each is returned.
"""

from telescope.typings import CheckResult
from telescope.utils import fetch_json, utcfromisoformat, utcnow


EXPOSED_PARAMETERS = ["repo", "rtd_slug"]


async def run(
    repo: str,
    rtd_slug: str,
    rtd_token: str,
    branch: str = "main",
    lag_margin_seconds: int = 3600,
) -> CheckResult:
    rtd_headers = {"Authorization": f"Token {rtd_token}"}

    rtd_versions = await fetch_json(
        f"https://readthedocs.org/api/v3/projects/{rtd_slug}/versions/",
        headers=rtd_headers,
    )
    latest_version = rtd_versions["results"][0]["slug"]
    rtd_builds = await fetch_json(
        f"https://readthedocs.org/api/v3/projects/{rtd_slug}/builds/",
        headers=rtd_headers,
    )
    latest_build_info = rtd_builds["results"][0]
    latest_build = (
        latest_build_info["commit"]
        if latest_build_info["success"]
        else latest_build_info["error"]
    )

    details = await fetch_json(f"https://api.github.com/repos/{repo}/branches/{branch}")
    latest_sha = details["commit"]["sha"]
    latest_datetime = details["commit"]["commit"]["author"]["date"]
    releases = await fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    latest_tag = releases["tag_name"]

    is_recent = (
        utcnow() - utcfromisoformat(latest_datetime)
    ).seconds < lag_margin_seconds

    return (
        is_recent or (latest_build == latest_sha and latest_version == latest_tag),
        {
            "github": {
                "latest_sha": latest_sha,
                "latest_version": latest_tag,
            },
            "readthedocs": {
                "lastest_build": latest_build,
                "latest_version": latest_version,
            },
        },
    )
