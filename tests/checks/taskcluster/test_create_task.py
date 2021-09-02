from unittest import mock

import pytest
import taskcluster.exceptions

from checks.taskcluster.create_task import run


MODULE = "checks.taskcluster.create_task"

PARAMS = {
    "root_url": "http://server",
}


async def test_positive():
    class FakeQueue:
        async def createTask(self, *args, **kwargs):
            self.called_with = args, kwargs
            return {"status": {"taskId": 42}}

    fake_queue = FakeQueue()

    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        status, data = await run(**PARAMS)

    assert status is True
    assert data == {"taskId": 42}
    _, definition = fake_queue.called_with[0]
    assert definition["payload"]["command"] == [
        ["/bin/bash", "-c", 'echo "hola mundo!"']
    ]


async def test_negative():
    class FakeQueue:
        async def createTask(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            raise e

    fake_queue = FakeQueue()

    with mock.patch(f"{MODULE}.taskcluster.aio.Queue", return_value=fake_queue):
        with pytest.raises(taskcluster.exceptions.TaskclusterRestFailure):
            await run(**PARAMS)
