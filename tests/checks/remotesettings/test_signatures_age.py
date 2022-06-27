import datetime
from unittest import mock

from checks.remotesettings.signatures_age import get_signature_age_hours, run
from checks.remotesettings.utils import KintoClient
from tests.utils import patch_async


FAKE_AUTH = "Bearer abc"
COLLECTION_URL = "/buckets/{}/collections/{}"
MODULE = "checks.remotesettings.signatures_age"
RECORDS_URL = COLLECTION_URL + "/records"
RESOURCES = [{"source": {"bucket": "bid", "collection": "cid"}}]


async def test_get_signature_age_hours(mock_responses):
    server_url = "http://fake.local/v1"
    collection_url = server_url + COLLECTION_URL.format("bid", "cid")
    mock_responses.get(
        collection_url,
        payload={
            "data": {
                "id": "cid",
                "last_signature_date": "2019-09-08T15:11:09.142054+00:00",
            }
        },
    )
    client = KintoClient(server_url=server_url)

    real_hours = await get_signature_age_hours(client, "bid", "cid")

    fake_now = datetime.datetime(2019, 9, 9, 14, 57, 38, 297837).replace(
        tzinfo=datetime.timezone.utc
    )
    with mock.patch(f"{MODULE}.utcnow", return_value=fake_now):
        hours = await get_signature_age_hours(client, "bid", "cid")

    assert hours == 23
    assert real_hours > 280  # age at the time this test was written.


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    module = "checks.remotesettings.signatures_age"
    with patch_async(f"{module}.fetch_signed_resources", return_value=RESOURCES):
        with patch_async(f"{module}.get_signature_age_hours", return_value=3):

            status, data = await run(server_url, FAKE_AUTH, max_age=4)

    assert status is True
    assert data == {}


async def test_negative(mock_responses):
    server_url = "http://fake.local/v1"
    with patch_async(f"{MODULE}.fetch_signed_resources", return_value=RESOURCES):
        with patch_async(f"{MODULE}.get_signature_age_hours", return_value=5):

            status, data = await run(server_url, FAKE_AUTH, max_age=4)

    assert status is False
    assert data == {"bid/cid": 5}
