"""
When changes are approved, the collection metadata change. When the
CDN TTL has elapsed, the content of origin should match the cached content.

The list of failing collections is returned, with the collection metadata
timestamps of the origin and the CDN.
"""

from telescope.typings import CheckResult

from .server_compare import run as server_compare_run


EXPOSED_PARAMETERS = ["origin_server", "cdn_server", "ttl_seconds"]


async def run(
    origin_server: str, cdn_server: str, ttl_seconds: int = 3600
) -> CheckResult:
    return await server_compare_run(
        source_server=origin_server,
        target_server=cdn_server,
        margin_seconds=ttl_seconds,
    )
