from poucave.utils import Cache


def test_cache_set_get():
    cache = Cache()
    cache.set("a", 42, ttl=100)
    cache.set("expired", 3.14, ttl=0)

    assert cache.get("a") == 42
    assert cache.get("b") is None
    assert cache.get("expired") is None
