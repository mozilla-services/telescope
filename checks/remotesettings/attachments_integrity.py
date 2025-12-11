"""
Every attachment in every collection has the right size and hash.

The URLs of invalid attachments is returned along with the number of checked records.
"""

import asyncio
import logging
import math

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import (
    ClientSession,
    limit_request_concurrency,
    run_in_process_pool,
    run_parallel,
    sha256hex,
)

from .utils import KintoClient


logger = logging.getLogger(__name__)


@limit_request_concurrency
async def test_attachment(session, attachment):
    url = attachment["location"]
    try:
        logger.debug(f"Fetch attachment from '{url}'")
        async with session.get(url) as response:
            binary = await response.read()
    except asyncio.TimeoutError:
        return {"url": url, "error": "timeout"}, False
    except aiohttp.client_exceptions.ClientError as exc:
        return {"url": url, "error": str(exc)}, False

    if (bz := len(binary)) != (az := attachment["size"]):
        return {"url": url, "error": f"size differ ({bz}!={az})"}, False

    if (bh := await run_in_process_pool(sha256hex, binary)) != (
        ah := attachment["hash"]
    ):
        return {"url": url, "error": f"hash differ ({bh}!={ah})"}, False

    return {}, True


async def run(server: str, slice_percent: tuple[int, int] = (0, 100)) -> CheckResult:
    client = KintoClient(server_url=server)

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    # Fetch collections records in parallel.
    entries = await client.get_monitor_changes()
    futures = [
        client.get_changeset(
            bucket=entry["bucket"],
            collection=entry["collection"],
            params={"_expected": entry["last_modified"]},
        )
        for entry in entries
        if "preview" not in entry["bucket"]
    ]
    results = await run_parallel(*futures)

    # For each record that has an attachment, check the attachment content.
    attachments = []
    for entry, changeset in zip(entries, results):
        records = changeset["changes"]
        for record in records:
            if "attachment" not in record:
                continue
            attachment = record["attachment"]
            attachment["location"] = base_url + attachment["location"]
            attachments.append(attachment)

    lower_idx = math.floor(slice_percent[0] / 100.0 * len(attachments))
    upper_idx = math.ceil(slice_percent[1] / 100.0 * len(attachments))

    async with ClientSession() as session:
        futures = [
            test_attachment(session, attachment)
            for attachment in attachments[lower_idx:upper_idx]
        ]
        results = await run_parallel(*futures)
    bad = [result for result, success in results if not success]
    return len(bad) == 0, {"bad": bad, "checked": len(attachments)}
