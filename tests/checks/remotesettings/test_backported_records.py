import responses

from checks.remotesettings.backported_records import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    source_url = server_url + RECORDS_URL.format("bid", "cid")
    mocked_responses.add(
        responses.HEAD, source_url, json={}, headers={"ETag": '"12345"'}
    )
    dest_url = server_url + RECORDS_URL.format("other", "cid")
    mocked_responses.add(responses.HEAD, dest_url, json={}, headers={"ETag": '"12345"'})

    status, data = await run(
        server_url, backports={"bid/cid": "other/cid"}, max_lag_seconds=1
    )

    assert status is True
    assert data == []


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    source_url = server_url + RECORDS_URL.format("bid", "cid")
    mocked_responses.add(
        responses.HEAD, source_url, json={}, headers={"ETag": '"1000000"'}
    )
    dest_url = server_url + RECORDS_URL.format("other", "cid")
    mocked_responses.add(
        responses.HEAD, dest_url, json={}, headers={"ETag": '"2000000"'}
    )

    status, data = await run(
        server_url, backports={"bid/cid": "other/cid"}, max_lag_seconds=1
    )

    assert status is False
    assert data == [{"bid/cid": "1000000", "other/cid": "2000000"}]
