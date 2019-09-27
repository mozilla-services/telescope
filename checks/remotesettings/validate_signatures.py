"""
Signatures should be valid for each collection content.

The errors are returned for each concerned collection.
"""
import base64
import cryptography
import datetime
import hashlib
import logging
import time
from typing import List, Dict

import cryptography.x509
import ecdsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.x509.oid import NameOID
from kinto_signer.serializer import canonical_json
from poucave.typings import CheckResult
from poucave.utils import fetch_text, run_parallel, utcnow

from .utils import KintoClient


logger = logging.getLogger(__name__)


def unpem(pem):
    # Join lines and strip -----BEGIN/END PUBLIC KEY----- header/footer
    return b"".join(
        [l.strip() for l in pem.split(b"\n") if l and not l.startswith(b"-----")]
    )


async def download_collection_data(server_url, entry):
    client = KintoClient(
        server_url=server_url, bucket=entry["bucket"], collection=entry["collection"]
    )
    # Collection metadata with cache busting
    collection = await client.get_collection(_expected=entry["last_modified"])
    metadata = collection["data"]
    # Download records with cache busting
    records = await client.get_records(
        _sort="-last_modified", _expected=entry["last_modified"]
    )
    timestamp = await client.get_records_timestamp()
    return (metadata, records, timestamp)


async def fetch_cert(x5u):
    cert_pem = await fetch_text(x5u)
    cert = cryptography.x509.load_pem_x509_certificate(
        cert_pem.encode("utf-8"), crypto_default_backend()
    )
    return cert


async def validate_signature(metadata, records, timestamp, checked_certificates):
    signature = metadata.get("signature")
    assert signature is not None, "Missing signature"

    # Serialize as canonical JSON
    serialized = canonical_json(records, timestamp)
    data = b"Content-Signature:\x00" + serialized.encode("utf-8")

    # Verify that the x5u certificate is valid (ie. that signature was well refreshed)
    x5u = signature["x5u"]
    if x5u not in checked_certificates:
        cert = await fetch_cert(x5u)
        assert (
            cert.not_valid_before.replace(tzinfo=datetime.timezone.utc) < utcnow()
        ), "Certificate not yet valid"
        assert (
            cert.not_valid_after.replace(tzinfo=datetime.timezone.utc) > utcnow()
        ), "Certificate expired"
        subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        # eg. ``onecrl.content-signature.mozilla.org``, or
        # ``pinning-preload.content-signature.mozilla.org``
        assert subject.endswith(
            ".content-signature.mozilla.org"
        ), "Invalid subject name"
        checked_certificates[x5u] = cert

    # Verify the signature with the public key
    cert = checked_certificates[x5u]
    cert_pubkey_pem = cert.public_key().public_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pubkey = unpem(cert_pubkey_pem)
    verifier = ecdsa.VerifyingKey.from_pem(pubkey)
    signature_bytes = base64.urlsafe_b64decode(signature["signature"])
    verifier.verify(signature_bytes, data, hashfunc=hashlib.sha384)


async def run(server: str, buckets: List[str]) -> CheckResult:
    client = KintoClient(server_url=server, bucket="monitor", collection="changes")
    entries = [
        entry for entry in await client.get_records() if entry["bucket"] in buckets
    ]

    # Fetch collections records in parallel.
    futures = [download_collection_data(server, entry) for entry in entries]
    start_time = time.time()
    results = await run_parallel(*futures)
    elapsed_time = time.time() - start_time
    logger.info(f"Downloaded all data in {elapsed_time:.2f}s")

    # Validate signatures sequentially.
    errors = {}
    checked_certificates: Dict[str, object] = {}
    for i, (entry, (metadata, records, timestamp)) in enumerate(zip(entries, results)):
        cid = "{bucket}/{collection}".format(**entry)
        message = "{:02d}/{:02d} {}: ".format(i + 1, len(entries), cid)
        try:
            start_time = time.time()
            await validate_signature(metadata, records, timestamp, checked_certificates)
            elapsed_time = time.time() - start_time

            message += f"OK ({elapsed_time:.2f}s)"
            logger.info(message)

        except Exception as e:
            message += "⚠ Signature Error ⚠ " + str(e)
            logger.error(message)
            errors[cid] = str(e)

    return len(errors) == 0, errors
