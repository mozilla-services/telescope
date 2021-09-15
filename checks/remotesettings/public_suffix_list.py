"""
The published PSL record should match the latest version available on Github.

The latest commit SHA of the https://github.com/publicsuffix/list repo and the
one published on Remote Settings are returned.
"""
from telescope.typings import CheckResult
from telescope.utils import fetch_json

from .utils import KintoClient


EXPOSED_PARAMETERS = ["server"]

COMMITS_URI = (
    "https://api.github.com/repos/publicsuffix/list/commits?path=public_suffix_list.dat"
)


async def run(server: str) -> CheckResult:
    client = KintoClient(server_url=server)

    published_record = await client.get_record(
        bucket="main", collection="public-suffix-list", id="tld-dafsa"
    )
    published_sha = published_record["data"]["commit-hash"]

    to_review_record = await client.get_record(
        bucket="main-preview", collection="public-suffix-list", id="tld-dafsa"
    )
    to_review_sha = to_review_record["data"]["commit-hash"]

    # Upstream version (commit hash)
    commits = await fetch_json(COMMITS_URI)

    latest_sha = commits[0]["sha"]

    return (
        latest_sha == published_sha,
        {
            "latest-sha": latest_sha,
            "to-review-sha": to_review_sha,
            "published-sha": published_sha,
        },
    )
