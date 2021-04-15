"""
Inspect the state of maintenance of a list of Github repositories.
The number of opened pull requests whose latest activity (comment or update) is older than
`ignore_last_days` should be under the specified maximum `max_opened_pulls`.

The number of total opened pull-requests along number of old ones is returned for each repository. Repositories with no opened pull-request are filtered.
"""
import logging
import os
from typing import List

from poucave.typings import CheckResult
from poucave.utils import (
    ClientSession,
    retry_decorator,
    run_parallel,
    utcfromisoformat,
    utcnow,
)


logger = logging.getLogger(__name__)

EXPOSED_PARAMETERS = ["ignore_last_days", "max_opened_pulls"]


async def pulls_info(session, repo: str) -> int:
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}" if token else "",
    }
    # Fetch list of pull-requests (drafts included).
    url = f"https://api.github.com/repos/{repo}/pulls?state=open"
    logger.debug(f"Fetch list of pull requests from {url}")
    async with session.get(url, headers=headers, raise_for_status=True) as response:
        all_pulls = await response.json()

    pulls = []
    for pull in all_pulls:
        if pull["draft"]:
            continue

        # Fetch list of recent comments.
        comments_url = pull["review_comments_url"] + "?sort=updated_at&direction=desc"
        async with session.get(
            comments_url, headers=headers, raise_for_status=True
        ) as response:
            all_comments = await response.json()
        if len(all_comments) > 0:
            date_latest_activity = all_comments[0]["updated_at"]
        else:
            date_latest_activity = pull["updated_at"]

        pulls.append(utcfromisoformat(date_latest_activity))

    return sorted(pulls)


@retry_decorator
async def run(
    repositories: List[str], max_opened_pulls: int = 7, ignore_last_days: int = 7
) -> CheckResult:
    async with ClientSession() as session:
        futures = [pulls_info(session, repo) for repo in repositories]
        results = await run_parallel(*futures)

        success = True
        infos = {}
        for (repo, pulls) in zip(repositories, results):
            if len(pulls) == 0:
                continue
            old_pulls = [dt for dt in pulls if (utcnow() - dt).days > ignore_last_days]
            infos[repo] = {
                "pulls": {
                    "old": len(old_pulls),
                    "total": len(pulls),
                }
            }
            if len(old_pulls) > max_opened_pulls:
                success = False

        sorted_by_old = dict(
            sorted(
                infos.items(), key=lambda item: item[1]["pulls"]["old"], reverse=True
            )
        )
        return success, sorted_by_old
