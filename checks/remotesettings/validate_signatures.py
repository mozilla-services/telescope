"""
Signatures should be valid for each collection content.

The errors are returned for each concerned collection.
"""
import logging
import operator
import time
from typing import List

import canonicaljson
from autograph_utils import MemoryCache, SignatureVerifier, decode_mozilla_hash

from poucave.typings import CheckResult
from poucave.utils import ClientSession, run_parallel

from .utils import KintoClient


logger = logging.getLogger(__name__)


async def validate_signature(verifier, metadata, records, timestamp):
    signature = metadata.get("signature")
    assert signature is not None, "Missing signature"
    x5u = signature["x5u"]
    signature = signature["signature"]

    data = canonicaljson.dumps(
        {
            "data": sorted(records, key=operator.itemgetter("id")),
            "last_modified": str(timestamp),
        }
    ).encode("utf-8")

    return await verifier.verify(data, signature, x5u)


async def run(server: str, buckets: List[str], root_hash: str) -> CheckResult:
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
        verifier = SignatureVerifier(session, cache, decode_mozilla_hash(root_hash))

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

            except Exception as e:
                message += "⚠ Signature Error ⚠ " + repr(e)
                logger.error(message)
                errors[cid] = repr(e)

    return len(errors) == 0, errors
