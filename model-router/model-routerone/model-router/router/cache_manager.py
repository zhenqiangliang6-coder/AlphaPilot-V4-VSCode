class CacheManager:
    def __init__(self):
        self.cache = {}

    def get(self, key):
        """Retrieve an item from the cache."""
        return self.cache.get(key)

    def set(self, key, value):
        """Store an item in the cache."""
        self.cache[key] = value

    def clear(self):
        """Clear the entire cache."""
        self.cache.clear()

    def exists(self, key):
        """Check if an item exists in the cache."""
        return key in self.cache

    def cache_result(self, func):
        """Decorator to cache the result of a function."""
        def wrapper(*args, **kwargs):
            key = (func.__name__, args, frozenset(kwargs.items()))
            if self.exists(key):
                return self.get(key)
            result = func(*args, **kwargs)
            self.set(key, result)
            return result
        return wrapper