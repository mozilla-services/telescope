"""
The HTML content of the page that lists blocked addons and plugins should
match the source of truth.

The list of missing or extras entries is returned, along with the source
timestamps.
"""

import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from telescope.typings import CheckResult
from telescope.utils import fetch_head, fetch_text, run_parallel

from .utils import KintoClient


EXPOSED_PARAMETERS = ["remotesettings_server", "blocked_pages"]

logger = logging.getLogger(__name__)


async def test_url(url):
    try:
        status, _ = await fetch_head(url)
        return status == 200
    except aiohttp.ClientError:
        return False


async def run(remotesettings_server: str, blocked_pages: str) -> CheckResult:
    # Read blocked page index to obtain the links.
    blocked_index = await fetch_text(blocked_pages)
    soup = BeautifulSoup(blocked_index, features="html.parser")
    urls = []
    for link in soup.find_all("a", href=re.compile(".html$")):
        urls.append(link["href"])

    # Make sure no link is broken.
    futures = [test_url(f"{blocked_pages}/{url}") for url in urls]
    results = await run_parallel(*futures)
    urls_success = zip(urls, results)
    missing = [url for url, success in urls_success if not success]

    # Compare list of blocked ids with the source of truth.
    client = KintoClient(server_url=remotesettings_server, bucket="blocklists")
    addons_records = await client.get_records(collection="addons")
    plugins_records = await client.get_records(collection="plugins")
    records_ids = [r.get("blockID", r["id"]) for r in plugins_records + addons_records]
    blocked_ids = [url.rsplit(".", 1)[0] for url in urls]
    extras_ids = set(blocked_ids) - set(records_ids)
    missing_ids = set(records_ids) - set(blocked_ids)

    addons_timestamp = int(await client.get_records_timestamp(collection="addons"))
    plugins_timestamp = int(await client.get_records_timestamp(collection="plugins"))
    certificates_timestamp = int(
        await client.get_records_timestamp(collection="certificates")
    )

    success = len(missing) == 0 and len(missing_ids) == 0 and len(extras_ids) == 0
    data = {
        "addons-timestamp": addons_timestamp,
        "plugins-timestamp": plugins_timestamp,
        "certificates-timestamp": certificates_timestamp,
        "broken-links": missing,
        "missing": list(missing_ids),
        "extras": list(extras_ids),
    }
    return success, data
