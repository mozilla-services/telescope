import asyncio
from unittest import mock
from contextlib import contextmanager


@contextmanager
def patch_async(*args, return_value=None, **kwargs):
    with mock.patch(*args, **kwargs) as m:
        f = asyncio.Future()
        f.set_result(return_value)
        m.return_value = f

        yield m
