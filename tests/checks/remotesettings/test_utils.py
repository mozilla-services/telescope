import pytest

from checks.remotesettings.utils import KintoClient, fetch_signed_resources


async def test_fetch_signed_resources_no_signer(mock_responses):
    server_url = "http://fake.local/v1"
    mock_responses.get(server_url + "/", payload={"capabilities": {}})

    with pytest.raises(ValueError):
        await fetch_signed_resources(server_url, auth="")


async def test_fetch_signed_resources(mock_responses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={
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
    mock_responses.get(
        changes_url,
        payload={
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
                {
                    "id": "ghi",
                    "bucket": "blog-preview",
                    "collection": "articles",
                    "last_modified": 40,
                },
            ]
        },
    )

    resources = await fetch_signed_resources(server_url, auth="")

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


async def test_fetch_signed_resources_unknown_collection(mock_responses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/", payload={"capabilities": {"signer": {"resources": []}}}
    )
    changes_url = server_url + "/buckets/monitor/collections/changes/records"
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {
                    "id": "abc",
                    "bucket": "blog",
                    "collection": "articles",
                    "last_modified": 42,
                }
            ]
        },
    )

    with pytest.raises(ValueError):
        await fetch_signed_resources(server_url, auth="")


def test_kinto_auth():
    client = KintoClient(server_url="http://server/v1", auth="Bearer token")

    assert client._client.session.auth.type == "Bearer"
    assert client._client.session.auth.token == "token"
