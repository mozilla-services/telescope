"""
Inspect the state of maintenance of a list of Github repositories.
The number of opened pull requests whose latest activity (comment or update) is older than
`min_days_last_activity` should be under the specified maximum `max_opened_pulls`.
All the opened pull-requests should have received activity in the last `max_days_last_activity` days.

The number of total opened pull-requests along number of old ones is returned for each repository. Repositories with no opened pull-request are filtered.
"""
import logging
from typing import List

from telescope import config
from telescope.typings import CheckResult
from telescope.utils import (
    ClientSession,
    retry_decorator,
    run_parallel,
    utcfromisoformat,
    utcnow,
)


logger = logging.getLogger(__name__)

EXPOSED_PARAMETERS = [
    "max_days_last_activity",
    "min_days_last_activity",
    "max_opened_pulls",
]


async def pulls_info(session, repo):
    @retry_decorator
    async def fetch_page(url):
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if config.GITHUB_TOKEN:
            headers["Authorization"] = config.GITHUB_TOKEN
        logger.debug(f"Fetch list of pull requests from {url}")
        async with session.get(url, headers=headers, raise_for_status=True) as response:
            page = await response.json()
            next = response.links.get("next", {}).get("url")
            return page, next

    pulls = []
    url = f"https://api.github.com/repos/{repo}/pulls?state=open"
    while url:
        page, url = await fetch_page(url)
        pulls.extend(page)
    return pulls


async def run(
    repositories: List[str],
    max_opened_pulls: int = 7,
    min_days_last_activity: int = 7,
    max_days_last_activity: int = 45,
    ignore_with_labels: List[str] = ["blocked"],
) -> CheckResult:
    async with ClientSession() as session:
        futures = [pulls_info(session, repo) for repo in repositories]
        results = await run_parallel(*futures)

        now = utcnow()
        success = True
        infos = {}
        for repo, pulls in zip(repositories, results):
            not_blocked = [
                p
                for p in pulls
                if not p["draft"]
                and set(label["name"] for label in p["labels"]).isdisjoint(
                    set(ignore_with_labels)
                )
            ]
            opened = [utcfromisoformat(p["updated_at"]) for p in not_blocked]
            if len(opened) == 0:
                continue
            # Fail if opened PR hasn't received recent activity.
            age_pulls = [(now - dt).days for dt in opened]
            if max(age_pulls) > max_days_last_activity:
                success = False
            # Fail if too many opened PR.
            old_pulls = [age for age in age_pulls if age > min_days_last_activity]
            if len(old_pulls) > max_opened_pulls:
                success = False
            infos[repo] = {
                "pulls": {
                    "old": len(old_pulls),
                    "total": len(opened),
                }
            }
        # Sort results with repos with most old PRs first.
        sorted_by_old = dict(
            sorted(
                infos.items(), key=lambda item: item[1]["pulls"]["old"], reverse=True
            )
        )
        return success, sorted_by_old
