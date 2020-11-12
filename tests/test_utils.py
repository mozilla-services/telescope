import pytest

from poucave.utils import BugTracker, Cache, extract_json, fetch_redash, run_parallel


def test_cache_set_get():
    cache = Cache()
    cache.set("a", 42, ttl=1)

    assert cache.get("a") == 42
    assert cache.get("b") is None


async def test_fetch_redash(mock_aioresponses):
    url = "https://sql.telemetry.mozilla.org/api/queries/64921/results.json?api_key=abc"

    row = {
        "status": "network_error",
        "source": "normandy/recipe/123",
        "min_timestamp": "2019-09-16T01:36:12.348",
        "total": 333,
        "max_timestamp": "2019-09-16T07:24:58.741",
    }

    mock_aioresponses.get(
        url, status=200, payload={"query_result": {"data": {"rows": [row]}}}
    )

    rows = await fetch_redash(query_id=64921, api_key="abc")

    assert rows == [row]


async def test_run_parallel():
    async def success():
        return 42

    async def failure():
        raise ValueError()

    with pytest.raises(ValueError):
        await run_parallel(success(), failure(), success())


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

    with pytest.raises(ValueError):
        extract_json(".pings.a", data)
        extract_json(".field", "An error returned by check")


async def test_bugzilla_fetch_fallsback_to_empty_list(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    results = await tracker.fetch(project="telemetry", name="pipeline")
    assert results == []


async def test_bugzilla_fetch_without_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    tracker = BugTracker()
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=poucave ",
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
    cache = Cache()
    tracker = BugTracker(cache=cache)
    cache.set(
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
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=poucave ",
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
    cache = Cache()
    tracker = BugTracker(cache=cache)
    cache.set("bugtracker-list", {"bugs": [{}, {}, {}]}, ttl=0)

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert len(results) == 1


async def test_bugzilla_fetch_with_empty_cache(mock_aioresponses, config):
    config.BUGTRACKER_URL = "https://bugzilla.mozilla.org"
    mock_aioresponses.get(
        config.BUGTRACKER_URL + "/rest/bug?whiteboard=poucave ",
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
    cache = Cache()
    tracker = BugTracker(cache=cache)

    results = await tracker.fetch(project="telemetry", name="pipeline")

    assert len(results) == 1
