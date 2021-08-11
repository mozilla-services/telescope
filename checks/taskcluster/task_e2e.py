"""
A check to create a task and verify that its artifacts are accessible.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

import taskcluster
import taskcluster.aio

from poucave import utils
from poucave.typings import CheckResult


logger = logging.getLogger(__name__)


EXPOSED_PARAMETERS = ["root_url", "project", "max_duration"]


async def run(
    root_url: str,
    client_id: str,
    access_token: str,
    project: str = "taskcluster",
    worker_type: str = "gw-ci-ubuntu-18-04",
    output_message: str = "Hello World!",
    max_duration: int = 120,  # fails if takes longer.
    task_lifetime: int = 600,  # recreate tasks every 10 min.
) -> CheckResult:
    """
    Check entrypoint, executed at an undeterminated frequency.

    For example, with the following `config-taskcluster.toml` config file:

    .. code-block:: toml

        [checks.queue.task-e2e]
        description = ""
        module = "checks.taskcluster.task_e2e"
        ttl = 60
        params.root_url = "${TASKCLUSTER_ROOT_URL}"
        params.client_id = "${TASKCLUSTER_CLIENT_ID}"
        params.access_token = "${TASKCLUSTER_ACCESS_TOKEN}"

    It can be executed from the command-line with:
    ::

        $ export TASKCLUSTER_ROOT_URL=https://community-tc.services.mozilla.com
        $ export TASKCLUSTER_CLIENT_ID=project/taskcluster/temp-pete-and-matt
        $ export TASKCLUSTER_ACCESS_TOKEN=bR67xxxxxxxxxxxxxxxxxxxxxxxxx
        $ export CONFIG_FILE=config-taskcluster.toml
        $ make check project=queue check=task-e2e

    When running the web server (``make serve``), this check gets executed everytime
    the associated HTTP endpoint ``http://.../checks/queue/task-e2e`` is reached.
    The result of the check execution is cached for 60 seconds (see TTL value).
    """
    provisioner_id = f"proj-{project}"
    queue_id = f"{provisioner_id}/{worker_type}"
    task_index_path = f"project.{project}.check.task_e2e"

    options = {
        "rootUrl": root_url,
        "credentials": {"clientId": client_id, "accessToken": access_token},
    }

    auth = taskcluster.aio.Auth(options)

    scopes = await auth.currentScopes()
    given_scopes = set(scopes["scopes"])
    required_scopes = {
        "index:find-task:*",
        f"index:insert-task:project.{project}.*",
        "queue:status:*",
        f"queue:create-task:highest:{provisioner_id}/*",
        "queue:get-artifact:public/*",
        "queue:get-task:*",
    }
    missing = required_scopes - given_scopes
    if len(missing):
        logger.warn(f"Current user has missing scopes: {missing}")

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

    if state == "completed":
        last_run = status["status"]["runs"][-1]
        #
        # 4. Try to download artifacts.
        artifacts = await list_artifacts(queue, task_id, last_run["runId"])
        artifacts_urls = [a["url"] for a in artifacts]
        details["task"]["artifacts"] = artifacts_urls

        futures = [utils.fetch_text(u) for u in artifacts_urls]
        results = await utils.run_parallel(*futures)
        for (url, content) in zip(artifacts_urls, results):
            # Check that our message is in log output!
            if output_message not in content:
                success = False
                details["error"] = f"Message '{output_message}' not found in {url}"

        #
        # 5. Report if it took too much time to be executed.
        resolved = utils.utcfromisoformat(last_run["resolved"])
        details["task"]["completed"] = resolved.isoformat()
        duration = (resolved - created_at).seconds
        details["task"]["duration"] = duration
        if duration > max_duration:
            details["error"] = f"Execution took too long ({duration}s)"
            success = False

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

    else:
        if age_task.seconds > max_duration:
            # The task has been pending/running for too long.
            success = False
            details["error"] = f"Execution timeout ({age_task.seconds}s)"
        # Otherwise, it's currently running, check is successful.

    return success, details


async def create_and_index_task(index, queue, queue_id, index_path, message):
    """Create a task in the specified queue, and index it immediately.

    The specified `message` will be ouput in the logs.
    """
    name = "end-to-end-test"
    gen = taskcluster.stableSlugId()
    task_id = gen(name)

    now = datetime.utcnow()
    in_3_hours = now + timedelta(hours=3)
    in_1_year = now + timedelta(days=365)

    payload = {
        "taskQueueId": queue_id,
        "created": now.isoformat(),
        "deadline": in_3_hours.isoformat(),
        "expires": in_1_year.isoformat(),
        "payload": {
            "command": [["/bin/bash", "-c", f'echo "{message}"']],
            "maxRunTime": 600,
        },
        "metadata": {
            "name": name,
            "owner": "bwong-directs@mozilla.com",
            "source": "https://github.com/mozilla-services/poucave",
            "description": "A task for an end-to-end test ",
        },
    }
    status = await queue.createTask(task_id, payload)
    task_id = status["status"]["taskId"]

    # Keep track of this task in the index, to make sure we only
    # run one task at a time.
    await index.insertTask(
        index_path,
        {
            "taskId": task_id,
            "data": {},
            "expires": in_1_year.isoformat(),
            "rank": int(utils.utcnow().timestamp()),
        },
    )
    return task_id


async def list_artifacts(queue, task_id, run_id):
    """Helper to list all task artifacts."""
    page = await queue.listArtifacts(task_id, run_id)
    artifacts = page.get("artifacts", [])
    while page.get("continuationToken"):
        artifacts += page.get("artifacts", [])
        page = await queue.listArtifacts(
            task_id,
            run_id,
            query={"continuationToken": page.get("continuationToken")},
        )
    futures = [
        queue.artifact(task_id, run_id, artifact["name"]) for artifact in artifacts
    ]
    infos = await utils.run_parallel(*futures)
    return infos
