"""
The published PSL record should match the latest version available on Github.

The latest commit SHA of the http://github.com/publicsuffixlist/list repo and the
one published on Remote Settings are returned.
"""
from poucave.typings import CheckResult
from poucave.utils import ClientSession

from .utils import KintoClient

EXPOSED_PARAMETERS = ["server"]

COMMITS_URI = f"https://api.github.com/repos/publicsuffix/list/commits?path=public_suffix_list.dat"


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

    async with ClientSession() as session:
        # Upstream version (commit hash)
        async with session.get(COMMITS_URI) as response:
            commits = await response.json()

    latest_sha = commits[0]["sha"]

    return (
        latest_sha == published_sha,
        {
            "latest-sha": latest_sha,
            "to-review-sha": to_review_sha,
            "published-sha": published_sha,
        },
    )
