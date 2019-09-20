"""
The HTML content of the page that lists blocked addons and plugins should
match the source of truth.

The list of missing or extras entries is returned, along with the XML and
source timestamps.
"""
import logging
import re
import xml.etree.ElementTree

import aiohttp
from bs4 import BeautifulSoup

from poucave.typings import CheckResult
from poucave.utils import fetch_text, fetch_head, run_parallel
from .utils import KintoClient


EXPOSED_PARAMETERS = ["remotesettings_server", "blocked_pages"]
BLOCKLIST_URL_PATH = "/blocklist/3/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}/46.0/"

logger = logging.getLogger(__name__)


async def test_url(url):
    try:
        status, _ = await fetch_head(url)
        return status == 200
    except aiohttp.ClientError:
        return False


async def run(remotesettings_server: str, blocked_pages: str) -> CheckResult:
    xml_url = remotesettings_server + BLOCKLIST_URL_PATH

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
    records_ids = [
        r.get("blockID", r["id"])
        for r in await client.get_records(collection="plugins")
        + await client.get_records(collection="addons")
    ]
    blocked_ids = [url.rsplit(".", 1)[0] for url in urls]
    extras_ids = set(blocked_ids) - set(records_ids)
    missing_ids = set(records_ids) - set(blocked_ids)

    """
    <?xml version="1.0" encoding="UTF-8"?>
    <blocklist xmlns="http://www.mozilla.org/2006/addons-blocklist" lastupdate="1568816392824">
    ...
    """
    timestamp = await client.get_records_timestamp(
        bucket="monitor", collection="changes"
    )
    xml_content = await fetch_text(xml_url)
    root = xml.etree.ElementTree.fromstring(xml_content)
    xml_timestamp = root.attrib["lastupdate"]

    success = (
        len(missing) == 0
        and len(missing_ids) == 0
        and len(extras_ids) == 0
        and timestamp == xml_timestamp
    )
    data = {
        "xml-update": xml_timestamp,
        "timestamp": timestamp,
        "broken-links": missing,
        "missing": list(missing_ids),
        "extras": list(extras_ids),
    }
    return success, data
