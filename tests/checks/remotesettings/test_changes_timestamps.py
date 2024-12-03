from checks.remotesettings.changes_timestamps import run


CHANGESET_URL = "/buckets/{}/collections/{}/changeset"


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + "/buckets/monitor/collections/changes/changeset"
    mock_responses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    changeset_url = server_url + CHANGESET_URL.format("bid", "cid")
    mock_responses.get(changeset_url, payload={"timestamp": 42})

    status, data = await run(server_url)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + "/buckets/monitor/collections/changes/changeset"
    mock_responses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    changeset_url = server_url + CHANGESET_URL.format("bid", "cid")
    mock_responses.get(changeset_url, payload={"timestamp": 123})

    status, data = await run(server_url)

    assert status is False
    assert data == {
        "bid/cid": {
            "collection": 123,
            "entry": 42,
            "datetime": "1970-01-01T00:00:00.123000+00:00",
        }
    }
