import datetime

import pytest

from poucave.utils import Cache, fetch_bugzilla, fetch_redash, run_parallel, utcnow


BUGZILLA_URL = "https://bugzilla.mozilla.org/rest/bug?whiteboard=poucave "


def test_cache_set_get():
    cache = Cache()
    cache.set("a", 42)

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


async def test_bugzilla_empty_token():
    results = await fetch_bugzilla(cache=None, project="a", name="b")
    assert results == []


async def test_bugzilla_fetch_without_cache(mock_aioresponses, config):
    config.BUGZILLA_API_KEY = "foo"
    mock_aioresponses.get(
        BUGZILLA_URL,
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

    results = await fetch_bugzilla(cache=None, project="telemetry", name="pipeline")

    assert results == [
        {
            "id": 20200801,
            "summary": "",  # hidden
            "last_update": "2020-08-01T00:00:00Z",
            "open": True,
            "status": "REOPENED",
        },
        {
            "id": 20200604,
            "summary": "Open bug",
            "last_update": "2020-06-04T22:54:59Z",
            "open": True,
            "status": "NEW",
        },
        {
            "id": 20200101,
            "summary": "Old open bug",
            "last_update": "2020-01-01T00:00:00Z",
            "open": True,
            "status": "UNKNOWN",
        },
        {
            "id": 20200701,
            "summary": "Recent closed bug",
            "last_update": "2020-07-01T00:00:00Z",
            "open": False,
            "status": "WONTFIX",
        },
    ]


async def test_bugzilla_return_results_from_cache(mock_aioresponses, config):
    config.BUGZILLA_API_KEY = "foo"
    cache = Cache()
    expires = utcnow() + datetime.timedelta(seconds=1000)
    cache.set(
        "bugzilla-bugs",
        (
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
            expires,
        ),
    )

    results = await fetch_bugzilla(cache=cache, project="telemetry", name="pipeline")

    assert len(results) == 1
    assert results[0]["id"] == 111


async def test_bugzilla_fetch_with_expired_cache(mock_aioresponses, config):
    config.BUGZILLA_API_KEY = "foo"
    mock_aioresponses.get(BUGZILLA_URL, payload={"bugs": []})
    cache = Cache()
    expires = utcnow() - datetime.timedelta(seconds=1000)
    cache.set("bugzilla-bugs", ({"bugs": [{}, {}, {}]}, expires))

    results = await fetch_bugzilla(cache=cache, project="telemetry", name="pipeline")

    assert len(results) == 0


async def test_bugzilla_fetch_with_empty_cache(mock_aioresponses, config):
    config.BUGZILLA_API_KEY = "foo"
    mock_aioresponses.get(BUGZILLA_URL, payload={"bugs": []})
    cache = Cache()

    results = await fetch_bugzilla(cache=cache, project="telemetry", name="pipeline")

    assert len(results) == 0
