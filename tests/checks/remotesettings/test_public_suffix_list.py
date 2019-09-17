from checks.remotesettings.public_suffix_list import run


async def test_positive(mock_aioresponses, mock_responses):
    url = "http://server.local/v1"
    sha = "cc7eb74f88c307c1eb11fdfb9d357a9fcd3f7f4d"
    mock_responses.get(
        url + "/buckets/main/collections/public-suffix-list/records/tld-dafsa",
        payload={"data": {"commit-hash": sha}},
    )
    mock_responses.get(
        url + "/buckets/main-preview/collections/public-suffix-list/records/tld-dafsa",
        payload={"data": {"commit-hash": sha}},
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/publicsuffix/list/commits?path=public_suffix_list.dat",
        status=200,
        payload=[
            {
                "sha": sha,
                "node_id": "MDY6Q29tbWl0MzU4OTAwMDI6Y2M3ZWI3NGY4OGMzMDdjMWViMTFmZGZiOWQzNTdhOWZjZDNmN2Y0ZA==",
                "commit": {
                    "author": {
                        "name": "TLD Update Robot",
                        "email": "47792085+tld-update-bot@users.noreply.github.com",
                        "date": "2019-09-10T16:45:48Z",
                    }
                },
            }
        ],
    )

    status, data = await run(server=url)

    assert status is True
    assert data == {"latest-sha": sha, "published-sha": sha, "to-review-sha": sha}


async def test_negative(mock_aioresponses, mock_responses):
    url = "http://server.local/v1"
    sha = "cc7eb74f88c307c1eb11fdfb9d357a9fcd3f7f4d"
    mock_responses.get(
        url + "/buckets/main/collections/public-suffix-list/records/tld-dafsa",
        payload={"data": {"commit-hash": "wrong"}},
    )
    mock_responses.get(
        url + "/buckets/main-preview/collections/public-suffix-list/records/tld-dafsa",
        payload={"data": {"commit-hash": sha}},
    )

    mock_aioresponses.get(
        "https://api.github.com/repos/publicsuffix/list/commits?path=public_suffix_list.dat",
        status=200,
        payload=[
            {
                "sha": sha,
                "node_id": "MDY6Q29tbWl0MzU4OTAwMDI6Y2M3ZWI3NGY4OGMzMDdjMWViMTFmZGZiOWQzNTdhOWZjZDNmN2Y0ZA==",
                "commit": {
                    "author": {
                        "name": "TLD Update Robot",
                        "email": "47792085+tld-update-bot@users.noreply.github.com",
                        "date": "2019-09-10T16:45:48Z",
                    }
                },
            }
        ],
    )

    status, data = await run(server=url)

    assert status is False
    assert data == {"latest-sha": sha, "published-sha": "wrong", "to-review-sha": sha}
