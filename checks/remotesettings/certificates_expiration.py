"""
Signature certificates should not expire for at least some minimum number of days.

Returns a list of collections whose certificate expires too soon, along with their
expiration date and x5u URL.
"""
import datetime
import logging
from typing import Dict, Tuple

import cryptography
import cryptography.x509
from autograph_utils import split_pem
from cryptography.hazmat.backends import default_backend as crypto_default_backend

from telescope.typings import CheckResult
from telescope.utils import fetch_text, run_parallel, utcnow

from .utils import KintoClient


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = ["server", "min_remaining_days"]

# Bound the alert thresholds.
LOWER_MIN_REMAINING_DAYS = 7
UPPER_MIN_REMAINING_DAYS = 60


async def fetch_certs(x5u):
    cert_pem = await fetch_text(x5u)
    logger.debug(f"Parse PEM file from {x5u}")
    pems = split_pem(cert_pem.encode("utf-8"))
    certs = [
        cryptography.x509.load_pem_x509_certificate(
            pem, backend=crypto_default_backend()
        )
        for pem in pems
    ]
    return certs


async def fetch_collection_metadata(server_url, entry):
    client = KintoClient(
        server_url=server_url, bucket=entry["bucket"], collection=entry["collection"]
    )
    collection = await client.get_collection(_expected=entry["last_modified"])
    return collection["data"]


async def run(
    server: str,
    percentage_remaining_validity: int = 10,
    min_remaining_days: int = LOWER_MIN_REMAINING_DAYS,
) -> CheckResult:
    client = KintoClient(server_url=server)
    entries = await client.get_monitor_changes()

    # First, fetch all collections metadata in parallel.
    futures = [fetch_collection_metadata(server, entry) for entry in entries]
    results = await run_parallel(*futures)
    entries_metadata = zip(entries, results)

    # Second, deduplicate the list of x5u URLs and fetch them in parallel.
    x5us = list(set(metadata["signature"]["x5u"] for metadata in results))
    futures = [fetch_certs(x5u) for x5u in x5us]
    results = await run_parallel(*futures)

    validity: Dict[str, Tuple] = {}
    for x5u, certs in zip(x5us, results):
        # For each cert of the chain, keep track of the one that ends the earliest.
        for cert in certs:
            end = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
            if x5u not in validity or end < validity[x5u][0]:
                start = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
                lifespan = (end - start).days
                validity[x5u] = end, lifespan

    # Return collections whose certificate expires too soon.
    errors: Dict[str, Dict] = {}
    for entry, metadata in entries_metadata:
        cid = "{bucket}/{collection}".format(**entry)
        x5u = metadata["signature"]["x5u"]
        end, lifespan = validity[x5u]

        # The minimum remaining days depends on the certificate lifespan.
        relative_minimum = lifespan * percentage_remaining_validity / 100
        bounded_minimum = int(
            min(UPPER_MIN_REMAINING_DAYS, max(min_remaining_days, relative_minimum))
        )
        remaining_days = (end - utcnow()).days
        logger.debug(
            f"{cid} cert lasts {lifespan} days and ends in {remaining_days} days "
            f"({remaining_days - bounded_minimum} days before alert)."
        )
        if remaining_days < bounded_minimum:
            errors[cid] = {"x5u": x5u, "expires": end.isoformat()}

    """
    {
      "main/normandy-recipes": {
        "x5u": "https://content-signature-2.cdn.mozilla.net/chains/remote-settings.content-signature.mozilla.org-2019-10-22-18-54-26.chain",
        "expires": "2019-10-22T18:54:26"
    },
    """
    return len(errors) == 0, errors
