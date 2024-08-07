"""
Verify freshness and validity of attachment bundles.

For each collection where the attachments bundle is enable, return the modification timestamp and number of attachments bundled.
"""

import io
import logging
import zipfile
from telescope.typings import CheckResult
from telescope.utils import ClientSession, run_parallel, utcfromtimestamp

from .utils import KintoClient, fetch_signed_resources


EXPOSED_PARAMETERS = ["server"]

logger = logging.getLogger(__name__)

async def run(server: str, auth: str) -> CheckResult:
    client = KintoClient(server_url=server)
    resources = await fetch_signed_resources(server, auth)

    logger.debug("Fetch metadata of %s collections", len(resources))
    futures = [
        client.get_collection(
            bucket=resource["source"]["bucket"],
            collection=resource["source"]["collection"],
        )
        for resource in resources
    ]
    sources_metadata = await run_parallel(*futures)

    metadata_for_bundled = [m for m in sources_metadata if m.get("attachment", {}).get("bundle", False)]
    logger.info("%s collections with attachment bundle", len(metadata_for_bundled))

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    futures = []
    async with ClientSession() as session:
        for metadata in metadata_for_bundled:
            bid = metadata["data"]["bucket"]
            cid = metadata["data"]["id"]
            url = f"{base_url}/bundles/{bid}--{cid}.zip"
            async with session.get(url) as response:
                futures.append(response.read())
    bundles = await run_parallel(*futures)

    metadata_bundles = zip(metadata_for_bundled, bundles)

    result = {}
    for metadata, bundle in metadata_bundles:
        bid = metadata["data"]["bucket"]
        cid = metadata["data"]["id"]
        z = zipfile.ZipFile(io.BytesIO(bundle))
        result[f"{bid}/{cid}"] = {
            "size": len(bundle),
            "attachments": len(z.namelist()),
        }

    return True, result

