from unittest import mock

import datetime
import responses
from kinto_http import Client

from checks.remotesettings.signatures_age import (
    run,
    get_signature_age_hours,
    fetch_source_collections,
)


FAKE_AUTH = ""
COLLECTION_URL = "/buckets/{}/collections/{}"
MODULE = "checks.remotesettings.signatures_age"
RECORDS_URL = COLLECTION_URL + "/records"


def test_fetch_source_collections(mocked_responses):
    server_url = "http://fake.local/v1"
    mocked_responses.add(
        responses.GET,
        server_url + "/",
        json={
            "capabilities": {
                "signer": {
                    "resources": [
                        {
                            "source": {"bucket": "blog-workspace", "collection": None},
                            "preview": {"bucket": "blog-preview", "collection": None},
                            "destination": {"bucket": "blog", "collection": None},
                        },
                        {
                            "source": {
                                "bucket": "security-workspace",
                                "collection": "blocklist",
                            },
                            "destination": {
                                "bucket": "security",
                                "collection": "blocklist",
                            },
                        },
                    ]
                }
            }
        },
    )
    changes_url = server_url + RECORDS_URL.format("monitor", "changes")
    mocked_responses.add(
        responses.GET,
        changes_url,
        json={
            "data": [
                {
                    "id": "abc",
                    "bucket": "blog",
                    "collection": "articles",
                    "last_modified": 42,
                },
                {
                    "id": "def",
                    "bucket": "security",
                    "collection": "blocklist",
                    "last_modified": 41,
                },
            ]
        },
    )
    client = Client(server_url=server_url)

    collections = fetch_source_collections(client)

    assert collections == [
        ("blog-workspace", "articles"),
        ("security-workspace", "blocklist"),
    ]


def test_get_signature_age_hours(mocked_responses):
    server_url = "http://fake.local/v1"
    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mocked_responses.add(
        responses.GET,
        collection_url,
        json={
            "data": {
                "id": "cid",
                "last_signature_date": "2019-09-08T15:11:09.142054+00:00",
            }
        },
    )
    client = Client(server_url=server_url)
    fake_now = datetime.datetime(2019, 9, 9, 14, 57, 38, 297837).replace(
        tzinfo=datetime.timezone.utc
    )

    with mock.patch(f"{MODULE}.utcnow", return_value=fake_now):
        hours = get_signature_age_hours(client, "bid", "cid")

    assert hours == 23


async def test_positive(mocked_responses):
    server_url = "http://fake.local/v1"
    collections = [("bid", "cid")]
    module = "checks.remotesettings.signatures_age"
    with mock.patch(f"{module}.fetch_source_collections", return_value=collections):
        with mock.patch(f"{module}.get_signature_age_hours", return_value=3):

            status, data = await run({}, server_url, FAKE_AUTH, max_age=4)

    assert status is True
    assert data == {"bid/cid": 3}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    collections = [("bid", "cid")]
    with mock.patch(f"{MODULE}.fetch_source_collections", return_value=collections):
        with mock.patch(f"{MODULE}.get_signature_age_hours", return_value=5):

            status, data = await run({}, server_url, FAKE_AUTH, max_age=4)

    assert status is False
    assert data == {"bid/cid": 5}


async def test_negative_queryparam(mocked_responses):
    server_url = "http://fake.local/v1"
    collections = [("bid", "cid")]
    with mock.patch(f"{MODULE}.fetch_source_collections", return_value=collections):
        with mock.patch(f"{MODULE}.get_signature_age_hours", return_value=3):

            status, data = await run({"max_age": "2"}, server_url, FAKE_AUTH, max_age=4)

    assert status is False
    assert data == {"bid/cid": 3}
