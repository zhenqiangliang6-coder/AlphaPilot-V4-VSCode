import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from cache_manager import CacheManager


@pytest.fixture
def cache_manager():
    return CacheManager()


def test_cache_set_and_get(cache_manager):
    cache_manager.set("test_key", "test_value")
    assert cache_manager.get("test_key") == "test_value"


def test_cache_get_from_cache_alias(cache_manager):
    cache_manager.set("alias_key", "alias_value")
    assert cache_manager.get_from_cache("alias_key") == "alias_value"


def test_cache_save_to_cache_alias(cache_manager):
    cache_manager.save_to_cache("save_key", "save_value")
    assert cache_manager.get("save_key") == "save_value"


def test_cache_overwrite(cache_manager):
    cache_manager.set("overwrite_key", "value1")
    cache_manager.set("overwrite_key", "value2")
    assert cache_manager.get("overwrite_key") == "value2"


def test_cache_clear(cache_manager):
    cache_manager.set("clear_key", "clear_value")
    cache_manager.clear()
    assert cache_manager.get("clear_key") is None


def test_cache_exists(cache_manager):
    cache_manager.set("exists_key", "exists_value")
    assert cache_manager.exists("exists_key") is True
    assert cache_manager.exists("nonexistent") is False


def test_cache_miss_returns_none(cache_manager):
    assert cache_manager.get("nonexistent") is None


def test_build_cache_key_deterministic(cache_manager):
    k1 = cache_manager.build_cache_key("hello", "Qwen", 0.7, 2048)
    k2 = cache_manager.build_cache_key("hello", "Qwen", 0.7, 2048)
    assert k1 == k2


def test_build_cache_key_different_prompt(cache_manager):
    k1 = cache_manager.build_cache_key("hello", "Qwen", 0.7, 2048)
    k2 = cache_manager.build_cache_key("world", "Qwen", 0.7, 2048)
    assert k1 != k2


def test_build_cache_key_different_model(cache_manager):
    k1 = cache_manager.build_cache_key("hello", "Qwen", 0.7, 2048)
    k2 = cache_manager.build_cache_key("hello", "DeepSeek", 0.7, 2048)
    assert k1 != k2


def test_build_cache_key_different_temperature(cache_manager):
    k1 = cache_manager.build_cache_key("hello", "Qwen", 0.7, 2048)
    k2 = cache_manager.build_cache_key("hello", "Qwen", 1.0, 2048)
    assert k1 != k2


def test_build_cache_key_model_none(cache_manager):
    k1 = cache_manager.build_cache_key("hello")
    k2 = cache_manager.build_cache_key("hello", None, 0.7, 2048)
    assert k1 == k2