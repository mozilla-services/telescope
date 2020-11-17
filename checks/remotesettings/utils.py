import asyncio
import copy
import random
from typing import Dict, List, Optional, Tuple

import backoff
import kinto_http
import requests
from kinto_http.session import USER_AGENT as KINTO_USER_AGENT

from poucave import config


USER_AGENT = f"poucave {KINTO_USER_AGENT}"


retry_timeout = backoff.on_exception(
    backoff.expo,
    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
    max_tries=config.REQUESTS_MAX_RETRIES,
)


class KintoClient:
    """
    This Kinto client will retry the requests if they fail for timeout, and
    if the server replies with a 5XX.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("retry", config.REQUESTS_MAX_RETRIES)
        kwargs.setdefault("timeout", config.REQUESTS_TIMEOUT_SECONDS)
        kwargs.setdefault(
            "headers", {"User-Agent": USER_AGENT, **config.DEFAULT_REQUEST_HEADERS}
        )

        auth = kwargs.get("auth")
        if auth is not None:
            _type = None
            if " " in auth:
                # eg, "Bearer ghruhgrwyhg"
                _type, auth = auth.split(" ", 1)
            auth = (
                tuple(auth.split(":", 1))
                if ":" in auth
                else kinto_http.BearerTokenAuth(auth, type=_type)
            )
            kwargs["auth"] = auth

        self._client = kinto_http.Client(*args, **kwargs)

    @retry_timeout
    async def server_info(self, *args, **kwargs) -> Dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.server_info(*args, **kwargs)
        )

    @retry_timeout
    async def get_collection(self, *args, **kwargs) -> Dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_collection(*args, **kwargs)
        )

    @retry_timeout
    async def get_records(self, *args, **kwargs) -> List[Dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_records(*args, **kwargs)
        )

    @retry_timeout
    async def get_monitor_changes(self, bust_cache=False, **kwargs) -> List[Dict]:
        if bust_cache:
            if "_expected" in kwargs:
                raise ValueError("Pick one of `bust_cache` and `_expected` parameters")
            random_cache_bust = random.randint(999999000000, 999999999999)
            kwargs["_expected"] = random_cache_bust
        return await self.get_records(bucket="monitor", collection="changes", **kwargs)

    @retry_timeout
    async def get_record(self, *args, **kwargs) -> Dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_record(*args, **kwargs)
        )

    @retry_timeout
    async def get_records_timestamp(self, *args, **kwargs) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_records_timestamp(*args, **kwargs)
        )

    @retry_timeout
    async def get_history(self, *args, **kwargs) -> List[Dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_history(*args, **kwargs)
        )

    @retry_timeout
    async def get_group(self, *args, **kwargs) -> Dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._client.get_group(*args, **kwargs)
        )


async def fetch_signed_resources(server_url: str, auth: str) -> List[Dict[str, Dict]]:
    # List signed collection using capabilities.
    client = KintoClient(server_url=server_url, auth=auth)
    info = await client.server_info()
    try:
        resources = info["capabilities"]["signer"]["resources"]
    except KeyError:
        raise ValueError("No signer capabilities found. Run on *writer* server!")

    # Build the list of signed collections, source -> preview -> destination
    # For most cases, configuration of signed resources is specified by bucket and
    # does not contain any collection information.
    resources_by_bid = {}
    resources_by_cid = {}
    preview_buckets = set()
    for resource in resources:
        bid = resource["destination"]["bucket"]
        cid = resource["destination"]["collection"]
        if resource["source"]["collection"] is not None:
            resources_by_cid[(bid, cid)] = resource
        else:
            resources_by_bid[bid] = resource
        if "preview" in resource:
            preview_buckets.add(resource["preview"]["bucket"])

    resources = []
    monitored = await client.get_records(
        bucket="monitor", collection="changes", _sort="bucket,collection"
    )
    for entry in monitored:
        bid = entry["bucket"]
        cid = entry["collection"]

        # Skip preview collections entries
        if bid in preview_buckets:
            continue

        if (bid, cid) in resources_by_cid:
            r = resources_by_cid[(bid, cid)]
        elif bid in resources_by_bid:
            r = copy.deepcopy(resources_by_bid[bid])
            r["source"]["collection"] = r["destination"]["collection"] = cid
            if "preview" in r:
                r["preview"]["collection"] = cid
        else:
            raise ValueError(f"Unknown signed collection {bid}/{cid}")

        r["last_modified"] = entry["last_modified"]

        resources.append(r)

    return resources


def records_equal(a, b):
    """Compare records, ignoring timestamps."""
    ignored_fields = ("last_modified", "schema")
    ra = {k: v for k, v in a.items() if k not in ignored_fields}
    rb = {k: v for k, v in b.items() if k not in ignored_fields}
    return ra == rb


def compare_collections(
    a: List[Dict], b: List[Dict]
) -> Optional[Tuple[List[str], List[str], List[str]]]:
    """Compare two lists of records. Returns empty list if equal."""
    b_by_id = {r["id"]: r for r in b}
    missing = []
    differ = []
    for ra in a:
        rb = b_by_id.pop(ra["id"], None)
        if rb is None:
            missing.append(ra["id"])
        elif not records_equal(ra, rb):
            differ.append(ra["id"])
    extras = list(b_by_id.keys())

    if missing or differ or extras:
        return (missing, differ, extras)

    return None


def human_diff(
    left: str,
    right: str,
    missing: List[str],
    differ: List[str],
    extras: List[str],
    show_ids: int = 5,
) -> str:
    def ellipse(line):
        return ", ".join(repr(r) for r in line[:show_ids]) + (
            "..." if len(line) > show_ids else ""
        )

    details = []
    if missing:
        details.append(
            f"{len(missing)} record{'s' if len(missing) > 1 else ''} present in {left} but missing in {right} ({ellipse(missing)})"
        )
    if differ:
        details.append(
            f"{len(differ)} record{'s' if len(differ) > 1 else ''} differ between {left} and {right} ({ellipse(differ)})"
        )
    if extras:
        details.append(
            f"{len(extras)} record{'s' if len(extras) > 1 else ''} present in {right} but missing in {left} ({ellipse(extras)})"
        )
    return ", ".join(details)
