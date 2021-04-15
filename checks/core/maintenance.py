"""
Inspect a list of Github repositories, the number of opened
pull requests should be under the specified maximum.

The number of opened pull-requests for each repository is returned.
"""
import os
from typing import List

from poucave.typings import CheckResult
from poucave.utils import ClientSession, retry_decorator, run_parallel


EXPOSED_PARAMETERS = ["max_opened_pulls"]


async def count_pulls(session, repo: str) -> int:
    token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}" if token else "",
    }
    async with session.get(url, headers=headers) as response:
        data = await response.json()
    return len(data)


@retry_decorator
async def run(repositories: List[str], max_opened_pulls: int = 10) -> CheckResult:
    async with ClientSession() as session:
        futures = [count_pulls(session, repo) for repo in repositories]
        results = await run_parallel(*futures)
        zipped = zip(repositories, results)
        repos_over = {
            repo: count for (repo, count) in zipped if count > max_opened_pulls
        }
        return len(repos_over) == 0, {"pulls": zipped}
