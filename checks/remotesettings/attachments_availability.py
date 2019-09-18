"""
Every attachment in every collection should be avaailable.

The URLs of unreachable attachments is returned along with the number of checked records.
"""
import asyncio

import aiohttp

from poucave.typings import CheckResult

from .utils import KintoClient


async def test_url(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.head(url) as response:
                return response.status == 200
        except aiohttp.client_exceptions.ClientError:
            return False


async def run(server: str) -> CheckResult:
    client = KintoClient(server_url=server, bucket="monitor", collection="changes")

    info = await client.server_info()
    base_url = info["capabilities"]["attachments"]["base_url"]

    # Fetch collections records in parallel.
    entries = await client.get_records()
    futures = [
        client.get_records(
            bucket=entry["bucket"],
            collection=entry["collection"],
            _expected=entry["last_modified"],
        )
        for entry in entries
        if "preview" not in entry["bucket"]
    ]
    results = await asyncio.gather(*futures)

    # For each record that has an attachment, send a HEAD request to its url.
    urls = []
    for (entry, records) in zip(entries, results):
        for record in records:
            if "attachment" not in record:
                continue
            url = base_url + record["attachment"]["location"]
            urls.append(url)

    futures = [test_url(url) for url in urls]
    results = await asyncio.gather(*futures)

    # Check if there's any missing.
    missing = [url for success, url in zip(results, urls) if not success]
    return len(missing) == 0, {"missing": missing, "checked": len(results)}
