from checks.remotesettings.attachments_availability import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    mocked_responses.get(
        server_url + "/",
        json={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.get(
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mocked_responses.get(
        records_url,
        json={
            "data": [
                {"id": "abc", "attachment": {"location": "file1.jpg"}},
                {"id": "efg", "attachment": {"location": "file2.jpg"}},
                {"id": "ijk"},
            ]
        },
    )
    mocked_responses.head("http://cdn/file1.jpg")
    mocked_responses.head("http://cdn/file2.jpg")

    status, data = await run(server_url)

    # assert status is True
    assert data == {"missing": [], "checked": 2}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    mocked_responses.get(
        server_url + "/",
        json={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.get(
        changes_url,
        json={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mocked_responses.get(
        records_url,
        json={
            "data": [
                {"id": "abc", "attachment": {"location": "file.jpg"}},
                {"id": "efg", "attachment": {"location": "missing.jpg"}},
                {"id": "ijk"},
            ]
        },
    )
    mocked_responses.head("http://cdn/file.jpg")

    status, data = await run(server_url)

    assert status is False
    assert data == {"missing": ["http://cdn/missing.jpg"], "checked": 2}
