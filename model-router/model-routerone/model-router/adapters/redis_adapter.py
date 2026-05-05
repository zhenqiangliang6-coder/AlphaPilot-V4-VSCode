from redis import Redis
import json

class RedisAdapter:
    def __init__(self, host='localhost', port=6379, db=0):
        self.redis = Redis(host=host, port=port, db=db)

    def set(self, key, value, expire=None):
        """Set a value in Redis with an optional expiration time."""
        if expire:
            self.redis.setex(key, expire, json.dumps(value))
        else:
            self.redis.set(key, json.dumps(value))

    def get(self, key):
        """Get a value from Redis."""
        value = self.redis.get(key)
        return json.loads(value) if value else None

    def delete(self, key):
        """Delete a key from Redis."""
        self.redis.delete(key)

    def exists(self, key):
        """Check if a key exists in Redis."""
        return self.redis.exists(key)

    def clear(self):
        """Clear the entire Redis database."""
        self.redis.flushdb()