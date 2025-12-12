import asyncio
import time
from collections import namedtuple
from unittest import mock

import aiohttp
import pytest

from telescope.utils import (
    BugTracker,
    ClientSession,
    History,
    InMemoryCache,
    RedisCache,
    extract_json,
    fetch_bigquery,
    run_in_process_pool,
    run_parallel,
    sha256hex,
)


@pytest.mark.asyncio
async def test_cache_set_get():
    cache = InMemoryCache()
    await cache.set("a", 42, ttl=1)

    assert await cache.get("a") == 42
    assert await cache.get("b") is None


@pytest.fixture
def mock_redis():
    with mock.patch("telescope.utils.Redis.from_url") as mocked:

        class MockedClient:
            def __init__(self):
                self.store = {}
                self.locks = {}

            async def get(self, key):
                return self.store.get(key)

            async def set(self, key, value, ex=None):
                self.store[key] = value

            def lock(self, name, timeout=None, blocking_timeout=None):
                return self.locks.setdefault(name, asyncio.Lock())

        mocked.return_value = MockedClient()
        yield mocked.return_value


@pytest.mark.asyncio
async def test_redis_cache(mock_redis):
    cache = RedisCache(url="redis://localhost:6379/0", key_prefix="test:")
    result = await cache.get("key")
    assert result is None
    await cache.set("key", "value", ttl=10)
    result = await cache.get("key")
    assert result == "value"


@pytest.mark.asyncio
async def test_redis_cache_lock(mock_redis):
    cache = RedisCache(url="redis://localhost:6379/0", key_prefix="test:")
    async with cache.lock("my-lock"):
        # Simulate some work while holding the lock
        await asyncio.sleep(0.01)


async def test_clientsession_checks_open():
    async with ClientSession() as session:
        await session.close()

    with pytest.raises(RuntimeError):
        async with ClientSession() as session:
            pass


async def test_fetch_bigquery(mock_aioresponses):
    with mock.patch("telescope.utils.bigquery.Client") as mocked:
        mocked.return_value.project = "wip"
        mocked.return_value.query.return_value.result.return_value = [
            ("row1"),
            ("row2"),
        ]
        result = await fetch_bigquery("SELECT * FROM {__project__};")
    mocked.return_value.query.assert_called_with("SELECT * FROM wip;")
    assert result == [("row1"), ("row2")]


async def test_fetch_bigquery_with_specific_project(mock_aioresponses, config):
    config.HISTORY_PROJECT_ID = "acme-project-id"

    with mock.patch("telescope.utils.bigquery.Client") as mocked:
        await fetch_bigquery("SELECT * FROM {__project__};")

        mocked.assert_called_with(project="acme-project-id")


async def test_fetch_bigquery_without_specific_project(mock_aioresponses):
    with mock.patch("telescope.utils.bigquery.Client") as mocked:
        await fetch_bigquery("SELECT * FROM {__project__};")

        mocked.assert_called_with(project=None)


async def test_run_parallel():
    async def success():
        return 42

    async def failure():
        raise ValueError("boom")

    with pytest.raises(ValueError) as exc_info:
        await run_parallel(success(), failure(), success())
    assert str(exc_info.value) == "boom"


async def test_run_parallel_empty():
    results = await run_parallel()
    assert results == []


async def test_run_parallel_single():
    results = await run_parallel(asyncio.sleep(0.01, result=7))
    assert results == [7]


async def test_run_parallel_actually_parallelizes():
    async def sleep(n):
        await asyncio.sleep(0.01)
        return n**2

    before = time.time()
    results = await run_parallel(*(sleep(i) for i in range(5)))
    after = time.time()
    assert after - before < 0.05  # Should be less than the sum of sleeps
    assert results == [0, 1, 4, 9, 16]


async def test_run_in_process_pool():
    results = await asyncio.gather(
        run_in_process_pool(sha256hex, b"Hello, world!"),
        run_in_process_pool(sha256hex, b"Hola, mundo!"),
    )
    assert results[0].startswith("315f5")
    assert results[1].startswith("364e7")


def test_extract_json():
    data = {
        "min_timestamp": "2020-09-24T10:29:44.925",
        "max_timestamp": "2020-09-24T16:25:14.164",
        "percentiles": {
            "1": {"value": 29, "max": 60},
            "25": {"value": 180, "max": 300},
        },
        "pings": [314, 42],
    }
    assert extract_json(".", 12) == 12
    assert extract_json(".percentiles.1.value", data) == 29
    assert extract_json(".pings.0", data) == 314
    assert extract_json(".min_timestamp", data) == "2020-09-24T10:29:44.925"

    with pytest.raises(ValueError) as exc_info:
        extract_json(".pings.a", data)
    assert str(exc_info.value) == "list indices must be integers or slices, not str"

    with pytest.raises(ValueError) as exc_info:
        extract_json(".field", "An error returned by check")
    assert "string indices must be integers" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        extract_json(".percentiles.75.value", {"percentiles": "No results"})
    assert "string indices must be integers" in str(exc_info.value)


def test_sha256hex():
    assert sha256hex(b"Hello, world!").startswith("315f5")


async def test_bugzilla_ping_fallsback_to_false(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    with mock.patch(
        "telescope.utils.fetch_json",
    ) as mocked:
        mocked.side_effect = aiohttp.ClientError("Timeout")
        result = await tracker.ping()
    assert not result


async def test_bugzilla_ping_returns_true_on_success(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/whoami", payload={"name": "foo"}
    )
    result = await tracker.ping()
    assert result


async def test_bugzilla_fetch_fallsback_to_empty_list(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    with mock.patch(
        "telescope.utils.fetch_json",
    ) as mocked:
        mocked.side_effect = aiohttp.ClientError("Timeout")
        results = await tracker.fetch(project="telemetry", name="pipeline")
    assert results == []


async def test_bugzilla_fetch_fallsback_to_empty_list_with_missing_property(
    mock_aioresponses, config
):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=telescope ", payload={}
    )
    results = await tracker.fetch(project="telemetry", name="pipeline")
    assert results == []


async def test_bugzilla_fetch_fallsback_to_empty_list_with_bad_response(
    mock_aioresponses, config
):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=telescope ", payload="foo"
    )
    results = await tracker.fetch(project="telemetry", name="pipeline")
    assert results == []


async def test_bugzilla_fetch_without_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=telescope ",
        payload={
            "bugs": [
                {
                    "id": 20200701,
                    "summary": "Recent closed bug",
                    "last_change_time": "2020-07-01T00:00:00Z",
                    "product": "Firefox",
                    "is_open": False,
                    "status": "WONTFIX",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                },
                {
                    "id": 20200604,
                    "summary": "Open bug",
                    "last_change_time": "2020-06-04T22:54:59Z",
                    "product": "Firefox",
                    "is_open": True,
                    "status": "NEW",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                },
                {
                    "id": 20200801,
                    "summary": "Hidden security bug info",
                    "last_change_time": "2020-08-01T00:00:00Z",
                    "product": "Firefox",
                    "is_open": True,
                    "status": "REOPENED",
                    "groups": ["firefox-security"],
                    "whiteboard": "telemetry/pipeline",
                },
                {
                    "id": 20200101,
                    "summary": "Old open bug",
                    "last_change_time": "2020-01-01T00:00:00Z",
                    "product": "Firefox",
                    "is_open": True,
                    "status": "UNKNOWN",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                },
                {
                    "id": 20191201,
                    "summary": "Other check",
                    "last_change_time": "2019-12-01T12:14:29Z",
                    "product": "Firefox",
                    "is_open": False,
                    "status": "RESOLVED",
                    "groups": [],
                    "whiteboard": "other/check",
                },
            ]
        },
    )

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert results == [
        {
            "id": 20200801,
            "summary": "",  # hidden
            "last_update": "2020-08-01T00:00:00Z",
            "open": True,
            "heat": "cold",
            "status": "REOPENED",
            "url": "https://bugzilla.mozilla.org/20200801",
        },
        {
            "id": 20200604,
            "summary": "Open bug",
            "last_update": "2020-06-04T22:54:59Z",
            "open": True,
            "heat": "cold",
            "status": "NEW",
            "url": "https://bugzilla.mozilla.org/20200604",
        },
        {
            "id": 20200101,
            "summary": "Old open bug",
            "last_update": "2020-01-01T00:00:00Z",
            "open": True,
            "heat": "cold",
            "status": "UNKNOWN",
            "url": "https://bugzilla.mozilla.org/20200101",
        },
        {
            "id": 20200701,
            "summary": "Recent closed bug",
            "last_update": "2020-07-01T00:00:00Z",
            "open": False,
            "heat": "cold",
            "status": "WONTFIX",
            "url": "https://bugzilla.mozilla.org/20200701",
        },
    ]


async def test_bugzilla_return_results_from_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    cache = InMemoryCache()
    tracker = BugTracker(cache=cache)
    await cache.set(
        "bugtracker-list",
        {
            "bugs": [
                {
                    "id": 111,
                    "summary": "bug",
                    "last_change_time": "2020-06-04T22:54:59Z",
                    "product": "Firefox",
                    "is_open": True,
                    "status": "RESOLVED",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                }
            ]
        },
        ttl=1000,
    )

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert len(results) == 1
    assert results[0]["id"] == 111


async def test_bugzilla_fetch_with_expired_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=telescope ",
        payload={
            "bugs": [
                {
                    "id": 20200101,
                    "summary": "Old open bug",
                    "last_change_time": "2020-01-01T00:00:00Z",
                    "product": "Firefox",
                    "is_open": True,
                    "status": "UNKNOWN",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                }
            ]
        },
    )
    cache = InMemoryCache()
    tracker = BugTracker(cache=cache)
    await cache.set("bugtracker-list", {"bugs": [{}, {}, {}]}, ttl=0)

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert len(results) == 1


async def test_bugzilla_fetch_with_empty_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=telescope ",
        payload={
            "bugs": [
                {
                    "id": 20200101,
                    "summary": "Old open bug",
                    "last_change_time": "2020-01-01T00:00:00Z",
                    "product": "Firefox",
                    "is_open": True,
                    "heat": "cold",
                    "status": "UNKNOWN",
                    "groups": [],
                    "whiteboard": "telemetry/pipeline",
                }
            ]
        },
    )
    cache = InMemoryCache()
    tracker = BugTracker(cache=cache)

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert len(results) == 1


async def test_history_fetch_fallsback_to_empty_list(config):
    config.HISTORY_DAYS = 1
    history = History()
    with mock.patch(
        "telescope.utils.bigquery.Client",
    ) as mocked:
        mocked.side_effect = Exception("Timeout")
        results = await history.fetch(project="telemetry", name="pipeline")
    assert results == []


Row = namedtuple("Row", ["check", "t", "success", "scalar"])


async def test_history_fetch_without_cache(config):
    config.HISTORY_DAYS = 1

    history = History()
    with mock.patch(
        "telescope.utils.fetch_bigquery",
        return_value=[
            Row("crlite/filter-age", "2020-10-16 08:51:50", True, 32.0),
            Row("crlite/filter-age", "2020-10-18 08:51:50", True, 42.0),
            Row("telemetry/pipeline", "2020-10-15 08:51:50", False, 12.0),
        ],
    ):
        results = await history.fetch(project="crlite", name="filter-age")

    assert results == [
        {
            "scalar": 32.0,
            "success": True,
            "t": "2020-10-16 08:51:50",
        },
        {
            "scalar": 42.0,
            "success": True,
            "t": "2020-10-18 08:51:50",
        },
    ]


async def test_history_return_results_from_cache(config):
    config.HISTORY_DAYS = 1

    cache = InMemoryCache()
    history = History(cache=cache)
    await cache.set(
        "scalar-history",
        {
            "crlite/filter-age": [
                {
                    "scalar": 42.0,
                    "success": False,
                    "t": "2020-10-18 08:51:50",
                },
            ]
        },
        ttl=1000,
    )

    results = await history.fetch(project="crlite", name="filter-age")

    assert len(results) == 1
    assert results[0]["scalar"] == 42.0


async def test_history_fetch_with_expired_cache(config):
    config.HISTORY_DAYS = 1

    cache = InMemoryCache()
    history = History(cache=cache)
    await cache.set(
        "scalar-history",
        {
            "crlite/filter-age": [
                {
                    "scalar": 42.0,
                    "success": False,
                    "t": "2020-10-18 08:51:50",
                },
            ]
        },
        ttl=0,
    )

    with mock.patch(
        "telescope.utils.fetch_bigquery",
        return_value=[
            Row("crlite/filter-age", "2020-10-16 08:51:50", True, 32.0),
        ],
    ):
        results = await history.fetch(project="crlite", name="filter-age")

    assert len(results) == 1


async def test_history_fetch_with_empty_cache(config):
    config.HISTORY_DAYS = 1

    cache = InMemoryCache()
    history = History(cache=cache)
    with mock.patch(
        "telescope.utils.fetch_bigquery",
        return_value=[
            Row("crlite/filter-age", "2020-10-16 08:51:50", True, 32.0),
        ],
    ):
        results = await history.fetch(project="crlite", name="filter-age")

    assert len(results) == 1
