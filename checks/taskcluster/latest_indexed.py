"""
A check to verify that a task exists for the specified index path, that it ran recently,
and published the expected artifact.

This check can be used to verify that a certain hook (defined elsewhere) is
regularly triggered as expected.

Information about the lastest indexed task is returned.
"""
import logging
from typing import List

import taskcluster
import taskcluster.aio
import taskcluster.exceptions

from poucave import utils
from poucave.typings import CheckResult

from . import utils as tc_utils


logger = logging.getLogger(__name__)

# List which check parameters are visible in the UI.
EXPOSED_PARAMETERS = ["root_url", "index_path", "max_age"]


async def run(
    max_age: int,
    index_path: str,
    artifacts_names: List[str],
    root_url: str,
    client_id: str = "",
    access_token: str = "",
    certificate: str = "",
) -> CheckResult:
    """
    Example configuration:

    .. code-block:: toml

        [checks.queue.latest-indexed]
        description = ""
        module = "checks.taskcluster.latest_indexed"
        params.root_url = "${TASKCLUSTER_ROOT_URL}"
        params.client_id = "${TASKCLUSTER_CLIENT_ID}"
        params.access_token = "${TASKCLUSTER_ACCESS_TOKEN}"
        params.max_age = 360
        params.index_path = "project.taskcluster.telescope.periodic-task"
        params.artifacts_names = ["public/results/status.json"]

    """
    # Build connection infos from parameters.
    options = tc_utils.options_from_params(
        root_url, client_id, access_token, certificate
    )

    # 1. Get the task id from the index.
    index = taskcluster.aio.Index(options)
    try:
        indexed_task = await index.findTask(index_path)
        task_id = indexed_task["taskId"]
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        if getattr(e, "status_code") != 404:
            raise
        # No indexed task found. Failing.
        return False, f"No task found at {index_path!r}"

    # 2. Inspect the task using the queue.
    queue = taskcluster.aio.Queue(options)
    futures = [queue.latestArtifactInfo(task_id, a) for a in artifacts_names]
    try:
        artifacts = await utils.run_parallel(*futures)
    except taskcluster.exceptions.TaskclusterRestFailure as e:
        failed_call = e.body["requestInfo"]["params"]
        return False, "Artifact {name!r} of task {taskId!r} not available".format(
            **failed_call
        )

    # 3. Verify that latest run is not too old.
    status = await queue.status(task_id)
    last_run = status["status"]["runs"][-1]
    resolved_at = utils.utcfromisoformat(last_run["resolved"])
    age_task = utils.utcnow() - resolved_at
    if age_task.seconds > max_age:
        return (
            False,
            f"Latest task at {index_path!r} ({task_id!r}) is {age_task.seconds} seconds old",
        )

    # 4. Success! Return status info.
    return True, {
        **status,
        "artifacts": artifacts,
    }
