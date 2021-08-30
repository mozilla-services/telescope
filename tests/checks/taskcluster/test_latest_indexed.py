from datetime import timedelta
from unittest import mock

import pytest
import taskcluster.exceptions

from checks.taskcluster.latest_indexed import run
from poucave.utils import utcnow
from tests.utils import patch_async


MODULE = "checks.taskcluster.latest_indexed"

PARAMS = {
    "root_url": "http://server",
    "index_path": "project.myproject.task",
    "artifacts_names": ["public/status.json"],
    "max_age": 10,
}


@pytest.fixture
def fake_index():
    class FakeIndex:
        async def findTask(self, *args, **kwargs):
            return {"taskId": "task-42"}

    fake_index = FakeIndex()
    with mock.patch(f"{MODULE}.taskcluster.aio.Index", return_value=fake_index) as m:
        yield m


@pytest.fixture
def fake_queue():
    class FakeQueue:
        async def latestArtifactInfo(self, task_id, a):
            return {}

        async def status(self, task_id):
            task_status = {
                "runs": [{"resolved": (utcnow() - timedelta(seconds=5)).isoformat()}]
            }
            return {"status": task_status}

    fake_queue = FakeQueue()
    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue) as m:
        yield m


async def test_positive(fake_index, fake_queue):
    status, data = await run(**PARAMS)

    assert status is True
    assert "artifacts" in data
    assert "status" in data


async def test_index_errors_are_raised():
    class FakeIndex:
        async def findTask(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            raise e

    fake_index = FakeIndex()
    with mock.patch(f"{MODULE}.taskcluster.aio.Index", return_value=fake_index):
        with pytest.raises(taskcluster.exceptions.TaskclusterRestFailure):
            await run(**PARAMS)


async def test_negative_missing_task():
    class FakeIndex:
        async def findTask(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            e.status_code = 404
            raise e

    fake_index = FakeIndex()
    with mock.patch(f"{MODULE}.taskcluster.aio.Index", return_value=fake_index):
        status, data = await run(**PARAMS)

    assert status is False
    assert data == "No task found at 'project.myproject.task'"


async def test_negative_fail_artifact(fake_index):
    class FakeQueue:
        async def latestArtifactInfo(self, task_id, a):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            e.body = {"requestInfo": {"params": {"name": a, "taskId": task_id}}}
            raise e

    fake_queue = FakeQueue()
    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        status, data = await run(**PARAMS)

    assert status is False
    assert data == "Artifact 'public/status.json' of task 'task-42' not available"


async def test_negative_task_too_told(fake_index):
    class FakeQueue:
        async def latestArtifactInfo(self, task_id, a):
            return {}

        async def status(self, task_id):
            return {
                "status": {
                    "runs": [
                        {"resolved": (utcnow() - timedelta(seconds=11)).isoformat()}
                    ]
                }
            }

    fake_queue = FakeQueue()
    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        status, data = await run(**PARAMS)

    assert status is False
    assert (
        "Latest task at 'project.myproject.task' ('task-42') is 11 seconds old" in data
    )
