import responses

from checks.remotesettings.changes_timestamps import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid")
    mocked_responses.add(responses.HEAD, records_url, headers={"ETag": '"42"'})

    status, data = await run(None, server_url)

    assert status is True
    assert data == [
        {
            "collection": "42",
            "datetime": "1970-01-01T00:00:00.042000",
            "entry": "42",
            "id": "bid/cid",
        }
    ]


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid")
    mocked_responses.add(responses.HEAD, records_url, headers={"ETag": '"123"'})

    status, data = await run(None, server_url)

    assert status is False
    assert data == [
        {
            "id": "bid/cid",
            "collection": "123",
            "entry": "42",
            "datetime": "1970-01-01T00:00:00.123000",
        }
    ]
