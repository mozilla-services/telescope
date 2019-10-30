"""
The deployed `version` should be the latest tag of the specified `repo`.

The deployed version and the latest tag are returned.
"""
from poucave.typings import CheckResult
from poucave.utils import ClientSession, fetch_json, retry_decorator

EXPOSED_PARAMETERS = ["server", "repo"]


@retry_decorator
async def fetch_latest_tag(owner: str, name: str, token: str) -> str:
    url = "https://api.github.com/graphql"
    data = {
        "query": """
            query {
              repository(owner: "%s", name: "%s") {
                refs(refPrefix: "refs/tags/", last: 1, orderBy: {field: TAG_COMMIT_DATE, direction: ASC}) {
                  edges {
                    node { name }
                  }
                }
              }
            }
        """
        % (owner, name)
    }
    async with ClientSession() as session:
        async with session.post(
            url,
            json=data,
            headers={"Authorization": f"Bearer {token}"},
            raise_for_status=True,
        ) as response:
            resp = await response.json()
            # {'data': {'repository': {'refs': {'edges': [{'node': {'name': 'v1.127.0'}}]}}}}
            return resp["data"]["repository"]["refs"]["edges"][0]["node"]["name"]


async def run(server: str, repo: str, token: str = "") -> CheckResult:
    # Server __version__ (see mozilla-services/Dockerflow)
    version_info = await fetch_json(server + "/__version__")
    deployed_version = version_info["version"]

    # Latest Github release.
    releases = await fetch_json(
        f"https://api.github.com/repos/{repo}/releases",
        headers={"Authorization": f"Bearer {token}"},
        raise_for_status=True,
    )
    if len(releases) > 0:
        latest_tag = releases[0]["tag_name"]
    else:
        # Let's use the latest tag if no release is defined.
        owner, name = repo.split("/")
        latest_tag = await fetch_latest_tag(owner, name, token)

    return (
        deployed_version == latest_tag,
        {"latest_tag": latest_tag, "deployed_version": deployed_version},
    )
