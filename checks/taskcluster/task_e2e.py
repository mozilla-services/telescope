"""
A check to create a task and verify that its artifacts are accessible.

The check will fail if:
- the Queue or the Index is failing
- the log artifact is not reachable
- the log does not contain our message
- the task took more than `max_duration` seconds to be executed

Information about the current or latest task is returned, along with
any potential error.
"""
import logging
import textwrap
from datetime import datetime, timedelta
from typing import Any, Dict

import aiohttp
import taskcluster
import taskcluster.aio

from poucave import config, utils
from poucave.typings import CheckResult


logger = logging.getLogger(__name__)

# List which check parameters are visible in the UI.
EXPOSED_PARAMETERS = ["root_url", "project", "max_duration"]

LOG_ARTIFACT = "public/logs/live.log"
TASK_METADATA = {
    "owner": config.CONTACT_EMAIL,
    "source": "https://github.com/mozilla-services/poucave/",
    "description": textwrap.dedent(
        """
        This task is a test and is generated routinely by {config.SERVICE_NAME}
        in order to monitor the taskcluster Queue and Index services. It ensures
        that tasks are able to run, and they intentionally have a short expiry
        to reduce resource usage.
        """
    ),
}


async def run(
    root_url: str,
    client_id: str = "",
    access_token: str = "",
    certificate: str = "",
    project: str = "taskcluster",
    worker_type: str = "gw-ci-ubuntu-18-04",
    output_message: str = "Hello World!",
    max_duration: int = 120,  # fails if takes longer.
    task_lifetime: int = 600,  # recreate tasks every 10 min.
) -> CheckResult:
    """
    Check entrypoint, executed at an undeterminated frequency.

    Checks execution is stateless. And since they don't have access to the
    Poucave cache here, we rely on the TC Index manually in order to keep
    track of the currently executing task ID.

    * When no task is found in the index, create a task, index it, and exit
    * When a task is found and currently running, do nothing and exit
    * When a task is found and completed, make sure the `output_message` is found in its logs
    * When the task was completed `task_lifetime` ago, create a new one, index it and exit

    .. note::

        We cannot rely on tasks routes to index them, because they only get
        indexed once completed.
        We would have no way of knowing whether a task is already currently
        pending or running before creating a new one.

    For example, with the following `config-taskcluster.toml` config file:

    .. code-block:: toml

        [checks.queue.task-e2e]
        description = ""
        module = "checks.taskcluster.task_e2e"
        ttl = 60
        params.root_url = "${TASKCLUSTER_ROOT_URL}"
        params.client_id = "${TASKCLUSTER_CLIENT_ID}"
        params.access_token = "${TASKCLUSTER_ACCESS_TOKEN}"

    The check can be executed from the command-line with:

    ::

        $ export TASKCLUSTER_ROOT_URL=https://community-tc.services.mozilla.com
        $ export TASKCLUSTER_CLIENT_ID=project/taskcluster/temp-pete-and-matt
        $ export TASKCLUSTER_ACCESS_TOKEN=bR67xxxxxxxxxxxxxxxxxxxxxxxxx
        $ export CONFIG_FILE=config-taskcluster.toml
        $ make check project=queue check=task-e2e

    When running the web server (``make serve``), this check gets executed every time
    the associated HTTP endpoint ``http://.../checks/queue/task-e2e`` is reached.
    The result of the check execution is cached for 60 seconds (see TTL value).
    """
    provisioner_id = f"proj-{project}"
    queue_id = f"{provisioner_id}/{worker_type}"
    task_index_path = f"project.{project}.check.task_e2e"

    options = {
        "rootUrl": root_url,
        "credentials": (
            {"clientId": client_id, "accessToken": access_token}
            if client_id and access_token
            else {"certificate": certificate}
        ),
        "maxRetries": config.REQUESTS_MAX_RETRIES,
    }

    #
    # 1. Get the currently executing task or create a task using the index.
    index = taskcluster.aio.Index(options)
    queue = taskcluster.aio.Queue(options)
    try:
        indexed_task = await index.findTask(task_index_path)
        task_id = indexed_task["taskId"]
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        if getattr(e, "status_code") != 404:
            raise
        # No existing task, create one!
        # Note that this will occur only the first time this check runs on a specific server.
        # If the index fails consistently on this server, this will keep creating tasks.
        task_id = await create_and_index_task(
            index, queue, queue_id, task_index_path, output_message
        )

    #
    # 2. Inspect the task details.
    task_infos = await queue.task(task_id)
    created_at = utils.utcfromisoformat(task_infos["created"])
    age_task = utils.utcnow() - created_at

    #
    # 3. Check its status in the queue.
    status = await queue.status(task_id)
    state = status["status"]["state"]

    # Prepare the check response status and details.
    success = True
    details: Dict[str, Any] = {
        "task": {
            "id": task_id,
            "created": created_at.isoformat(),
            "age": age_task.seconds,
            "status": state,
        }
    }

    if state != "completed":
        # Task is pending or running.
        if age_task.seconds > max_duration:
            # The task has been alive for too long.
            success = False
            details["error"] = f"Execution timeout ({age_task.seconds}s)"

    else:
        last_run = status["status"]["runs"][-1]
        #
        # 4. Try to download artifacts.
        log_artifact = await queue.artifact(task_id, last_run["runId"], LOG_ARTIFACT)
        url = log_artifact["url"]
        details["task"]["log"] = log_artifact
        try:
            content = await utils.fetch_text(url)
            if output_message not in content:
                success = False
                details["error"] = f"Message '{output_message}' not found in {url}"
        except aiohttp.ClientError as e:
            success = False
            details["error"] = f"Failed to retrieve artifacts ({e})"

        #
        # 5. Report if it took too much time to be executed.
        resolved = utils.utcfromisoformat(last_run["resolved"])
        details["task"]["completed"] = resolved.isoformat()
        duration = (resolved - created_at).seconds
        details["task"]["duration"] = duration
        if duration > max_duration:
            success = False
            details["error"] = f"Execution took too long ({duration}s)"

        if age_task.seconds > task_lifetime:
            # The task was completed a while ago.
            # Let's create a new one, so that it has a chance to have
            # its artifacts inspected in a next check run.
            task_id = await create_and_index_task(
                index, queue, queue_id, task_index_path, output_message
            )
            logger.info(
                f"Last task was {age_task.seconds} secs old, created new task {task_id}"
            )

    return success, details


async def create_and_index_task(index, queue, queue_id, index_path, message):
    """Create a task in the specified queue, and index it immediately.

    The specified `message` will be ouput in the logs.

    .. note::

        We don't rely on routes to index it. See check docstring.

    """
    name = "end-to-end-test"
    gen = taskcluster.stableSlugId()
    task_id = gen(name)

    now = datetime.utcnow()
    in_3_hours = now + timedelta(hours=3)
    in_1_day = now + timedelta(days=1)

    payload = {
        "taskQueueId": queue_id,
        "created": now.isoformat(),
        "deadline": in_3_hours.isoformat(),
        "expires": in_1_day.isoformat(),
        "payload": {
            "command": [["/bin/bash", "-c", f'echo "{message}"']],
            "maxRunTime": 600,
        },
        "metadata": {
            **TASK_METADATA,
            "name": name,
        },
    }
    status = await queue.createTask(task_id, payload)
    task_id = status["status"]["taskId"]

    # Keep track of this task in the index manually, even if it is
    # not completed yet.
    # This is **currently** the only way we have to keep track of the
    # currently executing task id, from one check run to another.
    await index.insertTask(
        index_path,
        {
            "taskId": task_id,
            "data": {},
            "expires": in_1_day.isoformat(),
            "rank": int(utils.utcnow().timestamp()),
        },
    )
    return task_id
