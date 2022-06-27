from datetime import datetime
from unittest import mock

from checks.remotesettings.total_approvals import get_approvals, run
from checks.remotesettings.utils import KintoClient
from telescope.utils import utcnow
from tests.utils import patch_async


FAKE_AUTH = "Bearer abc"
HISTORY_URL = "/buckets/{}/history"


async def test_get_approvals(mock_responses):
    server_url = "http://fake.local/v1"
    history_url = server_url + HISTORY_URL.format("bid")
    query_params = (
        "?resource_name=collection&target.data.status=to-sign"
        "&action=update&_since=42&_before=52"
    )
    mock_responses.get(
        history_url + query_params,
        payload={
            "data": [
                {"id": "abc", "collection_id": "cid"},
                {"id": "efg", "collection_id": "cfr"},
                {"id": "hij", "collection_id": "cfr"},
            ]
        },
    )
    client = KintoClient(server_url=server_url)

    infos = await get_approvals(client, "bid", min_timestamp=42, max_timestamp=52)

    assert infos == {
        "cid": 1,
        "cfr": 2,
    }


async def test_positive(mock_responses):
    server_url = "http://fake.local/v1"
    module = "checks.remotesettings.total_approvals"
    resources = [
        {
            "last_modified": utcnow().timestamp() * 1000,
            "source": {"bucket": "bid", "collection": None},
        }
    ]
    totals = {
        "cid": 10,
        "cfr": 5,
    }
    with mock.patch(f"{module}.utcnow", return_value=datetime(1982, 5, 8)):
        with patch_async(f"{module}.fetch_signed_resources", return_value=resources):
            with patch_async(f"{module}.get_approvals", return_value=totals):

                status, data = await run(server_url, FAKE_AUTH, period_days=1)

    assert status is True
    assert data == [{"date": "1982-05-07", "totals": 15, "bid/cid": 10, "bid/cfr": 5}]
