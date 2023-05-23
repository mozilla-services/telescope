"""
URL should support the specified versions.
"""
import subprocess

from telescope.typings import CheckResult


EXPOSED_PARAMETERS = ["url", "versions"]

CURL_VERSION_FLAGS = ["--http1.0", "--http1.1", "--http2", "--http3"]


async def run(url: str, versions: list[str] = ["1", "1.1", "2", "3"]) -> CheckResult:
    supported_versions = set()
    for flag in CURL_VERSION_FLAGS:
        result = subprocess.run(
            ["curl", "-sI", flag, url, "-o/dev/null", "-w", "%{http_version}\n"],
            capture_output=True,
        )
        supported_versions.add(result.stdout.strip().decode())

    if missing_versions := set(versions).difference(supported_versions):
        return False, f"HTTP version(s) {', '.join(missing_versions)} unsupported"

    if extra_versions := supported_versions.difference(set(versions)):
        return (
            False,
            f"HTTP version(s) {', '.join(extra_versions)} unexpectedly supported",
        )

    return True, list(supported_versions)
