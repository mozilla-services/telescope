import pytest

from checks.remotesettings.utils import KintoClient, fetch_signed_resources


async def test_fetch_signed_resources_no_signer(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(server_url + "/", payload={"capabilities": {}})

    client = KintoClient(server_url=server_url, auth="Bearer abc")
    with pytest.raises(ValueError):
        await fetch_signed_resources(client=client)


async def test_fetch_signed_resources(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
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
    mock_aioresponses.get(
        server_url + "/buckets/blog-workspace/collections",
        payload={"data": [{"id": "articles"}]},
    )
    changes_url = server_url + "/buckets/monitor/collections/changes/changeset"
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
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

    client = KintoClient(server_url=server_url, auth="Bearer abc")
    resources = await fetch_signed_resources(client=client)

    assert resources == [
        {
            "last_modified": 42,
            "source": {"bucket": "blog-workspace", "collection": "articles"},
            "preview": {"bucket": "blog-preview", "collection": "articles"},
            "destination": {"bucket": "blog", "collection": "articles"},
        },
        {
            "last_modified": 41,
            "source": {"bucket": "security-workspace", "collection": "blocklist"},
            "destination": {"bucket": "security", "collection": "blocklist"},
        },
    ]


async def test_fetch_signed_resources_unknown_collection(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
        server_url + "/", payload={"capabilities": {"signer": {"resources": []}}}
    )
    changes_url = server_url + "/buckets/monitor/collections/changes/changeset"
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {
                    "id": "abc",
                    "bucket": "blog",
                    "collection": "articles",
                    "last_modified": 42,
                }
            ]
        },
    )

    client = KintoClient(server_url=server_url, auth="Bearer abc")
    with pytest.raises(ValueError):
        await fetch_signed_resources(client=client)


async def test_kinto_client_auth_bearer_header(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(server_url + "/", payload={})

    client = KintoClient(server_url=server_url, auth="Bearer mytoken")
    await client.server_info()
    _, [request] = next(iter(mock_aioresponses.requests.items()))
    assert request.kwargs["headers"]["Authorization"] == "Bearer mytoken"


async def test_kinto_client_auth_basic_header(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(server_url + "/", payload={})

    client = KintoClient(server_url=server_url, auth="admin:s3cr3t")
    await client.server_info()
    _, [request] = next(iter(mock_aioresponses.requests.items()))
    assert (
        request.kwargs["headers"]["Authorization"] == "Basic YWRtaW46czNjcjN0"
    )  # base64


async def test_user_agent(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(server_url + "/", payload={})

    client = KintoClient(server_url=server_url)
    await client.server_info()

    _, [request] = next(iter(mock_aioresponses.requests.items()))
    user_agent = request.kwargs["headers"]["User-Agent"]
    assert "telescope" in user_agent


async def test_get_monitor_changes(mock_aioresponses):
    server_url = "http://fake.local/v1"
    monitor_url = f"{server_url}/buckets/monitor/collections/changes/changeset"
    mock_aioresponses.get(monitor_url, payload={"changes": []}, repeat=3)

    client = KintoClient(server_url=server_url)

    await client.get_monitor_changes()
    await client.get_monitor_changes(bust_cache=True)
    await client.get_monitor_changes(params={"_expected": "bim"})

    [(_, [request1]), (_, [request2]), (_, [request3])] = (
        mock_aioresponses.requests.items()
    )

    assert request1.kwargs["params"]["_expected"] == 0
    assert "_expected" in request2.kwargs["params"]
    assert request3.kwargs["params"]["_expected"] == "bim"
