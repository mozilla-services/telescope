from typing import Any, Dict
from unittest import mock

import pytest
import taskcluster.exceptions

from checks.taskcluster.write_secrets import run


MODULE = "checks.taskcluster.write_secrets"

PARAMS = {
    "root_url": "http://server",
}


class FakeSecrets:
    _content: Dict[str, Any] = {}

    async def set(self, name, payload):
        self._content[name] = payload

    async def get(self, name):
        try:
            return self._content[name]
        except KeyError:
            e = taskcluster.exceptions.TaskclusterRestFailure("", None)
            e.status_code = 404
            raise e

    async def remove(self, name):
        del self._content[name]


async def test_positive():
    fake_secrets = FakeSecrets()
    with mock.patch(f"{MODULE}.taskcluster.aio.Secrets", return_value=fake_secrets):
        status, data = await run(**PARAMS)

    assert status is True
    assert data == {}


async def test_negative_cannot_write():
    class FailingSecrets(FakeSecrets):
        async def set(self, name, payload):
            pass  # Do not store.

    fake_secrets = FailingSecrets()
    with mock.patch(f"{MODULE}.taskcluster.aio.Secrets", return_value=fake_secrets):
        status, data = await run(**PARAMS)

    assert status is False
    assert data == "Secret 'project/taskcluster/secrets-test' was not stored"


async def test_negative_cannot_remove():
    class FailingSecrets(FakeSecrets):
        async def remove(self, name):
            pass  # Do not remove.

    fake_secrets = FailingSecrets()
    with mock.patch(f"{MODULE}.taskcluster.aio.Secrets", return_value=fake_secrets):
        status, data = await run(**PARAMS)

    assert status is False
    assert data == "Secret 'project/taskcluster/secrets-test' was not removed"


async def test_secrets_errors_are_raised():
    class FailingSecrets(FakeSecrets):
        async def get(self, name):
            raise ValueError("boom")

    fake_secrets = FailingSecrets()
    with mock.patch(f"{MODULE}.taskcluster.aio.Secrets", return_value=fake_secrets):
        with pytest.raises(ValueError):
            await run(**PARAMS)
