"""
Every attachment in every collection should be avaailable.

The URLs of unreachable attachments is returned along with the number of checked records.
"""

import math

import aiohttp

from telescope.typings import CheckResult
from telescope.utils import fetch_head, run_parallel

from .utils import KintoClient


async def test_url(url):
    try:
        status, _ = await fetch_head(url)
        return status == 200
    except aiohttp.ClientError:
        return False


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

    # For each record that has an attachment, send a HEAD request to its url.
    urls = []
    for entry, changeset in zip(entries, results):
        records = changeset["changes"]
        for record in records:
            if "attachment" not in record:
                continue
            url = base_url + record["attachment"]["location"]
            urls.append(url)

    lower_idx = math.floor(slice_percent[0] / 100.0 * len(urls))
    upper_idx = math.ceil(slice_percent[1] / 100.0 * len(urls))
    sliced = urls[lower_idx:upper_idx]

    futures = [test_url(url) for url in sliced]
    results = await run_parallel(*futures)
    missing = [url for url, success in zip(sliced, results) if not success]

    return len(missing) == 0, {
        "missing": missing,
        "checked": len(sliced),
        "total": len(urls),
    }
