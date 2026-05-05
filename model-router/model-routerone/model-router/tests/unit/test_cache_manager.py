import pytest
from router.cache_manager import CacheManager

@pytest.fixture
def cache_manager():
    return CacheManager()

def test_cache_set_and_get(cache_manager):
    cache_manager.set("test_key", "test_value")
    assert cache_manager.get("test_key") == "test_value"

def test_cache_expiry(cache_manager):
    cache_manager.set("temp_key", "temp_value", expiry=1)
    time.sleep(2)
    assert cache_manager.get("temp_key") is None

def test_cache_overwrite(cache_manager):
    cache_manager.set("overwrite_key", "value1")
    cache_manager.set("overwrite_key", "value2")
    assert cache_manager.get("overwrite_key") == "value2"

def test_cache_clear(cache_manager):
    cache_manager.set("clear_key", "clear_value")
    cache_manager.clear()
    assert cache_manager.get("clear_key") is None

def test_cache_size_limit(cache_manager):
    for i in range(10):
        cache_manager.set(f"key_{i}", f"value_{i}")
    assert len(cache_manager.cache) <= cache_manager.size_limit