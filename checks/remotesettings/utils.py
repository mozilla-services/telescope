import copy
import re
from typing import Any, Dict, List

import backoff
import kinto_http
import requests
from kinto_http.session import USER_AGENT as KINTO_USER_AGENT

from telescope import config, utils


USER_AGENT = f"telescope {KINTO_USER_AGENT}"


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
        self._client = kinto_http.AsyncClient(*args, **kwargs)

    @retry_timeout
    async def server_info(self, *args, **kwargs) -> Dict:
        return await self._client.server_info(*args, **kwargs)

    @retry_timeout
    async def get_collection(self, *args, **kwargs) -> Dict:
        return await self._client.get_collection(*args, **kwargs)

    @retry_timeout
    async def get_collections(self, *args, **kwargs) -> Dict:
        return await self._client.get_collections(*args, **kwargs)

    @retry_timeout
    async def get_records(self, *args, **kwargs) -> List[Dict]:
        return await self._client.get_records(*args, **kwargs)

    @retry_timeout
    async def get_monitor_changes(self, **kwargs) -> List[Dict]:
        resp = await self.get_changeset(
            bucket="monitor", collection="changes", **kwargs
        )
        return resp["changes"]

    @retry_timeout
    async def get_changeset(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._client.get_changeset(*args, **kwargs)

    @retry_timeout
    async def get_record(self, *args, **kwargs) -> Dict:
        return await self._client.get_record(*args, **kwargs)

    @retry_timeout
    async def get_records_timestamp(self, *args, **kwargs) -> str:
        return await self._client.get_records_timestamp(*args, **kwargs)

    @retry_timeout
    async def get_history(self, *args, **kwargs) -> List[Dict]:
        return await self._client.get_history(*args, **kwargs)

    @retry_timeout
    async def get_group(self, *args, **kwargs) -> Dict:
        return await self._client.get_group(*args, **kwargs)


class MissingSignerCapabilityError(ValueError):
    """
    Raised when the server does not have the signer capability.
    """

    def __init__(self):
        super().__init__("No signer capabilities found. Run on *writer* server!")


class UnknownSignedCollectionError(ValueError):
    """
    Raised when the server does not have the specified signed collection.
    """

    def __init__(self, bucket: str, collection: str):
        super().__init__(f"Unknown signed collection {bucket}/{collection}")
        self.bucket = bucket
        self.collection = collection


class MissingFromMonitorChangesError(ValueError):
    """
    Raised when the server does not have the specified collection in monitor/changes.
    """

    def __init__(self, bucket: str, collection: str):
        super().__init__(f"{bucket}/{collection} missing from monitor/changes")
        self.bucket = bucket
        self.collection = collection


async def fetch_signed_resources(server_url: str, auth: str) -> List[Dict[str, Dict]]:
    # List signed collection using capabilities.
    client = KintoClient(server_url=server_url, auth=auth)
    info = await client.server_info()
    try:
        resources = info["capabilities"]["signer"]["resources"]
    except KeyError:
        raise MissingSignerCapabilityError()

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

    # Fetch the list of collections in each resource's source bucket,
    # and build a list of all source collections.
    all_source_collections = set()
    futures = []
    for resource in resources_by_bid.values():
        bid = resource["source"]["bucket"]
        futures.append(client.get_collections(bucket=bid))
    results = await utils.run_parallel(*futures)
    for resource, collections in zip(resources_by_bid.values(), results):
        bid = resource["source"]["bucket"]
        for c in collections:
            all_source_collections.add((bid, c["id"]))
    # Include collections that were explicitily specified in config.
    for resource in resources_by_cid.values():
        bid = resource["source"]["bucket"]
        cid = resource["source"]["collection"]
        all_source_collections.add((bid, cid))

    resources = []
    monitored = await client.get_monitor_changes(_sort="bucket,collection")
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
            raise UnknownSignedCollectionError(bid, cid)

        all_source_collections.discard(
            (r["source"]["bucket"], r["source"]["collection"])
        )

        r["last_modified"] = entry["last_modified"]

        resources.append(r)

    # Check that all source collections were found in the monitored changes.
    for bid, cid in all_source_collections:
        raise MissingFromMonitorChangesError(bid, cid)

    return resources


def human_diff(
    left: str,
    right: str,
    missing: List[dict],
    differ: List[tuple[dict, dict]],
    extras: List[dict],
    show_ids: int = 5,
) -> str:
    missing_ids = [r["id"] for r in missing]
    differ_ids = [r["id"] for _, r in differ]
    extras_ids = [r["id"] for r in extras]

    def ellipse(line):
        return ", ".join(repr(r) for r in line[:show_ids]) + (
            "..." if len(line) > show_ids else ""
        )

    details = []
    if missing_ids:
        details.append(
            f"{len(missing_ids)} record{'s' if len(missing_ids) > 1 else ''} present in {left} but missing in {right} ({ellipse(missing_ids)})"
        )
    if differ_ids:
        details.append(
            f"{len(differ_ids)} record{'s' if len(differ_ids) > 1 else ''} differ between {left} and {right} ({ellipse(differ_ids)})"
        )
    if extras_ids:
        details.append(
            f"{len(extras_ids)} record{'s' if len(extras_ids) > 1 else ''} present in {right} but missing in {left} ({ellipse(extras_ids)})"
        )
    return ", ".join(details)


async def current_firefox_esr():
    resp = await utils.fetch_json(
        "https://product-details.mozilla.org/1.0/firefox_versions.json"
    )
    version = resp["FIREFOX_ESR"]
    # "91.0.1esr" -> (91, 0, 1)
    return tuple(int(re.sub(r"[^\d]+", "", n)) for n in version.split("."))
