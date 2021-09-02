from unittest import mock

import pytest
import taskcluster.exceptions

from checks.taskcluster.create_hook import run


MODULE = "checks.taskcluster.create_hook"

PARAMS = {
    "root_url": "http://server",
    "hook_id": "a-b-c",
}


async def test_positive_creates():
    class FakeHooks:
        async def hook(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            e.status_code = 404
            raise e

        async def createHook(self, *args, **kwargs):
            self.created_called_with = args, kwargs
            return {"hookId": 42}

    fake_hooks = FakeHooks()

    with mock.patch(f"{MODULE}.taskcluster.aio.Hooks", return_value=fake_hooks):
        status, data = await run(**PARAMS)

    assert status is True
    assert data == {"hookId": 42}
    group_id, hook_id, definition = fake_hooks.created_called_with[0]
    assert hook_id == "a-b-c"
    assert definition["task"]["command"] == [
        [
            "/bin/bash",
            "-vxec",
            'echo \'{"msg": "hola mundo"}\' > workspace/results/hello.json',
        ],
    ]


async def test_positive_exists():
    class FakeHooks:
        async def hook(self, *args, **kwargs):
            return {"hookId": "42"}

    fake_hooks = FakeHooks()

    with mock.patch(f"{MODULE}.taskcluster.aio.Hooks", return_value=fake_hooks):
        status, data = await run(**PARAMS)

    assert status is True
    assert data == {"hookId": "42"}


async def test_negative():
    class FakeHooks:
        async def hook(self, *args, **kwargs):
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            raise e

    fake_hooks = FakeHooks()

    with mock.patch(f"{MODULE}.taskcluster.aio.Hooks", return_value=fake_hooks):
        with pytest.raises(taskcluster.exceptions.TaskclusterRestFailure):
            await run(**PARAMS)
