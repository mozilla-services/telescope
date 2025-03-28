import json
from contextlib import asynccontextmanager
from unittest import mock

from checks.remotesettings.push_timestamp import BROADCAST_ID, get_push_timestamp, run
from telescope.utils import utcfromtimestamp


MODULE = "checks.remotesettings.push_timestamp"


async def test_positive(mock_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/changeset"
    mock_responses.get(
        url,
        status=200,
        payload={
            "changes": [
                {"id": "a", "bucket": "main-preview", "last_modified": 2000000000000},
                {"id": "b", "bucket": "main", "last_modified": 1273086234731},
                {"id": "c", "bucket": "main", "last_modified": 1573086234731},
            ]
        },
    )

    with mock.patch(f"{MODULE}.get_push_timestamp", return_value="1573086234731"):
        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is True
    assert data == {
        "remotesettings": {
            "datetime": "2019-11-07T00:23:54.731000+00:00",
            "timestamp": "1573086234731",
        },
        "push": {
            "datetime": "2019-11-07T00:23:54.731000+00:00",
            "timestamp": "1573086234731",
        },
    }


async def test_positive_with_margin(mock_responses):
    server_timestamp = 1573086234731
    server_datetime = utcfromtimestamp(server_timestamp)

    url = "http://server.local/v1/buckets/monitor/collections/changes/changeset"
    mock_responses.get(
        url,
        status=200,
        payload={
            "changes": [
                {"id": "b", "bucket": "main", "last_modified": server_timestamp},
            ]
        },
    )

    with mock.patch(f"{MODULE}.utcnow", return_value=server_datetime):
        with mock.patch(f"{MODULE}.get_push_timestamp", return_value=42):
            status, _ = await run(
                remotesettings_server="http://server.local/v1", push_server=""
            )

    assert status is True


async def test_negative(mock_responses):
    url = "http://server.local/v1/buckets/monitor/collections/changes/changeset"
    mock_responses.get(
        url,
        status=200,
        payload={
            "changes": [{"id": "a", "bucket": "main", "last_modified": 1573086234731}]
        },
    )

    with mock.patch(f"{MODULE}.get_push_timestamp", return_value="2573086234731"):
        status, data = await run(
            remotesettings_server="http://server.local/v1", push_server=""
        )

    assert status is False
    assert data == {
        "remotesettings": {
            "datetime": "2019-11-07T00:23:54.731000+00:00",
            "timestamp": "1573086234731",
        },
        "push": {
            "datetime": "2051-07-16T02:10:34.731000+00:00",
            "timestamp": "2573086234731",
        },
    }


async def test_get_push_timestamp():
    class FakeConnection:
        async def send(self, value):
            self.sent = value

        async def recv(self):
            return json.dumps({"broadcasts": {BROADCAST_ID: '"42"'}})

    fake_connection = FakeConnection()

    @asynccontextmanager
    async def fake_connect(url):
        yield fake_connection

    with mock.patch("checks.remotesettings.push_timestamp.websockets") as mocked:
        mocked.connect = fake_connect

        result = await get_push_timestamp("ws://fake")

    assert json.loads(fake_connection.sent) == {
        "messageType": "hello",
        "broadcasts": {BROADCAST_ID: "v0"},
        "use_webpush": True,
    }
    assert result == "42"
