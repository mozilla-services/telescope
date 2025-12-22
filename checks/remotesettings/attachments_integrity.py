"""
Every attachment in every collection has the right size and hash.

The URLs of invalid attachments is returned along with the number of checked records.
"""

import asyncio
import logging

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import (
    fetch_raw,
    limit_request_concurrency,
    run_in_process_pool,
    run_parallel,
    sha256hex,
)

from .utils import KintoClient


logger = logging.getLogger(__name__)


@limit_request_concurrency
async def test_attachment(attachment):
    url = attachment["location"]
    try:
        logger.debug(f"Fetch attachment from '{url}'")
        _, _, binary = await fetch_raw(url)
    except asyncio.TimeoutError:
        return {"url": url, "error": "timeout"}, False
    except aiohttp.ClientError as exc:
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
    total_size = 0
    for changeset in results:
        records = changeset["changes"]
        for record in records:
            if "attachment" not in record:
                continue
            attachment = record["attachment"]
            attachment["location"] = base_url + attachment["location"]
            attachments.append(attachment)
            total_size += attachment["size"]

    # Spread the load of attachments integrity check based on size.
    # Otherwise some slices may take much longer to complete than others.

    # We sort by attachment size descending. It's not mandatory, but
    # it gives us more observability of what slices are taking longer
    # to complete (big files or lots of small files).
    attachments.sort(key=lambda att: att["size"], reverse=True)
    # Compute the slice using percent of total size.
    slice_lower = (slice_percent[0] / 100.0) * total_size
    slice_upper = (slice_percent[1] / 100.0) * total_size
    lower_idx = 0
    accumulated_size = 0
    for attachment in attachments:
        if accumulated_size >= slice_lower:
            break
        accumulated_size += attachment["size"]
        lower_idx += 1
    upper_idx = lower_idx
    for attachment in attachments[lower_idx:]:
        accumulated_size += attachment["size"]
        upper_idx += 1
        if accumulated_size >= slice_upper:
            break
    print(
        f"Total size {total_size} Slice {slice_percent} => size {slice_lower:.0f}-{slice_upper:.0f} bytes"
    )
    print(f"Attachments slice indexes: {lower_idx}-{upper_idx} of {len(attachments)}")
    sliced = attachments[lower_idx:upper_idx]

    futures = [test_attachment(attachment) for attachment in sliced]
    results = await run_parallel(*futures)
    bad = [result for result, success in results if not success]
    return len(bad) == 0, {
        "bad": bad,
        "checked": len(sliced),
        "total": len(attachments),
    }
