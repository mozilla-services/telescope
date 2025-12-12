from time import time

from checks.remotesettings.crlite_filter_age import run


SERVER_URL = "http://fake.local/v1"
RECORDS_URL = (
    SERVER_URL + "/buckets/security-state/collections/cert-revocations/records"
)


def add_mock_aioresponses(mock_aioresponses, hours):
    now = time() * 1000
    records = [
        {"id": str(i), "effectiveTimestamp": now - h * 3600 * 1000}
        for i, h in enumerate(hours)
    ]
    mock_aioresponses.get(RECORDS_URL, payload={"data": records})


async def test_positive(mock_aioresponses):
    add_mock_aioresponses(mock_aioresponses, [11, 5, 42])

    status, data = await run(SERVER_URL)
    assert status is True
    assert 5 <= data <= 5.01


async def test_negative(mock_aioresponses):
    add_mock_aioresponses(mock_aioresponses, [61, 55, 42])

    status, data = await run(SERVER_URL)
    assert status is False
    assert 42 <= data <= 42.01
