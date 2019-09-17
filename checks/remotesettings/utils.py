import copy
import os
from typing import Dict, List

import backoff
import kinto_http
import requests
from requests.adapters import TimeoutSauce  # type: ignore


REQUESTS_TIMEOUT_SECONDS = float(os.getenv("REQUESTS_TIMEOUT_SECONDS", 5))
REQUESTS_MAX_RETRIES = int(os.getenv("REQUESTS_MAX_RETRIES", 4))


retry_timeout = backoff.on_exception(
    backoff.expo,
    (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
    max_tries=REQUESTS_MAX_RETRIES,
)


class CustomTimeout(TimeoutSauce):
    def __init__(self, *args, **kwargs):
        if kwargs["connect"] is None:
            kwargs["connect"] = REQUESTS_TIMEOUT_SECONDS
        if kwargs["read"] is None:
            kwargs["read"] = REQUESTS_TIMEOUT_SECONDS
        super().__init__(*args, **kwargs)


requests.adapters.TimeoutSauce = CustomTimeout


class KintoClient:
    """
    This Kinto client will retry the requests if they fail for timeout, and
    if the server replies with a 5XX.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("retry", REQUESTS_MAX_RETRIES)

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
    def server_info(self, *args, **kwargs):
        return self._client.server_info(*args, **kwargs)

    @retry_timeout
    def get_collection(self, *args, **kwargs):
        return self._client.get_collection(*args, **kwargs)

    @retry_timeout
    def get_records(self, *args, **kwargs):
        return self._client.get_records(*args, **kwargs)

    @retry_timeout
    def get_record(self, *args, **kwargs):
        return self._client.get_record(*args, **kwargs)

    @retry_timeout
    def get_records_timestamp(self, *args, **kwargs):
        return self._client.get_records_timestamp(*args, **kwargs)

    @retry_timeout
    def get_history(self, *args, **kwargs):
        return self._client.get_history(*args, **kwargs)


def fetch_signed_resources(server_url: str, auth: str) -> List[Dict[str, Dict]]:
    # List signed collection using capabilities.
    client = KintoClient(server_url=server_url, auth=auth)
    info = client.server_info()
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
    monitored = client.get_records(
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
        resources.append(r)

    return resources
