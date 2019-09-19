from poucave.utils import Cache, fetch_redash


def test_cache_set_get():
    cache = Cache()
    cache.set("a", 42, ttl=100)
    cache.set("expired", 3.14, ttl=0)

    assert cache.get("a") == 42
    assert cache.get("b") is None
    assert cache.get("expired") is None


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
