"""
Signatures should be valid for each collection content.

The errors are returned for each concerned collection.
"""
import asyncio
import base64
import cryptography
import hashlib
import logging
import time
from datetime import datetime
from typing import List, Dict

import cryptography.x509
import ecdsa
import requests
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.x509.oid import NameOID
from kinto_signer.serializer import canonical_json
from poucave.typings import CheckResult

from .utils import KintoClient as Client


logger = logging.getLogger(__name__)


def unpem(pem):
    # Join lines and strip -----BEGIN/END PUBLIC KEY----- header/footer
    return b"".join(
        [l.strip() for l in pem.split(b"\n") if l and not l.startswith(b"-----")]
    )


async def download_collection_data(server_url, entry):
    client = Client(
        server_url=server_url, bucket=entry["bucket"], collection=entry["collection"]
    )
    # Collection metadata with cache busting
    metadata = await client.get_collection(_expected=entry["last_modified"])["data"]
    # Download records with cache busting
    records = await client.get_records(
        _sort="-last_modified", _expected=entry["last_modified"]
    )
    timestamp = await client.get_records_timestamp()
    return (metadata, records, timestamp)


def validate_signature(metadata, records, timestamp, checked_certificates):
    signature = metadata.get("signature")
    assert signature is not None, "Missing signature"

    # Serialize as canonical JSON
    serialized = canonical_json(records, timestamp)
    data = b"Content-Signature:\x00" + serialized.encode("utf-8")

    # Verify the signature with the public key
    pubkey = signature["public_key"].encode("utf-8")
    verifier = ecdsa.VerifyingKey.from_pem(pubkey)
    signature_bytes = base64.urlsafe_b64decode(signature["signature"])
    verified = verifier.verify(signature_bytes, data, hashfunc=hashlib.sha384)
    assert verified, "Signature verification failed"

    # Verify that the x5u certificate is valid (ie. that signature was well refreshed)
    x5u = signature["x5u"]
    if x5u not in checked_certificates:
        resp = requests.get(signature["x5u"])
        cert_pem = resp.text.encode("utf-8")
        cert = cryptography.x509.load_pem_x509_certificate(
            cert_pem, crypto_default_backend()
        )
        assert cert.not_valid_before < datetime.now(), "Certificate not yet valid"
        assert cert.not_valid_after > datetime.now(), "Certificate expired"
        subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        # eg. ``onecrl.content-signature.mozilla.org``, or
        # ``pinning-preload.content-signature.mozilla.org``
        assert subject.endswith(
            ".content-signature.mozilla.org"
        ), "Invalid subject name"
        checked_certificates[x5u] = cert

    # Check that public key matches the certificate one.
    cert = checked_certificates[x5u]
    cert_pubkey_pem = cert.public_key().public_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert (
        unpem(cert_pubkey_pem) == pubkey
    ), "Signature public key does not match certificate"


async def run(server: str, buckets: List[str]) -> CheckResult:
    client = Client(server_url=server, bucket="monitor", collection="changes")
    entries = [
        entry for entry in await client.get_records() if entry["bucket"] in buckets
    ]

    # Fetch collections records in parallel.
    futures = [download_collection_data(server, entry) for entry in entries]
    start_time = time.time()
    results = await asyncio.gather(*futures)
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
            validate_signature(metadata, records, timestamp, checked_certificates)
            elapsed_time = time.time() - start_time

            message += f"OK ({elapsed_time:.2f}s)"
            logger.info(message)

        except Exception as e:
            message += "⚠ Signature Error ⚠ " + str(e)
            logger.error(message)
            errors[cid] = str(e)

    return len(errors) == 0, errors
