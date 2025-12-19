from unittest import mock

from checks.remotesettings.latest_approvals import get_latest_approvals, run
from checks.remotesettings.utils import KintoClient
from telescope.utils import utcnow


FAKE_AUTH = ""
HISTORY_URL = "/buckets/{}/history"
APPROVAL_TIMESTAMP = 1567790095111
INFOS = [
    {
        "timestamp": APPROVAL_TIMESTAMP,
        "datetime": "2019-09-06T17:14:55.106994",
        "by": "ldap:n@mozilla.com",
        "changes": {"create": 2, "delete": 1},
    }
]


async def test_get_latest_approvals(mock_aioresponses):
    server_url = "http://fake.local/v1"
    history_url = server_url + HISTORY_URL.format("bid")
    query_params = (
        "?resource_name=collection&target.data.id=cid"
        "&target.data.status=to-sign&_sort=-last_modified&_since=42&_limit=3"
    )
    mock_aioresponses.get(
        history_url + query_params,
        payload={
            "data": [
                {
                    "id": "0fdeba9f-d83c-4ab2-99f9-d852d6f22cae",
                    "last_modified": APPROVAL_TIMESTAMP,
                    "uri": "/buckets/bid/collections/cid",
                    "date": "2019-09-06T17:14:55.106994",
                    "action": "update",
                    "target": {
                        "data": {
                            "id": "cid",
                            "status": "to-sign",
                            "last_edit_by": "ldap:a@mozilla.com",
                            "last_modified": 1567790094461,
                            "last_edit_date": "2019-09-05T07:15:03.950868+00:00",
                            "last_review_by": "ldap:r@mozilla.com",
                            "last_review_date": "2019-04-16T19:28:10.065088+00:00",
                            "last_signature_by": "account:cloudservices_kinto_prod",
                            "last_editor_comment": "add layout property for existing and new save_login message",
                            "last_signature_date": "2019-09-04T19:41:57.068721+00:00",
                            "last_reviewer_comment": "",
                            "last_review_request_by": "ldap:e@mozilla.com",
                            "last_review_request_date": "2019-09-05T19:12:32.910831+00:00",
                        }
                    },
                    "user_id": "ldap:n@mozilla.com",
                    "collection_id": "cid",
                    "resource_name": "collection",
                }
            ]
        },
    )
    query_params = (
        "?resource_name=record&collection_id=cid"
        "&_since=0&_before={}"
        "&gt_target.data.last_modified=0&lt_target.data.last_modified={}"
    ).format(APPROVAL_TIMESTAMP + 1000, APPROVAL_TIMESTAMP)
    mock_aioresponses.get(
        history_url + query_params,
        payload={
            "data": [
                {"id": "r1", "action": "delete"},
                {"id": "r2", "action": "create"},
                {"id": "r3", "action": "create"},
            ]
        },
    )
    client = KintoClient(server_url=server_url)

    infos = await get_latest_approvals(
        client, "bid", "cid", max_approvals=2, min_timestamp=42
    )

    assert infos == INFOS


async def test_positive(mock_aioresponses):
    server_url = "http://fake.local/v1"
    module = "checks.remotesettings.latest_approvals"
    resources = [
        {
            "last_modified": utcnow().timestamp() * 1000,
            "source": {"bucket": "bid", "collection": "cid"},
        }
    ]
    with mock.patch(f"{module}.fetch_signed_resources", return_value=resources):
        with mock.patch(f"{module}.get_latest_approvals", return_value=INFOS):
            status, data = await run(server_url, FAKE_AUTH)

    assert status is True
    assert data == [{"source": "bid/cid", **INFOS[0]}]
