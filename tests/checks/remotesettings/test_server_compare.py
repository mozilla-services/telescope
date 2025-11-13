from datetime import datetime, timedelta, timezone
from unittest import mock

from checks.remotesettings.server_compare import run


MODULE = "checks.remotesettings.server_compare"
RECORDS_URL = "/buckets/{}/collections/{}/records"
CHANGESET_URL = "/buckets/{}/collections/{}/changeset?_expected={}"
CHANGES_ENTRIES = {
    "changes": [
        {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
    ]
}


async def test_positive(mock_responses):
    source_url = "http://fake.local/v1"
    changes_url = source_url + CHANGESET_URL.format("monitor", "changes", 0)
    mock_responses.get(
        changes_url,
        payload=CHANGES_ENTRIES,
    )
    target_url = "http://cdn.local/v1"

    changeset_url = CHANGESET_URL.format("bid", "cid", 42)
    mock_responses.get(
        source_url + changeset_url, payload={"metadata": {"last_modified": 123}}
    )
    mock_responses.get(
        target_url + changeset_url, payload={"metadata": {"last_modified": 123}}
    )

    status, data = await run(source_url, target_url)

    assert status is True
    assert data == {}


async def test_positive_min_age(mock_responses):
    source_url = "http://fake.local/v1"
    changes_url = source_url + CHANGESET_URL.format("monitor", "changes", 0)
    mock_responses.get(
        changes_url,
        payload=CHANGES_ENTRIES,
    )
    target_url = "http://cdn.local/v1"

    fake_now = datetime(1982, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    freshly_changed = fake_now - timedelta(seconds=1800)
    fresh_timestamp = freshly_changed.timestamp() * 1000

    changeset_url = CHANGESET_URL.format("bid", "cid", 42)
    mock_responses.get(
        source_url + changeset_url,
        payload={"metadata": {"last_modified": fresh_timestamp}},
    )
    mock_responses.get(
        target_url + changeset_url, payload={"metadata": {"last_modified": 123}}
    )

    with mock.patch(f"{MODULE}.utcnow", return_value=fake_now):
        status, data = await run(source_url, target_url)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    source_url = "http://fake.local/v1"
    changes_url = source_url + CHANGESET_URL.format("monitor", "changes", 0)
    mock_responses.get(
        changes_url,
        payload=CHANGES_ENTRIES,
    )
    target_url = "http://cdn.local/v1"

    changeset_url = CHANGESET_URL.format("bid", "cid", 42)
    mock_responses.get(
        source_url + changeset_url, payload={"metadata": {"last_modified": 456}}
    )
    mock_responses.get(
        target_url + changeset_url, payload={"metadata": {"last_modified": 123}}
    )

    status, data = await run(source_url, target_url)

    assert status is False
    assert data == {"bid/cid": {"cdn": 123, "source": 456}}
