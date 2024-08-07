"""
Verify freshness and validity of attachment bundles.

For each collection where the attachments bundle is enable, return the modification timestamp and number of attachments bundled.
"""

import io
import logging
import urllib.parse
import zipfile
from telescope.typings import CheckResult
from telescope.utils import ClientSession, retry_decorator, run_parallel, utcfromhttpdate, utcfromtimestamp

from .utils import KintoClient, fetch_signed_resources


EXPOSED_PARAMETERS = ["server"]

logger = logging.getLogger(__name__)


@retry_decorator
async def fetch_binary(url: str, **kwargs) -> bytes:
    human_url = urllib.parse.unquote(url)
    logger.debug(f"Fetch binary from '{human_url}'")
    async with ClientSession() as session:
        async with session.get(url, **kwargs) as response:
            return (response.status, response.headers["Last-Modified"], await response.read())


async def run(server: str, auth: str, margin_publication_days: int = 1) -> CheckResult:
    client = KintoClient(server_url=server, auth=auth)
    resources = await fetch_signed_resources(server, auth)

    resources = [r for r in resources if r["source"]["collection"] in ("intermediates",)]

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

    metadata_for_bundled = [(r, m) for r, m in resources_sources_metadata if m["data"].get("attachment", {}).get("bundle", False)]
    logger.info("%s collections with attachments bundle", len(metadata_for_bundled))

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    futures = []
    for resource, metadata in metadata_for_bundled:
        bid = resource["destination"]["bucket"]
        cid = metadata["data"]["id"]
        url = f"{base_url}bundles/{bid}--{cid}.zip"
        futures.append(fetch_binary(url, raise_for_status=True))
    bundles = await run_parallel(*futures)

    futures = []
    for resource, _ in metadata_for_bundled:
        futures.append(client.get_records_timestamp(bucket=resource["destination"]["bucket"], collection=resource["destination"]["collection"]))
    records_timestamps = await run_parallel(*futures)

    timestamps_metadata_bundles = zip(records_timestamps, metadata_for_bundled, bundles)

    result = {}
    success = True
    for timestamp, (resource, metadata), bundle in timestamps_metadata_bundles:
        status, modified, binary = bundle
        bid = resource["destination"]["bucket"]
        cid = metadata["data"]["id"]
        if status >= 400:
            result[f"{bid}/{cid}"] = "missing"
            success = False
            continue

        try:
            z = zipfile.ZipFile(io.BytesIO(binary))
            nfiles = len(z.namelist())
        except zipfile.BadZipFile:
            result[f"{bid}/{cid}"] = "bad zip"
            success = False
            continue

        bundle_ts = utcfromhttpdate(modified)
        records_ts = utcfromtimestamp(timestamp)
        if (records_ts - bundle_ts).days > margin_publication_days:
            result[f"{bid}/{cid}"] = "outdated"
            success = False
            continue

        result[f"{bid}/{cid}"] = {
            "size": len(bundle),
            "attachments": nfiles,
            "modified": modified,
        }

    return success, result

