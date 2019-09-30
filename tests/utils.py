import asyncio
from contextlib import contextmanager
from unittest import mock


@contextmanager
def patch_async(*args, return_value=None, **kwargs):
    side_effect = kwargs.pop("side_effect", None)

    with mock.patch(*args, **kwargs) as m:
        f = asyncio.Future()

        if side_effect is not None:
            f.set_exception(side_effect)
        else:
            f.set_result(return_value)

        m.return_value = f
        yield m
