import hashlib


class CacheManager:
    def __init__(self):
        self.cache = {}

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value

    def clear(self):
        self.cache.clear()

    def get_from_cache(self, key):
        return self.get(key)

    def save_to_cache(self, key, value):
        self.set(key, value)

    def exists(self, key):
        return key in self.cache

    def build_cache_key(self, prompt, model=None, temperature=0.7, max_tokens=2048):
        payload = f"{prompt}|{model or ''}|{temperature}|{max_tokens}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def cache_result(self, func):
        def wrapper(*args, **kwargs):
            key = (func.__name__, args, frozenset(kwargs.items()))
            if self.exists(key):
                return self.get(key)
            result = func(*args, **kwargs)
            self.set(key, result)
            return result
        return wrapper