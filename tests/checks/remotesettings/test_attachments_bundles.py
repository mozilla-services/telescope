import io
import zipfile

from checks.remotesettings.attachments_bundles import run


COLLECTION_URL = "/buckets/{}/collections/{}"
CHANGESET_URL = "/buckets/{}/collections/{}/changeset"


def build_zip(num_files=3):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i in range(num_files):
            file_name = f"fake_file_{i}.txt"
            zip_file.writestr(file_name, 1024 * "x")
    return zip_buffer.getvalue()


async def test_negative(mock_aioresponses):
    server_url = "http://fake.local/v1"
    mock_aioresponses.get(
        server_url + "/",
        payload={
            "capabilities": {
                "attachments": {"base_url": "http://cdn/"},
                "signer": {
                    "resources": [
                        {
                            "source": {"bucket": "main-workspace", "collection": None},
                            "preview": {"bucket": "main-preview", "collection": None},
                            "destination": {"bucket": "main", "collection": None},
                        }
                    ]
                },
            }
        },
        repeat=2,  # One for signed resources, one for attachment base URL.
    )
    mock_aioresponses.get(
        server_url + "/buckets/main-workspace/collections",
        payload={
            "data": [
                {"id": cid}
                for cid in ("missing", "ok", "badzip", "outdated", "late", "no-bundle")
            ]
        },
    )

    may8_ts = 389664061000
    may8_http = "Mon, 08 May 1982 00:01:01 GMT"
    may8_iso = "1982-05-08T00:01:01+00:00"

    changes_url = server_url + CHANGESET_URL.format("monitor", "changes")
    mock_aioresponses.get(
        changes_url,
        payload={
            "changes": [
                {
                    "id": "abc",
                    "bucket": "main",
                    "collection": "missing",
                    "last_modified": may8_ts,
                },
                {
                    "id": "efg",
                    "bucket": "main",
                    "collection": "ok",
                    "last_modified": may8_ts,
                },
                {
                    "id": "hij",
                    "bucket": "main",
                    "collection": "badzip",
                    "last_modified": may8_ts,
                },
                {
                    "id": "klm",
                    "bucket": "main",
                    "collection": "outdated",
                    "last_modified": may8_ts + 24 * 3600 * 1000 + 60 * 1000,
                },
                {
                    "id": "nop",
                    "bucket": "main",
                    "collection": "late",
                    "last_modified": may8_ts + 600 * 1000,
                },
                {
                    "id": "qrs",
                    "bucket": "main",
                    "collection": "no-bundle",
                    "last_modified": may8_ts,
                },
                {
                    "id": "tuv",
                    "bucket": "main",
                    "collection": "no-records",
                    "last_modified": may8_ts,
                },
            ]
        },
    )

    for cid in (
        "missing",
        "no-records",
        "ok",
        "badzip",
        "outdated",
        "late",
        "no-bundle",
    ):
        mock_aioresponses.get(
            server_url + COLLECTION_URL.format("main-workspace", cid),
            payload={
                "data": {
                    "id": cid,
                    "bucket": "main-workspace",
                    "attachment": {"bundle": cid != "no-bundle"},
                }
            },
        )

    mock_aioresponses.get("http://cdn/bundles/main--missing.zip", status=404)
    mock_aioresponses.get("http://cdn/bundles/main--no-records.zip", status=404)

    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("main", "no-records"),
        payload={"changes": []},
    )
    mock_aioresponses.get(
        server_url + CHANGESET_URL.format("main", "missing"),
        payload={"changes": [{"id": "r1"}, {"id": "r2"}]},
    )

    mock_aioresponses.get(
        "http://cdn/bundles/main--ok.zip",
        body=build_zip(),
        headers={"Last-Modified": may8_http},
    )
    mock_aioresponses.get(
        "http://cdn/bundles/main--outdated.zip",
        body=build_zip(num_files=6),
        headers={"Last-Modified": may8_http},
    )
    mock_aioresponses.get(
        "http://cdn/bundles/main--late.zip",
        body=build_zip(num_files=6),
        headers={"Last-Modified": may8_http},
    )
    mock_aioresponses.get(
        "http://cdn/bundles/main--badzip.zip",
        body=b"boom",
        headers={"Last-Modified": may8_http},
    )

    status, data = await run(server_url, auth="")

    assert status is False
    assert data == {
        "main/badzip": {"status": "bad zip"},
        "main/missing": {"status": "missing"},
        "main/no-records": {"status": "no records"},
        "main/ok": {
            "status": "ok",
            "attachments": 3,
            "collection_timestamp": "1982-05-08T00:01:01+00:00",
            "publication_timestamp": may8_iso,
            "size": 373,
        },
        "main/late": {
            "status": "ok",
            "attachments": 6,
            "collection_timestamp": "1982-05-08T00:11:01+00:00",
            "publication_timestamp": may8_iso,
            "size": 724,
        },
        "main/outdated": {
            "attachments": 6,
            "collection_timestamp": "1982-05-09T00:02:01+00:00",
            "publication_timestamp": may8_iso,
            "size": 724,
            "status": "outdated",
        },
    }
