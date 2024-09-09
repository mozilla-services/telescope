"""
Verify freshness and validity of attachment bundles.

For each collection where the attachments bundle is enable, return the modification timestamp and number of attachments bundled.
"""

import io
import logging
import urllib.parse
import zipfile
from typing import Any

from telescope.typings import CheckResult
from telescope.utils import (
    ClientSession,
    retry_decorator,
    run_parallel,
    utcfromhttpdate,
    utcfromtimestamp,
)

from .utils import KintoClient, fetch_signed_resources


EXPOSED_PARAMETERS = ["server"]

logger = logging.getLogger(__name__)


@retry_decorator
async def fetch_binary(url: str, **kwargs) -> tuple[int, str, bytes]:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch binary from '{human_url}'")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return (
                response.status,
                response.headers.get("Last-Modified", "Mon, 01 Jan 1970 00:00:00 GMT"),
                await response.read(),
            )


async def run(
    server: str, auth: str, margin_publication_hours: int = 12
) -> CheckResult:
    client = KintoClient(server_url=server, auth=auth)
    resources = await fetch_signed_resources(server, auth)

    # resources = [r for r in resources if r["source"]["collection"] in ("intermediates",)]

    logger.debug("Fetch metadata of %s collections", len(resources))
    futures = [
        client.get_collection(
            bucket=resource["source"]["bucket"],
            id=resource["source"]["collection"],
        )
        for resource in resources
    ]
    sources_metadata = await run_parallel(*futures)
    resources_sources_metadata = zip(resources, sources_metadata)

    metadata_for_bundled = [
        (r, m)
        for r, m in resources_sources_metadata
        if m["data"].get("attachment", {}).get("bundle", False)
    ]
    logger.info("%s collections with attachments bundle", len(metadata_for_bundled))
    assert metadata_for_bundled, metadata_for_bundled
    records_timestamps = [
        resource["last_modified"] for resource, _ in metadata_for_bundled
    ]

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    futures_bundles = []
    for resource, metadata in metadata_for_bundled:
        bid = resource["destination"]["bucket"]
        cid = metadata["data"]["id"]
        url = f"{base_url}bundles/{bid}--{cid}.zip"
        futures_bundles.append(fetch_binary(url))
    bundles = await run_parallel(*futures_bundles)

    timestamps_metadata_bundles = zip(records_timestamps, metadata_for_bundled, bundles)

    result: dict[str, dict[str, Any]] = {}
    success = True
    for timestamp, (resource, metadata), bundle in timestamps_metadata_bundles:
        http_status, modified, binary = bundle
        bid = resource["destination"]["bucket"]
        cid = metadata["data"]["id"]
        if http_status >= 400:
            result[f"{bid}/{cid}"] = {"status": "missing"}
            success = False
            continue

        try:
            z = zipfile.ZipFile(io.BytesIO(binary))
            nfiles = len(z.namelist())
        except zipfile.BadZipFile:
            result[f"{bid}/{cid}"] = {"status": "bad zip"}
            success = False
            continue

        bundle_ts = utcfromhttpdate(modified)
        records_ts = utcfromtimestamp(timestamp)
        status = (
            "outdated"
            if ((records_ts - bundle_ts).total_seconds() / 3600)
            > margin_publication_hours
            else "ok"
        )
        result[f"{bid}/{cid}"] = {
            "status": status,
            "size": len(binary),
            "attachments": nfiles,
            "publication_timestamp": bundle_ts.isoformat(),
            "collection_timestamp": records_ts.isoformat(),
        }

    return success, result
