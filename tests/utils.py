import asyncio
import sys
from contextlib import contextmanager
from unittest import mock


if sys.version_info >= (3, 8, 1):
    # mock.patch automatically detects async stuff and returns an
    # AsyncMock as of 3.8.1
    patch_async = mock.patch
else:
    # Otherwise, work around it ourselves
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
