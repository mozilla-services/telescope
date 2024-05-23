"""
Signatures should be valid for each published recipe.

The list of failing recipes is returned.
"""

import json
import logging
import random
from typing import Optional

from autograph_utils import MemoryCache, SignatureVerifier, decode_mozilla_hash

from telescope.typings import CheckResult
from telescope.utils import ClientSession, fetch_json


RECIPES_URL = (
    "{server}/buckets/main/collections/{collection}/changeset?_expected={expected}"
)


logger = logging.getLogger(__name__)


async def validate_signature(verifier, recipe):
    signature_payload = recipe["signature"]
    x5u = signature_payload["x5u"]
    signature = signature_payload["signature"]
    attributes = recipe["recipe"]
    data = json.dumps(attributes, sort_keys=True, separators=(",", ":")).encode("utf8")
    return await verifier.verify(data, signature, x5u)


async def run(
    server: str, collection: str, root_hash: Optional[str] = None
) -> CheckResult:
    """Fetch recipes from Remote Settings and verify that each attached signature
    is verified with the related recipe attributes.

    :param server: URL of Remote Settings server.
    :param collection: Collection id to obtain recipes from (eg. ``"normandy-recipes"``.
    :param root_hash: The expected hash for the first certificate in a chain.
    """
    root_hash_bytes: Optional[bytes] = (
        decode_mozilla_hash(root_hash) if root_hash else None
    )
    expected = random.randint(999999000000, 999999999999)
    resp = await fetch_json(
        RECIPES_URL.format(server=server, collection=collection, expected=expected)
    )
    recipes = resp["changes"]

    cache = MemoryCache()

    errors = {}

    async with ClientSession() as session:
        verifier = SignatureVerifier(session, cache, root_hash_bytes)

        for recipe in recipes:
            try:
                await validate_signature(verifier, recipe)
            except Exception as e:
                errors[recipe["id"]] = repr(e)

    return len(errors) == 0, errors
