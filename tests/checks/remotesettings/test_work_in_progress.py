import sys
from datetime import timedelta

from checks.remotesettings.work_in_progress import run
from telescope.utils import utcnow
from tests.utils import patch_async


FAKE_AUTH = "Bearer abc"
COLLECTION_URL = "/buckets/{}/collections/{}"
GROUP_URL = "/buckets/{}/groups/{}"
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


async def test_positive(mock_responses):
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


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"

    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "status": "to-review",
                "last_edit_by": "ldap:mleplatre@mozilla.com",
                "last_edit_date": (utcnow() - timedelta(days=10)).isoformat(),
            }
        },
    )
    group_url = server_url + GROUP_URL.format("bid", "cid-editors")
    mock_responses.get(
        group_url, payload={"data": {"members": ["ldap:user@mozilla.com"]}}
    )
    collection_url = server_url + COLLECTION_URL.format("bid", "cid2")
    mock_responses.get(collection_url, payload={"data": {"status": "work-in-progress"}})
    group_url = server_url + GROUP_URL.format("bid", "cid2-editors")
    mock_responses.get(
        group_url, payload={"data": {"members": ["ldap:editor@mozilla.com"]}}
    )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        status, data = await run(server_url, FAKE_AUTH, max_age=5)

    assert status is False
    assert data == {
        "main/cid": {
            "age": 10,
            "status": "to-review",
            "last_edit_by": "ldap:mleplatre@mozilla.com",
            "editors": ["ldap:user@mozilla.com"],
        },
        "main/cid2": {
            "age": sys.maxsize,
            "status": "work-in-progress",
            "last_edit_by": "N/A",
            "editors": ["ldap:editor@mozilla.com"],
        },
    }
