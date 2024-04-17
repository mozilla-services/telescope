from checks.remotesettings.attachments_integrity import run


RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_responses, mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mock_responses.get(
        records_url,
        payload={
            "data": [
                {
                    "id": "abc",
                    "attachment": {
                        "size": 5,
                        "hash": "ed968e840d10d2d313a870bc131a4e2c311d7ad09bdf32b3418147221f51a6e2",
                        "location": "file1.jpg",
                    },
                },
                {
                    "id": "efg",
                    "attachment": {
                        "size": 10,
                        "hash": "bf2cb58a68f684d95a3b78ef8f661c9a4e5b09e82cc8f9cc88cce90528caeb27",
                        "location": "file2.jpg",
                    },
                },
                {"id": "ijk"},
            ]
        },
    )
    mock_aioresponses.get("http://cdn/file1.jpg", body=b"a" * 5)
    mock_aioresponses.get("http://cdn/file2.jpg", body=b"a" * 10)

    status, data = await run(server_url)

    # assert status is True
    assert data == {"bad": [], "checked": 2}


async def test_negative(mock_responses, mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "data": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mock_responses.get(
        records_url,
        payload={
            "data": [
                {
                    "id": "abc",
                    "attachment": {
                        "size": 7,
                        "hash": "ed968e840d10d2d313a870bc131a4e2c311d7ad09bdf32b3418147221f51a6e2",
                        "location": "file1.jpg",
                    },
                },
                {"id": "efg", "attachment": {"location": "missing.jpg"}},
                {
                    "id": "ijk",
                    "attachment": {"size": 10, "hash": "foo", "location": "file2.jpg"},
                },
                {"id": "lmn"},
            ]
        },
    )
    mock_aioresponses.get("http://cdn/file1.jpg", body=b"a" * 5)
    mock_aioresponses.get("http://cdn/file2.jpg", body=b"a" * 10)

    status, data = await run(server_url)

    assert status is False
    assert data == {
        "bad": [
            {
                "error": "size differ (5!=7)",
                "url": "http://cdn/file1.jpg",
            },
            {
                "error": "Connection refused: GET http://cdn/missing.jpg",
                "url": "http://cdn/missing.jpg",
            },
            {
                "error": "hash differ (bf2cb58a68f684d95a3b78ef8f661c9a4e5b09e82cc8f9cc88cce90528caeb27!=foo)",
                "url": "http://cdn/file2.jpg",
            },
        ],
        "checked": 3,
    }
