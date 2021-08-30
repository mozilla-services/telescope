"""
A check to verify that the Secrets service is operational.

Information about the lastest indexed task is returned.
"""
import logging
from datetime import timedelta

import taskcluster
import taskcluster.aio
import taskcluster.exceptions

from poucave import utils
from poucave.typings import CheckResult

from . import utils as tc_utils


logger = logging.getLogger(__name__)


DEFAULT_NAME = "project/taskcluster/secrets-test"
DEFAULT_EXPIRES_SECONDS = 600


async def run(
    root_url: str,
    secret_name: str = DEFAULT_NAME,
    expires_seconds: int = DEFAULT_EXPIRES_SECONDS,
    client_id: str = "",
    access_token: str = "",
    certificate: str = "",
) -> CheckResult:
    # Build connection infos from parameters.
    options = tc_utils.options_from_params(
        root_url, client_id, access_token, certificate
    )

    secrets = taskcluster.aio.Secrets(options)

    # 1. Write and read.
    payload = {
        "expires": (utils.utcnow() + timedelta(seconds=expires_seconds)).isoformat(),
        "secret": {"hello": "beautiful world"},
    }
    await secrets.set(secret_name, payload)
    try:
        await secrets.get(secret_name)
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        if getattr(e, "status_code") != 404:  # pragma: no-cover
            raise
        return False, f"Secret {secret_name!r} was not stored"

    # 2. Remove and check.
    await secrets.remove(secret_name)
    try:
        await secrets.get(secret_name)
        return False, f"Secret {secret_name!r} was not removed"
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        if getattr(e, "status_code") != 404:  # pragma: no-cover
            raise

    return True, {}
