from checks.remotesettings.backported_records import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    source_url = server_url + RECORDS_URL.format("bid", "cid")
    mock_responses.get(
        source_url, payload={"data": [{"id": "abc", "last_modified": 42}]}
    )
    dest_url = server_url + RECORDS_URL.format("other", "cid")
    mock_responses.get(dest_url, payload={"data": [{"id": "abc", "last_modified": 43}]})

    status, data = await run(
        server_url, backports={"bid/cid": "other/cid"}, max_lag_seconds=1
    )

    assert status is True
    assert data == []


async def test_positive_small_lag(mock_responses):
    server_url = "http://fake.local/v1"
    source_url = server_url + RECORDS_URL.format("bid", "cid")
    mock_responses.get(
        source_url,
        payload={"data": [{"id": "abc", "last_modified": 42}]},
        headers={"ETag": '"100"'},
    )
    dest_url = server_url + RECORDS_URL.format("other", "cid")
    mock_responses.get(
        dest_url,
        payload={"data": [{"id": "abc", "last_modified": 43, "title": "abc"}]},
        headers={"ETag": '"150"'},
    )

    status, data = await run(
        server_url, backports={"bid/cid": "other/cid"}, max_lag_seconds=1
    )

    assert status is True
    assert data == []


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"
    source_url = server_url + RECORDS_URL.format("bid", "cid")
    mock_responses.get(
        source_url,
        payload={"data": [{"id": "abc", "last_modified": 42}]},
        headers={"ETag": '"1000000"'},
    )
    dest_url = server_url + RECORDS_URL.format("other", "cid")
    mock_responses.get(
        dest_url,
        payload={"data": [{"id": "abc", "last_modified": 43, "title": "abc"}]},
        headers={"ETag": '"2000000"'},
    )

    status, data = await run(
        server_url, backports={"bid/cid": "other/cid"}, max_lag_seconds=1
    )

    assert status is False
    assert data == ["1 record differ between bid/cid and other/cid ('abc')"]
