import sys
from datetime import timedelta

from checks.remotesettings.work_in_progress import run
from telescope.utils import utcnow
from tests.utils import patch_async


FAKE_AUTH = "Bearer abc"
COLLECTION_URL = "/buckets/{}/collections/{}"
GROUP_URL = "/buckets/{}/groups/{}"
RECORD_URL = "/buckets/{}/collections/{}/records"
MODULE = "checks.remotesettings.work_in_progress"
RESOURCES = [
    {
        "source": {"bucket": "bid", "collection": "cid"},
        "destination": {"bucket": "main", "collection": "cid"},
    },
    {
        "source": {"bucket": "bid", "collection": "cid2"},
        "destination": {"bucket": "main", "collection": "cid2"},
    },
]


async def test_positive_signed(mock_responses):
    server_url = "http://fake.local/v1"

    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "signed",
                "last_edit_date": (utcnow() - timedelta(days=20)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )
    collection_url = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(collection_url, payload={"data": {"status": "signed"}})

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=25)

    assert status is True
    assert data == {}


async def test_positive_recent(mock_responses):
    server_url = "http://fake.local/v1"

    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "work-in-progress",
                "last_edit_date": (utcnow() - timedelta(days=10)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )
    collection_url = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(
        collection_url,
        payload={
            "data": {"status": "signed", "last_edit_date": "2017-08-01T01:00.000"}
        },
    )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=25)

    assert status is True
    assert data == {}


async def test_positive_no_pending_changes(mock_responses):
    server_url = "http://fake.local/v1"

    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "work-in-progress",
                "last_edit_date": (utcnow() - timedelta(days=10)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )
    collection_url = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "work-in-progress",
                "last_edit_date": (utcnow() - timedelta(days=10)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )
    for bid, cid in [
        ("bid", "cid"),
        ("main", "cid"),
        ("bid", "cid2"),
        ("main", "cid2"),
    ]:
        record = {"id": "record", "field": "foo"}
        mock_responses.get(
            server_url + RECORD_URL.format(bid, cid),
            payload={
                "data": [record],
            },
        )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=5)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"

    # Source collection is WIP.
    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "work-in-progress",
                "last_edit_by": "ldap:mleplatre@mozilla.com",
                "last_edit_date": (utcnow() - timedelta(days=10)).isoformat(),
            }
        },
    )
    # Records are different in source and destination.
    mock_responses.get(
        server_url + RECORD_URL.format("bid", "cid"),
        payload={
            "data": [{"id": "record", "field": "foo"}],
        },
    )
    mock_responses.get(
        server_url + RECORD_URL.format("main", "cid"),
        payload={
            "data": [{"id": "record", "field": "bar"}],
        },
    )
    # The check needs to show the collection editors.
    group_url = server_url + GROUP_URL.format("bid", "cid2-editors")
    mock_responses.get(
        group_url, payload={"data": {"members": ["ldap:editor@mozilla.com"]}}
    )
    # Add another failing collection, without last-edit
    group_url = server_url + GROUP_URL.format("bid", "cid-editors")
    collection_url = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(collection_url, payload={"data": {"status": "to-review"}})
    mock_responses.get(
        group_url, payload={"data": {"members": ["ldap:user@mozilla.com"]}}
    )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=5)

    assert status is False
    assert data == {
        "main/cid": {
            "age": 10,
            "status": "work-in-progress",
            "last_edit_by": "ldap:mleplatre@mozilla.com",
            "editors": ["ldap:user@mozilla.com"],
        },
        "main/cid2": {
            "age": sys.maxsize,
            "status": "to-review",
            "last_edit_by": "N/A",
            "editors": ["ldap:editor@mozilla.com"],
        },
    }


async def test_negative_with_recent(mock_responses):
    server_url = "http://fake.local/v1"

    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "signed",
                "last_edit_date": (utcnow() - timedelta(days=3)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )

    collection_url2 = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(
        collection_url2,
        payload={
            "data": {
                "status": "to-review",
                "last_edit_date": (utcnow() - timedelta(days=20)).isoformat(),
                "last_edit_by": "ldap:mleplatre@mozilla.com",
            }
        },
    )
    mock_responses.get(
        server_url + GROUP_URL.format("bid", "cid2-editors"),
        payload={"data": {"members": ["ldap:editor@mozilla.com"]}},
    )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=15)

    assert status is False
    assert data == {
        "main/cid2": {
            "age": 20,
            "editors": ["ldap:editor@mozilla.com"],
            "last_edit_by": "ldap:mleplatre@mozilla.com",
            "status": "to-review",
        }
    }
