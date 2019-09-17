from unittest import mock

import datetime
from kinto_http import Client

from checks.remotesettings.signatures_age import run, get_signature_age_hours


FAKE_AUTH = ""
COLLECTION_URL = "/buckets/{}/collections/{}"
MODULE = "checks.remotesettings.signatures_age"
RECORDS_URL = COLLECTION_URL + "/records"
RESOURCES = [{"source": {"bucket": "bid", "collection": "cid"}}]


def test_get_signature_age_hours(mocked_responses):
    server_url = "http://fake.local/v1"
    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mocked_responses.get(
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
    module = "checks.remotesettings.signatures_age"
    with mock.patch(f"{module}.fetch_signed_resources", return_value=RESOURCES):
        with mock.patch(f"{module}.get_signature_age_hours", return_value=3):

            status, data = await run(server_url, FAKE_AUTH, max_age=4)

    assert status is True
    assert data == {}


async def test_negative(mocked_responses):
    server_url = "http://fake.local/v1"
    with mock.patch(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        with mock.patch(f"{MODULE}.get_signature_age_hours", return_value=5):

            status, data = await run(server_url, FAKE_AUTH, max_age=4)

    assert status is False
    assert data == {"bid/cid": 5}
