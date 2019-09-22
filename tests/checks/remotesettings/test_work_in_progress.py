from datetime import timedelta

from poucave.utils import utcnow
from checks.remotesettings.work_in_progress import run

from tests.utils import patch_async


FAKE_AUTH = ""
COLLECTION_URL = "/buckets/{}/collections/{}"
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
                "last_edit_date": (utcnow() - timedelta(days=1)).isoformat(),
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
                "status": "work-in-progress",
                "last_edit_date": (utcnow() - timedelta(days=1)).isoformat(),
            }
        },
    )

    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES[:1]):
        status, data = await run(server_url, FAKE_AUTH, max_age=20)

    assert status is False
    assert data == {"main/cid": 24}
