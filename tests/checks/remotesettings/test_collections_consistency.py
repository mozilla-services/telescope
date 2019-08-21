from unittest import mock

import responses

from checks.remotesettings.collections_consistency import (
    run,
    fetch_signed_resources,
    has_inconsistencies,
)


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


def test_fetch_signed_resources(mocked_responses):
    server_url = "http://fake.local/v1"
    mocked_responses.add(
        responses.GET,
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
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
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

    resources = fetch_signed_resources(server_url, auth=FAKE_AUTH)

    assert resources == RESOURCES


def test_has_inconsistencies_no_preview(mocked_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    records = [{"id": "abc", "last_modified": 42}, {"id": "def", "last_modified": 41}]

    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mocked_responses.add(
        responses.GET,
        collection_url,
        json={"data": {"id": "blocklist", "status": "signed"}},
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mocked_responses.add(responses.GET, records_url, json={"data": records})
    records_url = server_url + RECORDS_URL.format("security", "blocklist")
    mocked_responses.add(responses.GET, records_url, json={"data": records})

    assert has_inconsistencies(server_url, FAKE_AUTH, resource) is None


def test_has_inconsistencies_unsupported_status(mocked_responses):
    server_url = "http://fake.local/v1"
    resource = {
        "source": {"bucket": "security-workspace", "collection": "blocklist"},
        "destination": {"bucket": "security", "collection": "blocklist"},
    }
    collection_url = server_url + COLLECTION_URL.format(
        "security-workspace", "blocklist"
    )
    mocked_responses.add(
        responses.GET,
        collection_url,
        json={"data": {"id": "blocklist", "status": "to-resign"}},
    )

    result = has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "unexpected status" in result


def test_has_inconsistencies_preview_differs(mocked_responses):
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
    mocked_responses.add(
        responses.GET,
        collection_url,
        json={"data": {"id": "blocklist", "status": "to-review"}},
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mocked_responses.add(responses.GET, records_url, json={"data": records})
    records_url = server_url + RECORDS_URL.format("security-preview", "blocklist")
    mocked_responses.add(
        responses.GET,
        records_url,
        json={"data": records + [{"id": "xyz", "last_modified": 40}]},
    )

    result = has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "source and preview differ" in result


def test_has_inconsistencies_destination_differs(mocked_responses):
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
    mocked_responses.add(
        responses.GET,
        collection_url,
        json={"data": {"id": "blocklist", "status": "signed"}},
    )
    records_url = server_url + RECORDS_URL.format("security-workspace", "blocklist")
    mocked_responses.add(responses.GET, records_url, json={"data": records})
    records_url = server_url + RECORDS_URL.format("security-preview", "blocklist")
    mocked_responses.add(responses.GET, records_url, json={"data": records})
    records_url = server_url + RECORDS_URL.format("security", "blocklist")
    mocked_responses.add(
        responses.GET,
        records_url,
        json={"data": records + [{"id": "xyz", "last_modified": 40}]},
    )

    result = has_inconsistencies(server_url, FAKE_AUTH, resource)

    assert "source, preview, and/or destination differ" in result


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"

    module = "checks.remotesettings.collections_consistency"
    with mock.patch(f"{module}.fetch_signed_resources", return_value=RESOURCES):
        with mock.patch(f"{module}.has_inconsistencies", return_value=None):

            status, data = await run(None, server_url, FAKE_AUTH)

    assert status is True
    assert data == {}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"

    m = "checks.remotesettings.collections_consistency"
    with mock.patch(f"{m}.fetch_signed_resources", return_value=RESOURCES):
        with mock.patch(f"{m}.has_inconsistencies", side_effect=("Some error", None)):
            status, data = await run(None, server_url, FAKE_AUTH)

    assert status is False
    assert data == {"blog/articles": "Some error"}
