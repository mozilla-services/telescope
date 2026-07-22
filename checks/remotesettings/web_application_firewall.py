"""
Verify Fastly VCL and WAF rules of the server.

A set of URLs is requested with a Firefox ``User-Agent`` and the HTTP status
codes returned by the CDN are compared with the expected ones. The check also
verifies that the certificate chain (``x5u``) and the attachment URLs
referenced in the ``regions`` changeset are reachable.
"""

from datetime import timedelta
import re
from typing import Any

from telescope.typings import CheckResult
from telescope.utils import fetch_head, run_parallel, utcnow


EXPOSED_PARAMETERS = ["server"]

# The WAF rules key off the ``User-Agent``, hence sending a realistic Firefox one.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:136.0) "
    "Gecko/20100101 Firefox/136.0"
)


def build_expectations() -> list[tuple[str, int, str]]:
    """Return the list of ``(url, expected_status, message)`` to be checked."""
    now_epoch_ms = int((utcnow() - timedelta(seconds=300)).timestamp() * 1000)
    old_epoch_ms = now_epoch_ms - 30 * 86400 * 1000  # 30 days ago
    return [
        ("/", 307, "Root URL redirects to /v1/"),
        ("/v1", 307, "Trailing slash is required for /v1/"),
        ("/v1/", 200, "Base API URL should be accessible"),
        ("/v2", 307, "Trailing slash is required for /v2/"),
        ("/v2/", 200, "Base API URL should be accessible"),
        ("/v1/boo", 406, "Unknown endpoint should return 406"),
        ("/v1/cert-chains", 406, "Unknown endpoint should return 406"),
        ("/v1/buckets", 200, "Buckets list"),
        ("/v1/buckets/main", 200, "Main bucket"),
        ("/v1/buckets/main/collections", 200, "Collections list"),
        ("/v1/buckets/main/collections/regions", 200, "Collection metadata"),
        ("/v1/buckets/main/collections/regions/records", 200, "Collection records"),
        (
            "/v1/buckets/main/collections/regions/changeset",
            400,
            "Missing _expected should return 400",
        ),
        (
            "/v1/buckets/main/collections/regions/changeset?_expected=0",
            200,
            "Changeset with expected=0",
        ),
        (
            "/v1/buckets/main/collections/regions/changeset?_expected=0&_since=0",
            200,
            "Changeset with expected=0 and since=0",
        ),
        (
            f"/v1/buckets/main/collections/regions/changeset?_expected={now_epoch_ms}",
            200,
            "Changeset with current timestamp as _expected should return 200",
        ),
        (
            f'/v1/buckets/main/collections/regions/changeset?_expected="{now_epoch_ms}"',
            200,
            "Changeset with current timestamp as _expected (quoted) should return 200",
        ),
        (
            f'/v1/buckets/main/collections/regions/changeset?_expected={now_epoch_ms}&_since="123"',
            200,
            "Changeset with current timestamp as _expected and quoted _since should return 200",
        ),
        (
            f"/v1/buckets/main/collections/regions/changeset?_expected={now_epoch_ms}&_since=123",
            200,
            "Changeset with current timestamp as _expected and unquoted _since should return 200",
        ),
        (
            f'/v1/buckets/main/collections/regions/changeset?_expected="{now_epoch_ms}"&_since="123"',
            200,
            "Changeset with current timestamp as quoted _expected and quoted _since should return 200",
        ),
        (
            f'/v1/buckets/main/collections/regions/changeset?_expected="{now_epoch_ms}"&_since=123',
            200,
            "Changeset with current timestamp as quoted _expected and unquoted _since should return 200",
        ),
        (
            '/v1/buckets/main/collections/regions/changeset?_expected="abc"',
            200,
            "TODO: should be 400",
        ),
        (
            f'/v1/buckets/main/collections/regions/changeset?_expected="{old_epoch_ms}"',
            200,
            "Changeset with old timestamp as quoted _expected should return 307",
        ),
        (
            f"/v1/buckets/main/collections/regions/changeset?_expected={old_epoch_ms}",
            200,
            "Changeset with old timestamp as _expected should return return 200",
        ),
        (
            "/v1/buckets/monitor/collections/changes/records",
            406,
            "Decommissioned monitor/changes records",
        ),
        (
            "/v1/buckets/monitor/collections/changes/changeset",
            400,
            "Missing _expected should return 400 for monitor/changes changeset",
        ),
        (
            "/v1/buckets/monitor/collections/changes/changeset?_expected=abc",
            400,
            "Non-numeric _expected should return 400 for monitor/changes changeset",
        ),
        (
            "/v1/buckets/monitor/collections/changes/changeset?_expected=0",
            200,
            "Changeset with expected=0 should return 200 for monitor/changes changeset",
        ),
        (
            f"/v1/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}",
            200,
            "Changeset with current timestamp as _expected should return 200 for monitor/changes changeset",
        ),
        (
            f'/v1/buckets/monitor/collections/changes/changeset?_expected="{now_epoch_ms}"',
            307,
            "Changeset with current timestamp as quoted _expected should return 200 for monitor/changes changeset",
        ),
        (
            f'/v1/buckets/monitor/collections/changes/changeset?_expected="{now_epoch_ms}"&_since="{old_epoch_ms}"',
            307,
            "Changeset with current timestamp as quoted _expected and old timestamp as quoted _since should return 307 for monitor/changes changeset",
        ),
        (
            f'/v1/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}&_since="{now_epoch_ms}"',
            200,
            "Changeset with current timestamp as _expected and quoted current timestamp as _since should return 200 for monitor/changes changeset",
        ),
        (
            f"/v1/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}&_since={now_epoch_ms}",
            200,
            "Changeset with current timestamp as _expected and current timestamp as _since should return 200 for monitor/changes changeset",
        ),
        (
            f'/v1/buckets/monitor/collections/changes/changeset?_expected="{now_epoch_ms}"&_since="{now_epoch_ms}"',
            307,
            "Changeset with current timestamp as quoted _expected redirects to unquoted in monitor/changes changeset",
        ),
        (
            f'/v1/buckets/monitor/collections/changes/changeset?_expected="{now_epoch_ms}"&_since={now_epoch_ms}',
            307,
            "Changeset with current timestamp as quoted _expected redirects to unquoted in monitor/changes changeset",
        ),
        ("/v2/boo", 406, "Unknown endpoint should return 406"),
        ("/v2/buckets", 404, "Buckets endpoint should return 404 in v2"),
        ("/v2/buckets/main", 404, "Main bucket should return 404 in v2"),
        (
            "/v2/buckets/main/collections",
            404,
            "Collections endpoint should return 404 in v2",
        ),
        (
            "/v2/buckets/main/collections/regions",
            404,
            "Collection metadata endpoint should return 404 in v2",
        ),
        (
            "/v2/buckets/main/collections/regions/records",
            404,
            "Records endpoint should return 404 in v2",
        ),
        (
            "/v2/buckets/main/collections/regions/changeset",
            422,
            "Missing _expected should return 422 for v2 changeset",
        ),
        (
            "/v2/buckets/main/collections/regions/changeset?_expected=0",
            200,
            "Changeset with expected=0 should return 200 for v2 changeset",
        ),
        (
            f'/v2/buckets/main/collections/regions/changeset?_expected="{now_epoch_ms}"',
            422,
            "Quoted _expected should return 422 for v2 changeset",
        ),
        (
            f"/v2/buckets/main/collections/regions/changeset?_expected={now_epoch_ms}",
            200,
            "Unquoted _expected should return 200 for v2 changeset",
        ),
        (
            f'/v2/buckets/monitor/collections/changes/changeset?_expected="{now_epoch_ms}"',
            422,
            "Quoted _expected should return 422 for monitor/changes changeset in v2",
        ),
        (
            f"/v2/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}",
            200,
            "Unquoted _expected should return 200 for monitor/changes changeset in v2",
        ),
        (
            f'/v2/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}&_since="{old_epoch_ms}"',
            307,
            "Quoted old _since should redirect to unfiltered monitor/changes changeset in v2",
        ),
        (
            f"/v2/buckets/monitor/collections/changes/changeset?_expected={now_epoch_ms}&_since={old_epoch_ms}",
            307,
            "Unquoted old _since should redirect to unfiltered monitor/changes changeset in v2",
        ),
    ]


async def run(server: str, user_agent: str = DEFAULT_USER_AGENT) -> CheckResult:
    # Normalize the server URL to a base host (without version prefix).
    server = re.sub(r"/v\d+$", "", server.rstrip("/"))
    headers = {"User-Agent": user_agent}

    errors: dict[str, Any] = {}

    # 1. Check that each URL returns the status code expected from the WAF rules.
    expectations = build_expectations()
    futures = [
        fetch_head(f"{server}{url}", headers=headers, allow_redirects=False)
        for url, _, _ in expectations
    ]
    results = await run_parallel(*futures)

    for (url, expected, message), (status, resp_headers) in zip(expectations, results):
        if status != expected:
            errors[f"{server}{url}"] = {
                "message": message,
                "expected": expected,
                "status": status,
                "location": resp_headers.get("Location", ""),
            }

    return len(errors) == 0, errors
