from datetime import datetime, timedelta


class Cache:
    def __init__(self):
        self._content = {}

    def set(self, key, value, ttl):
        # Store expiration datetime along data.
        expires = datetime.now() + timedelta(seconds=ttl)
        self._content[key] = (expires, value)

    def get(self, key):
        try:
            expires, cached = self._content[key]
            # Check if cached data has expired.
            if datetime.now() > expires:
                del self._content[key]
                return None
            # Cached valid data.
            return cached

        except KeyError:
            # Unknown key.
            return None
