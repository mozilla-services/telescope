from datetime import datetime, timezone
from unittest import mock

from checks.core.deployed_commit import run


GITHUB_EXAMPLE_COMMIT = {
    "name": "main",
    "commit": {
        "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
        "node_id": "C_kwDOB0k-MNoAKDdhNTBmNTUwNmUwYTNlNGEyOGU2NzYxNjQ1ZGE2ZTNlMTI3NmE1Y2M",
        "commit": {
            "author": {
                "name": "Mathieu Leplatre",
                "email": "email@mozilla.com",
                "date": "2025-02-25T18:11:32Z",
            },
            "message": "Fix #755: Import lambdas into this repo (#758)\n\n* Import code as is\n\n* Adjust to fit in the repo\n\n* Add missing conftest\n\n* Move Dockerfile to cronjobs/ folder\n\n* Format and lint cronjobs folder\n\n* Fix cronjobs dependencies definition\n\n* Lock poetry files\n\n* Install optional cronjobs group for tests\n\n* Do not upgrade Kinto yet\n\n* Mention folder cronjobs/ in README",
            "tree": {
                "sha": "9b63c84ce2ceefa85060c347ea62cf53043459d7",  # pragma: allowlist secret
                "url": "https://api.github.com/repos/mozilla/remote-settings/git/trees/9b63c84ce2ceefa85060c347ea62cf53043459d7",
            },
        },
        "author": {
            "login": "leplatrem",
            "id": 546692,
        },
    },
}


async def test_positive(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/__version__",
        status=200,
        payload={
            "commit": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
            "version": "v4.15.0-11-geb670",
            "source": "https://github.com/mozilla-services/kinto-dist",
            "build": "https://circleci.com/gh/mozilla-services/kinto-dist/3355",
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla-services/kinto-dist/branches/main",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    status, data = await run(server=url, repo="mozilla-services/kinto-dist")

    assert status is True
    assert (
        data
        == {
            "latest_commit": {
                "author": "leplatrem",
                "message": "Fix #755: Import lambdas into this repo (#758)",
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "deployed_commit": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
        }
    )


async def test_positive_latency(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/__version__",
        status=200,
        payload={
            # Different commit deployed.
            "commit": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
            "version": "v4.15.0-11-geb670",
            "source": "https://github.com/mozilla-services/kinto-dist",
            "build": "https://circleci.com/gh/mozilla-services/kinto-dist/3355",
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla-services/kinto-dist/branches/main",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    # Less than 30min after commit was made.
    fake_now = datetime(2025, 2, 25, 18, 30, 0, tzinfo=timezone.utc)
    with mock.patch("checks.core.deployed_commit.utcnow", return_value=fake_now):
        status, data = await run(server=url, repo="mozilla-services/kinto-dist")

    assert status is True
    assert (
        data
        == {
            "latest_commit": {
                "author": "leplatrem",
                "message": "Fix #755: Import lambdas into this repo (#758)",
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "deployed_commit": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
        }
    )


async def test_negative(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/__version__",
        status=200,
        payload={
            "commit": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
            "version": "v4.15.0-11-geb670",
            "source": "https://github.com/mozilla-services/kinto-dist",
            "build": "https://circleci.com/gh/mozilla-services/kinto-dist/3355",
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla-services/kinto-dist/branches/main",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    status, data = await run(server=url, repo="mozilla-services/kinto-dist")

    assert status is False
    assert (
        data
        == {
            "latest_commit": {
                "author": "leplatrem",
                "message": "Fix #755: Import lambdas into this repo (#758)",
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "deployed_commit": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
        }
    )
