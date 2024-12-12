from unittest import mock

import pytest

from checks.remotesettings.attachments_availability import run


CHANGESET_URL = "/buckets/{}/collections/{}/changeset"
RECORDS_URL = "/buckets/{}/collections/{}/records"


async def test_positive(mock_responses, mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mock_responses.get(
        records_url,
        payload={
            "data": [
                {"id": "abc", "attachment": {"location": "file1.jpg"}},
                {"id": "efg", "attachment": {"location": "file2.jpg"}},
                {"id": "ijk"},
            ]
        },
    )
    mock_aioresponses.head("http://cdn/file1.jpg")
    mock_aioresponses.head("http://cdn/file2.jpg")

    status, data = await run(server_url)

    # assert status is True
    assert data == {"missing": [], "checked": 2}


async def test_negative(mock_responses, mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mock_responses.get(
        records_url,
        payload={
            "data": [
                {"id": "abc", "attachment": {"location": "file.jpg"}},
                {"id": "efg", "attachment": {"location": "missing.jpg"}},
                {"id": "ijk"},
            ]
        },
    )
    mock_aioresponses.head("http://cdn/file.jpg")

    status, data = await run(server_url)

    assert status is False
    assert data == {"missing": ["http://cdn/missing.jpg"], "checked": 2}


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
    slice_percent, expected_lower, expected_upper, mock_responses
):
    server_url = "http://fake.local/v1"
    mock_responses.get(
        server_url + "/",
        payload={"capabilities": {"attachments": {"base_url": "http://cdn/"}}},
    )
    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_responses.get(
        changes_url,
        payload={
            "changes": [
                {"id": "abc", "bucket": "bid", "collection": "cid", "last_modified": 42}
            ]
        },
    )
    records_url = server_url + RECORDS_URL.format("bid", "cid") + "?_expected=42"
    mock_responses.get(
        records_url,
        payload={
            "data": [
                {"id": f"id{i}", "attachment": {"location": f"file{i}.jpg"}}
                for i in range(100)
            ]
        },
    )

    with mock.patch(
        "checks.remotesettings.attachments_availability.test_url"
    ) as mocked:
        await run(server_url, slice_percent=slice_percent)
    calls = mocked.call_args_list
    assert calls[0][0] == (f"http://cdn/file{expected_lower}.jpg",)
    assert calls[-1][0] == (f"http://cdn/file{expected_upper}.jpg",)
