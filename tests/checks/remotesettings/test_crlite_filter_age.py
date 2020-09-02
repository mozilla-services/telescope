from time import time

from checks.remotesettings.crlite_filter_age import run


SERVER_URL = "http://fake.local/v1"
RECORDS_URL = (
    SERVER_URL + "/buckets/security-state/collections/cert-revocations/records"
)


def add_mock_responses(mock_responses, hours):
    now = time() * 1000
    records = [
        {"id": str(i), "effectiveTimestamp": now - h * 3600 * 1000}
        for i, h in enumerate(hours)
    ]
    mock_responses.get(RECORDS_URL, payload={"data": records})


async def test_positive(mock_responses):
    add_mock_responses(mock_responses, [11, 5, 42])

    status, data = await run(SERVER_URL)
    assert status is True
    assert data == 5


async def test_negative(mock_responses):
    add_mock_responses(mock_responses, [61, 55, 42])

    status, data = await run(SERVER_URL)
    assert status is False
    assert data == 42
