import asyncio
from unittest import mock

import pytest

from checks.remotesettings.attachments_integrity import run


CHANGESET_URL = "/buckets/{}/collections/{}/changeset"


async def test_positive(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + CHANGESET_URL.format("bid", "cid") + "?_expected=42"
    mock_aioresponses.get(
        records_url,
        payload={
            "changes": [
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


async def test_negative(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + CHANGESET_URL.format("bid", "cid") + "?_expected=42"
    mock_aioresponses.get(
        records_url,
        payload={
            "changes": [
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
                {
                    "id": "opq",
                    "attachment": {"size": 42, "hash": "boh", "location": "file3.jpg"},
                },
                {"id": "lmn"},
            ]
        },
    )
    mock_aioresponses.get("http://cdn/file1.jpg", body=b"a" * 5)
    mock_aioresponses.get("http://cdn/file2.jpg", body=b"a" * 10)
    mock_aioresponses.get(
        "http://cdn/file3.jpg", exception=asyncio.TimeoutError("Connection timeout")
    )

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
            {
                "error": "timeout",
                "url": "http://cdn/file3.jpg",
            },
        ],
        "checked": 4,
    }


@pytest.mark.parametrize(
    ("slice_percent", "expected_lower", "expected_upper"),
    [
        ((0, 100), 0, 99),
        ((0, 25), 0, 24),
        ((25, 50), 25, 49),
        ((50, 75), 50, 74),
        ((75, 100), 75, 99),
        ((0, 33), 0, 32),
        ((33, 66), 33, 65),
        ((66, 100), 66, 99),
    ],
)
async def test_urls_slicing(
    slice_percent, expected_lower, expected_upper, mock_aioresponses
):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + CHANGESET_URL.format("bid", "cid") + "?_expected=42"
    mock_aioresponses.get(
        records_url,
        payload={
            "changes": [
                {"id": f"id{i}", "attachment": {"location": f"file{i}.jpg"}}
                for i in range(100)
            ]
        },
    )

    with mock.patch(
        "checks.remotesettings.attachments_integrity.test_attachment"
    ) as mocked:
        mocked.return_value = {}, True
        await run(server_url, slice_percent=slice_percent)
    calls = mocked.call_args_list
    assert calls[0][0][1]["location"] == f"http://cdn/file{expected_lower}.jpg"
    assert calls[-1][0][1]["location"] == f"http://cdn/file{expected_upper}.jpg"
