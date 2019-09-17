from checks.core.deployed_version import run


async def test_positive(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/__version__",
        status=200,
        payload={
            "commit": "ba2d991534a1346d10304013438b8dcfe7456d10",
            "version": "17.1.4",
            "source": "https://github.com/mozilla-services/kinto-dist",
            "build": "https://circleci.com/gh/mozilla-services/kinto-dist/3355",
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla-services/kinto-dist/releases",
        status=200,
        payload=[
            {
                "url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/18962883",
                "assets_url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/18962883/assets",
                "upload_url": "https://uploads.github.com/repos/mozilla-services/kinto-dist/releases/18962883/assets{?name,label}",
                "html_url": "https://github.com/mozilla-services/kinto-dist/releases/tag/17.1.4",
                "id": 18962883,
                "node_id": "MDc6UmVsZWFzZTE4OTYyODgz",
                "tag_name": "17.1.4",
                "target_commitish": "master",
                "name": "",
                "author": {"login": "leplatrem", "id": 546692},
            }
        ],
    )

    status, data = await run(server=url, repo="mozilla-services/kinto-dist")

    assert status is True
    assert data == {"latest_tag": "17.1.4", "deployed_version": "17.1.4"}


async def test_negative(mock_aioresponses):
    url = "http://server.local/v1"
    mock_aioresponses.get(
        url + "/__version__",
        status=200,
        payload={
            "commit": "ba2d991534a1346d10304013438b8dcfe7456d10",
            "version": "17.1.4",
            "source": "https://github.com/mozilla-services/kinto-dist",
            "build": "https://circleci.com/gh/mozilla-services/kinto-dist/3355",
        },
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/mozilla-services/kinto-dist/releases",
        status=200,
        payload=[
            {
                "url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/19949437",
                "assets_url": "https://api.github.com/repos/mozilla-services/kinto-dist/releases/19949437/assets",
                "upload_url": "https://uploads.github.com/repos/mozilla-services/kinto-dist/releases/19949437/assets{?name,label}",
                "html_url": "https://github.com/mozilla-services/kinto-dist/releases/tag/17.2.0",
                "id": 19949437,
                "node_id": "MDc6UmVsZWFzZTE5OTQ5NDM3",
                "tag_name": "17.2.0",
                "target_commitish": "master",
                "name": "",
                "author": {"login": "leplatrem", "id": 546692},
            }
        ],
    )

    status, data = await run(server=url, repo="mozilla-services/kinto-dist")

    assert status is False
    assert data == {"latest_tag": "17.2.0", "deployed_version": "17.1.4"}
