"""
Signatures should be valid for each collection content.

The errors are returned for each concerned collection.
"""

import logging
import operator
import time
from typing import List, Optional

import canonicaljson
from autograph_utils import (
    BadCertificate,
    BadSignature,
    MemoryCache,
    SignatureVerifier,
    decode_mozilla_hash,
)

from telescope.typings import CheckResult
from telescope.utils import ClientSession, retry_decorator, run_parallel

from .utils import KintoClient


logger = logging.getLogger(__name__)


@retry_decorator
async def validate_signature(verifier, metadata, records, timestamp):
    signatures = metadata.get("signatures")
    assert signatures is not None and len(signatures) > 0, "Missing signature"

    data = canonicaljson.dumps(
        {
            "data": sorted(records, key=operator.itemgetter("id")),
            "last_modified": str(timestamp),
        }
    ).encode("utf-8")

    thrown_error = None
    for signature in signatures:
        x5u = signature["x5u"]
        sig = signature["signature"]
        try:
            await verifier.verify(data, sig, x5u)
            return True
        except (BadSignature, BadCertificate) as exc:
            thrown_error = exc
    raise thrown_error


async def run(
    server: str, buckets: List[str], root_hash: Optional[str] = None
) -> CheckResult:
    root_hash_bytes: Optional[bytes] = (
        decode_mozilla_hash(root_hash) if root_hash else None
    )
    client = KintoClient(server_url=server)
    entries = [
        entry
        for entry in await client.get_monitor_changes()
        if entry["bucket"] in buckets
    ]

    # Fetch collections records in parallel.
    futures = [
        client.get_changeset(
            entry["bucket"], entry["collection"], _expected=entry["last_modified"]
        )
        for entry in entries
    ]
    start_time = time.time()
    results = await run_parallel(*futures)
    elapsed_time = time.time() - start_time
    logger.info(f"Downloaded all data in {elapsed_time:.2f}s")

    cache = MemoryCache()

    async with ClientSession() as session:
        verifier = SignatureVerifier(session, cache, root_hash=root_hash_bytes)

        # Validate signatures sequentially.
        errors = {}
        for i, (entry, changeset) in enumerate(zip(entries, results)):
            cid = "{bucket}/{collection}".format(**entry)
            message = "{:02d}/{:02d} {}: ".format(i + 1, len(entries), cid)
            try:
                start_time = time.time()
                await validate_signature(
                    verifier,
                    changeset["metadata"],
                    changeset["changes"],
                    changeset["timestamp"],
                )
                elapsed_time = time.time() - start_time

                message += f"OK ({elapsed_time:.2f}s)"
                logger.info(message)

            except (BadSignature, BadCertificate) as e:
                message += "⚠ Signature Error ⚠ " + repr(e)
                logger.error(message)
                errors[cid] = repr(e)

    return len(errors) == 0, errors
