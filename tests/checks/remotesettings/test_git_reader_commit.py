from checks.remotesettings.git_reader_commit import run


GITHUB_EXAMPLE_COMMIT = {
    "name": "main",
    "commit": {
        "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
        "node_id": "C_kwDOB0k-MNoAKDdhNTBmNTUwNmUwYTNlNGEyOGU2NzYxNjQ1ZGE2ZTNlMTI3NmE1Y2M",
        "commit": {
            "author": {
                "name": "Remote Settings Data Bot",
                "email": "email@mozilla.com",
                "date": "2025-02-25T18:11:32Z",
            },
            "message": "Latest run @ 2025-02-25T18:11:32Z",
            "tree": {
                "sha": "9b63c84ce2ceefa85060c347ea62cf53043459d7",  # pragma: allowlist secret
                "url": "https://api.github.com/repos/mozilla/remote-settings/git/trees/9b63c84ce2ceefa85060c347ea62cf53043459d7",
            },
        },
        "author": {
            "login": "remote-settings-data-bot",
            "id": 546692,
        },
    },
}


async def test_positive(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/",
        status=200,
        payload={
            "git": {
                "common": {
                    "id": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                    "datetime": "2025-02-25T18:11:32Z",
                }
            },
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings-data/branches/v1/common",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    status, data = await run(server=url, repo="mozilla/remote-settings-data")

    assert status is True
    assert (
        data
        == {
            "latest_commit": {
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "source_commit": {
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
        }
    )


async def test_positive_latency(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/",
        status=200,
        payload={
            "git": {
                "common": {
                    # Different source commit.
                    "id": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
                    # Latest commit date is within lag margin.
                    "datetime": "2025-02-25T18:02:02Z",
                }
            },
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings-data/branches/v1/common",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    status, data = await run(server=url, repo="mozilla/remote-settings-data")

    assert status is True
    assert (
        data
        == {
            "latest_commit": {
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "source_commit": {
                "sha": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
                "date": "2025-02-25T18:02:02Z",
            },
        }
    )


async def test_negative(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/",
        status=200,
        payload={
            "git": {
                "common": {
                    # Different source commit.
                    "id": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
                    "datetime": "2025-02-25T17:02:02Z",
                }
            },
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings-data/branches/v1/common",
        status=200,
        payload=GITHUB_EXAMPLE_COMMIT,
    )

    status, data = await run(server=url, repo="mozilla/remote-settings-data")

    assert status is False
    assert (
        data
        == {
            "latest_commit": {
                "sha": "ba2d991534a1346d10304013438b8dcfe7456d10",  # pragma: allowlist secret
                "date": "2025-02-25T18:11:32Z",
            },
            "source_commit": {
                "sha": "7a50f5506e0a3e4a28e6761645da6e3e1276a5cc",  # pragma: allowlist secret
                "date": "2025-02-25T17:02:02Z",
            },
        }
    )


async def test_negative_hit_rate(mock_aioresponses, config):
    config.GITHUB_TOKEN = "s3cr3t"
    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla/remote-settings-data/branches/v1/common",
        status=503,
        payload={"message": "Too many requests"},
    )

    status, data = await run(
        server="http://server", repo="mozilla/remote-settings-data"
    )

    assert status is False
    assert data == "Could not fetch commit info from {'message': 'Too many requests'}"
