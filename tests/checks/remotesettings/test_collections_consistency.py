from checks.remotesettings.collections_consistency import run, has_inconsistencies

from tests.utils import patch_async


FAKE_AUTH = ""
COLLECTION_URL = "/buckets/{}/collections/{}"
RECORDS_URL = COLLECTION_URL + "/records"
RESOURCES = [
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


async def test_has_inconsistencies_no_preview(mock_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    records = [{"id": "abc", "last_modified": 42}, {"id": "def", "last_modified": 41}]

    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mock_responses.get(
        collection_url, payload={"data": {"id": "blocklist", "status": "signed"}}
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mock_responses.get(records_url, payload={"data": records})
    records_url = server_url + RECORDS_URL.format("security", "blocklist")
    mock_responses.get(records_url, payload={"data": records})

    assert await has_inconsistencies(server_url, FAKE_AUTH, resource) is None


async def test_has_inconsistencies_unsupported_status(mock_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mock_responses.get(
        collection_url, payload={"data": {"id": "blocklist", "status": "to-resign"}}
    )

    result = await has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "unexpected status" in result


async def test_has_inconsistencies_preview_differs(mock_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "preview": {"bucket": "security-preview", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    records = [{"id": "abc", "last_modified": 42}, {"id": "def", "last_modified": 41}]

    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mock_responses.get(
        collection_url, payload={"data": {"id": "blocklist", "status": "to-review"}}
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mock_responses.get(records_url, payload={"data": records})
    records_url = server_url + RECORDS_URL.format("security-preview", "blocklist")
    mock_responses.get(
        records_url, payload={"data": records + [{"id": "xyz", "last_modified": 40}]}
    )

    result = await has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "source and preview differ" in result


async def test_has_inconsistencies_destination_differs(mock_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "preview": {"bucket": "security-preview", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    records = [{"id": "abc", "last_modified": 42}, {"id": "def", "last_modified": 41}]

    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mock_responses.get(
        collection_url, payload={"data": {"id": "blocklist", "status": "signed"}}
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mock_responses.get(records_url, payload={"data": records})
    records_url = server_url + RECORDS_URL.format("security-preview", "blocklist")
    mock_responses.get(records_url, payload={"data": records})
    records_url = server_url + RECORDS_URL.format("security", "blocklist")
    mock_responses.get(
        records_url, payload={"data": records + [{"id": "xyz", "last_modified": 40}]}
    )

    result = await has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "source, preview, and/or destination differ" in result


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"

    module = "checks.remotesettings.collections_consistency"
    with patch_async(f"{module}.fetch_signed_resources", return_value=RESOURCES):
        with patch_async(f"{module}.has_inconsistencies", return_value=None):

            status, data = await run(server_url, FAKE_AUTH)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"

    m = "checks.remotesettings.collections_consistency"
    with patch_async(f"{m}.fetch_signed_resources", return_value=RESOURCES):
        with patch_async(f"{m}.has_inconsistencies", return_value="Some error"):
            status, data = await run(server_url, FAKE_AUTH)

    assert status is False
    print(data)
    assert data == {"blog/articles": "Some error", "security/blocklist": "Some error"}
