from checks.remotesettings.changes_timestamps import run

RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid")
    mock_responses.head(records_url, headers={"ETag": '"42"'})

    status, data = await run(server_url)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid")
    mock_responses.head(records_url, headers={"ETag": '"123"'})

    status, data = await run(server_url)

    assert status is False
    assert data == {
        "bid/cid": {
            "collection": 123,
            "entry": 42,
            "datetime": "1970-01-01T00:00:00.123000",
        }
    }
