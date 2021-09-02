"""
This check will create a hook with the specified period of execution, if it
does not exist.

Information about created or existing hook will be returned.
"""
import logging
import shlex
import textwrap

import taskcluster
import taskcluster.aio
import taskcluster.exceptions

from poucave import config
from poucave.typings import CheckResult

from . import utils as tc_utils


logger = logging.getLogger(__name__)

# List which check parameters are visible in the UI.
EXPOSED_PARAMETERS = ["root_url", "index_path", "max_age"]

TASK_METADATA = {
    "owner": config.CONTACT_EMAIL,
    "description": textwrap.dedent(
        f"""
        This task is a test and is generated routinely by {config.SERVICE_NAME}
        in order to monitor the Taskcluster Queue services. It ensures that tasks
        are able to be created, and they intentionally have a short expiry
        to reduce resource usage.
        """
    ),
}

COMMAND = """/bin/bash -vxec "echo '{\\"msg\\": \\"hola mundo\\"}' > workspace/results/hello.json" """


async def run(
    root_url: str,
    hook_id: str,
    project: str = "taskcluster",
    group_id: str = "",
    max_run_time: int = 600,
    schedule: str = "*/15 * * * *",
    client_id: str = "",
    access_token: str = "",
    certificate: str = "",
) -> CheckResult:
    # Build connection infos from parameters.
    options = tc_utils.options_from_params(
        root_url, client_id, access_token, certificate
    )

    hooks = taskcluster.aio.Hooks(options)

    group_id = group_id or f"project-{project}"
    try:
        existing = await hooks.hook(group_id, hook_id)
        return True, existing  # XXX: too much info?
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        if getattr(e, "status_code") != 404:
            raise

    # Hook does not exist. Create it!
    payload = {
        "metadata": {
            "name": hook_id,
            **TASK_METADATA,
        },
        "schedule": [schedule],
        "task": {
            "routes": [
                f"index.project.{project}.{config.SERVICE_NAME}.{hook_id}",
            ],
            "command": [shlex.split(cmd) for cmd in COMMAND.splitlines()],
            "artifacts": [
                {
                    "name": "public/results",
                    "path": "workspace/results",
                    "type": "directory",
                }
            ],
            "maxRunTime": max_run_time,
        },
    }
    created = await hooks.createHook(group_id, hook_id, payload)
    return True, created
