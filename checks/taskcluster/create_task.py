"""
A check to verify that tasks can be created.

Information about the lastest created task is returned.
"""

import logging
import shlex
import textwrap
from datetime import datetime, timedelta

import taskcluster
import taskcluster.aio
import taskcluster.exceptions

from telescope import config
from telescope.typings import CheckResult

from . import utils as tc_utils


logger = logging.getLogger(__name__)


TASK_METADATA = {
    "owner": config.CONTACT_EMAIL,
    "source": config.SOURCE_URL,
    "description": textwrap.dedent(
        """
        This task is a test and is generated routinely by {config.SERVICE_NAME}
        in order to monitor the Taskcluster Queue services. It ensures that tasks
        are able to be created, and they intentionally have a short expiry
        to reduce resource usage.
        """
    ),
}


async def run(
    root_url: str,
    queue_id: str = "proj-taskcluster/gw-ci-ubuntu-18-04",
    command: str = "/bin/echo 'hola mundo!'",
    task_source_url: str = "",
    deadline_seconds: int = 3 * 60 * 60,
    expires_seconds: int = 24 * 60 * 60,
    max_run_time: int = 10 * 60,
    client_id: str = "",
    access_token: str = "",
    certificate: str = "",
) -> CheckResult:
    # Build connection infos from parameters.
    options = tc_utils.options_from_params(
        root_url, client_id, access_token, certificate
    )
    queue = taskcluster.aio.Queue(options)

    name = "task-test"
    task_id = taskcluster.stableSlugId()(name)  # type: ignore

    now = datetime.utcnow()
    deadline = now + timedelta(seconds=deadline_seconds)
    expires = now + timedelta(seconds=expires_seconds)

    payload = {
        "taskQueueId": queue_id,
        "created": now.isoformat(),
        "deadline": deadline.isoformat(),
        "expires": expires.isoformat(),
        "payload": {
            "command": [shlex.split(cmd) for cmd in command.splitlines()],
            "maxRunTime": max_run_time,
        },
        "metadata": {
            **TASK_METADATA,
            "name": name,
            "source": task_source_url or config.SOURCE_URL,
        },
    }

    status = await queue.createTask(task_id, payload)

    return True, status["status"]
