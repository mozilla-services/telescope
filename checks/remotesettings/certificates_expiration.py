"""
Signature certificates should expire in a minimum number of days.

The list of collections whose certificate expires too soon is returned, along
Signature certificates should not expire for at least some minimum number of days.

Returns a list of collections whose certificate expires too soon, along with their expiration date and x5u URL.
"""
import asyncio
import logging
from datetime import datetime

import cryptography
import cryptography.x509
import requests
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from poucave.typings import CheckResult

from .utils import KintoClient as Client


logger = logging.getLogger(__name__)


def fetch_collection_metadata(server_url, entry):
    client = Client(
        server_url=server_url, bucket=entry["bucket"], collection=entry["collection"]
    )
    return client.get_collection(_expected=entry["last_modified"])["data"]


def fetch_certificate_expiration(x5u: str) -> datetime:
    resp = requests.get(x5u)
    cert_pem = resp.text.encode("utf-8")
    cert = cryptography.x509.load_pem_x509_certificate(
        cert_pem, crypto_default_backend()
    )
    return cert.not_valid_after


async def run(server: str, min_remaining_days: int) -> CheckResult:
    loop = asyncio.get_event_loop()

    client = Client(server_url=server, bucket="monitor", collection="changes")
    entries = client.get_records()

    futures = [
        loop.run_in_executor(None, fetch_collection_metadata, server, entry)
        for entry in entries
    ]
    results = await asyncio.gather(*futures)
    entries_metadata = zip(entries, results)

    x5us = list({metadata["signature"]["x5u"] for metadata in results})
    futures = [
        loop.run_in_executor(None, fetch_certificate_expiration, x5u) for x5u in x5us
    ]
    results = await asyncio.gather(*futures)
    expirations = {x5u: expiration for x5u, expiration in zip(x5us, results)}

    errors = {}
    for entry, metadata in entries_metadata:
        cid = "{bucket}/{collection}".format(**entry)
        x5u = metadata["signature"]["x5u"]

        expiration = expirations[x5u]
        remaining_days = (expiration - datetime.now()).days
        if remaining_days < min_remaining_days:
            errors[cid] = {"x5u": x5u, "expires": expiration.isoformat()}

    """
    {
      "main/normandy-recipes": {
        "x5u": "https://content-signature-2.cdn.mozilla.net/chains/remote-settings.content-signature.mozilla.org-2019-10-22-18-54-26.chain",
        "expires": "2019-10-22T18:54:26"
    },
    """
    return len(errors) == 0, errors
