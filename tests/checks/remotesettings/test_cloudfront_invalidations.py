from datetime import datetime
from unittest import mock

from checks.remotesettings.cloudfront_invalidations import run

MODULE = "checks.remotesettings.cloudfront_invalidations"
COLLECTION_URL = "/buckets/{}/collections/{}"
RECORDS_URL = COLLECTION_URL + "/records"
CHANGES_ENTRIES = {
    "data": [{"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}]
}


async def test_positive(mock_responses):
    origin_url = "http://fake.local/v1"
    changes_url = origin_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url, payload=CHANGES_ENTRIES,
    )
    cdn_url = "http://cdn.local/v1"

    collection_url = COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        origin_url + collection_url, payload={"data": {"last_modified": 123}}
    )
    mock_responses.get(
        cdn_url + collection_url, payload={"data": {"last_modified": 123}}
    )

    records_url = RECORDS_URL.format("bid", "cid")
    mock_responses.head(origin_url + records_url, headers={"ETag": '"42"'})
    mock_responses.head(cdn_url + records_url, headers={"ETag": '"42"'})

    status, data = await run(origin_url, cdn_url)

    assert status is True
    assert data == {}


async def test_positive_min_age(mock_responses):
    origin_url = "http://fake.local/v1"
    changes_url = origin_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url, payload=CHANGES_ENTRIES,
    )
    cdn_url = "http://cdn.local/v1"

    collection_url = COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        origin_url + collection_url, payload={"data": {"last_modified": 389700073814}}
    )
    mock_responses.get(
        cdn_url + collection_url, payload={"data": {"last_modified": 123}}
    )

    records_url = RECORDS_URL.format("bid", "cid")
    mock_responses.head(origin_url + records_url, headers={"ETag": '"42"'})
    mock_responses.head(cdn_url + records_url, headers={"ETag": '"42"'})

    fake_now = datetime(1982, 5, 8, 13, 0, 0)  # half an hour later
    with mock.patch(f"{MODULE}.utcnow", return_value=fake_now):
        status, data = await run(origin_url, cdn_url, min_age=3600)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    origin_url = "http://fake.local/v1"
    changes_url = origin_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url, payload=CHANGES_ENTRIES,
    )
    cdn_url = "http://cdn.local/v1"

    collection_url = COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        origin_url + collection_url, payload={"data": {"last_modified": 456}}
    )
    mock_responses.get(
        cdn_url + collection_url, payload={"data": {"last_modified": 123}}
    )

    records_url = RECORDS_URL.format("bid", "cid")
    mock_responses.head(origin_url + records_url, headers={"ETag": '"40"'})
    mock_responses.head(cdn_url + records_url, headers={"ETag": '"42"'})

    status, data = await run(origin_url, cdn_url)

    assert status is False
    assert data == {
        "bid/cid": {
            "cdn": {"collection": 123, "records": "42"},
            "source": {"collection": 456, "records": "40"},
        }
    }
