from checks.remotesettings.utils import fetch_signed_resources


def test_fetch_signed_resources(mocked_responses):
    server_url = "http://fake.local/v1"
    mocked_responses.get(
        server_url + "/",
        json={
            "capabilities": {
                "signer": {
                    "resources": [
                        {
                            "source": {"bucket": "blog-workspace", "collection": None},
                            "preview": {"bucket": "blog-preview", "collection": None},
                            "destination": {"bucket": "blog", "collection": None},
                        },
                        {
                            "source": {
                                "bucket": "security-workspace",
                                "collection": "blocklist",
                            },
                            "destination": {
                                "bucket": "security",
                                "collection": "blocklist",
                            },
                        },
                    ]
                }
            }
        },
    )
    changes_url = server_url + "/buckets/monitor/collections/changes/records"
    mocked_responses.get(
        changes_url,
        json={
            "data": [
                {
                    "id": "abc",
                    "bucket": "blog",
                    "collection": "articles",
                    "last_modified": 42,
                },
                {
                    "id": "def",
                    "bucket": "security",
                    "collection": "blocklist",
                    "last_modified": 41,
                },
            ]
        },
    )

    resources = fetch_signed_resources(server_url, auth="")

    assert resources == [
        {
            "source": {"bucket": "blog-workspace", "collection": "articles"},
            "preview": {"bucket": "blog-preview", "collection": "articles"},
            "destination": {"bucket": "blog", "collection": "articles"},
        },
        {
            "source": {"bucket": "security-workspace", "collection": "blocklist"},
            "destination": {"bucket": "security", "collection": "blocklist"},
        },
    ]
