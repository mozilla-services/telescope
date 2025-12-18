"""
Latest version and build from ReadTheDocs must match Github.

The details of each is returned.
"""

from bs4 import BeautifulSoup

from telescope.typings import CheckResult
from telescope.utils import fetch_json, fetch_text, utcfromisoformat, utcnow


EXPOSED_PARAMETERS = ["repo", "rtd_slug"]


async def run(
    repo: str,
    rtd_slug: str,
    rtd_token: str | None = None,
    branch: str = "main",
    lag_margin_seconds: int = 3600,
) -> CheckResult:
    builds_page = await fetch_text(
        f"https://app.readthedocs.org/projects/{rtd_slug}/builds/",
        raise_for_status=True,
    )
    soup = BeautifulSoup(builds_page, "html.parser")
    # Read the main table.
    main_table = soup.find("table")
    assert main_table is not None, "Could not find builds table on ReadTheDocs page"
    rows = main_table.find_all("tr")
    assert rows, "Could not find any rows in builds table"
    # Find the latest build commit SHA.
    latest_build = None
    for row in rows[:5]:  # Check only the first 5 rows to find the latest build
        links_hrefs = [link.get("href", "") for link in row.find_all("a")]
        commit_links = [link for link in links_hrefs if "/commit/" in link]
        if commit_links:
            latest_build = commit_links[0].split("/commit/")[1]
            break
    assert latest_build is not None, "Could not find latest build commit SHA"

    # Fetch latest commit details from GitHub.
    details = await fetch_json(f"https://api.github.com/repos/{repo}/branches/{branch}")
    latest_sha = details["commit"]["sha"]
    latest_datetime = details["commit"]["commit"]["author"]["date"]

    is_recent = (
        utcnow() - utcfromisoformat(latest_datetime)
    ).total_seconds() < lag_margin_seconds

    return (
        is_recent or (latest_build == latest_sha),
        {
            "github": {
                "latest_sha": latest_sha,
            },
            "readthedocs": {
                "latest_build": latest_build,
            },
        },
    )
