from datetime import timedelta
from unittest import mock

import pytest
import taskcluster.exceptions

from checks.taskcluster.create_task import run
from poucave.utils import utcnow


MODULE = "checks.taskcluster.create_task"

PARAMS = {
    "root_url": "http://server",
}


async def test_positive():
    class FakeQueue:
        async def createTask(self, *args, **kwargs):
            return {"status": {"taskId": 42}}

    fake_queue = FakeQueue()

    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        status, data = await run(**PARAMS)

    assert status is True
    assert data == {"taskId": 42}


async def test_negative():
    class FakeQueue:
        async def createTask(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            raise e

    fake_queue = FakeQueue()

    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        with pytest.raises(taskcluster.exceptions.TaskclusterRestFailure):
            await run(**PARAMS)
