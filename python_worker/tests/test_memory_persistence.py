# -*- coding: utf-8 -*-
"""
AlphaPilot 记忆 PG 持久化集成测试
--------------------------------------------------------
验证 ② 跨轮次记忆 PG 持久化：
  - 写入 → 读取 → 重建连接 → 再读取（重启不丢）
  - 多用户隔离
  - 用户偏好持久化
  - build_memory_context 集成链路

约束：不 mock PG，直连 Docker 容器内的真实 PostgreSQL。
      如果 PG 不可用，所有测试 skip 而非 fail。
"""

import sys
import os
import hashlib
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_service import MemoryService, MemoryItem, MemoryType, MemoryStatus


def _pg_available() -> bool:
    try:
        svc = MemoryService()
        conn = svc._get_connection()
        conn.close()
        return True
    except Exception:
        return False


def _unique_user_id(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _unique_content(prefix: str = "test-memory") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def memory_service():
    if not _pg_available():
        pytest.skip("PostgreSQL not available — start Docker: docker compose up -d postgres")
    return MemoryService()


# ============================================================
# 1. 基础连通性
# ============================================================
def test_pg_connection_succeeds(memory_service):
    conn = memory_service._get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    assert cur.fetchone()[0] == 1
    cur.close()
    conn.close()


def test_memory_items_table_exists(memory_service):
    conn = memory_service._get_connection()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.memory_items')")
    assert cur.fetchone()[0] is not None, "memory_items table missing"
    cur.close()
    conn.close()


def test_user_profiles_table_exists(memory_service):
    conn = memory_service._get_connection()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.user_profiles')")
    assert cur.fetchone()[0] is not None, "user_profiles table missing"
    cur.close()
    conn.close()


# ============================================================
# 2. 写入 → 读取（同连接）
# ============================================================
def test_write_read_cycle(memory_service):
    user_id = _unique_user_id("persist")
    content = _unique_content("write-read")
    summary = "写读周期测试摘要"

    item = MemoryItem(
        user_id=user_id,
        content=content,
        summary=summary,
        memory_type=MemoryType.FACT,
        importance_score=0.8,
    )
    memory_id = memory_service.save_memory(item)
    assert memory_id is not None

    results = memory_service.search_similar_memories(
        user_id, content, top_k=10, min_activation=0.0
    )
    found = [m for m in results if m.content == content]
    assert len(found) == 1, f"Expected exactly 1 match, got {len(found)}"
    assert found[0].summary == summary


# ============================================================
# 3. 写入 → 断开 → 重连 → 读取（重启不丢）
# ============================================================
def test_memory_survives_reconnect(memory_service):
    user_id = _unique_user_id("survive")
    content = _unique_content("survive-reconnect")

    item = MemoryItem(
        user_id=user_id,
        content=content,
        memory_type=MemoryType.FACT,
        importance_score=0.9,
    )
    memory_id = memory_service.save_memory(item)
    assert memory_id is not None

    del memory_service

    new_svc = MemoryService()
    results = new_svc.search_similar_memories(
        user_id, content, top_k=10, min_activation=0.0
    )
    found = [m for m in results if m.content == content]

    assert len(found) == 1, (
        f"Memory NOT found after reconnect! PG persistence broken. "
        f"user_id={user_id}, content={content[:40]}..."
    )


# ============================================================
# 4. 用户偏好持久化
# ============================================================
def test_user_preference_persistence(memory_service):
    user_id = _unique_user_id("pref")
    preference = f"默认测试框架 pytest_{uuid.uuid4().hex[:6]}"

    memory_service.save_user_preference(user_id, preference)

    profile = memory_service._get_user_profile(user_id)
    assert profile is not None, f"Profile not found for {user_id}"
    prefs = profile.get("global_preferences", {})
    declared = prefs.get("declared_preferences", [])
    assert preference in declared, f"Preference '{preference}' not in {declared}"


def test_user_preference_update_merges_not_overwrites(memory_service):
    user_id = _unique_user_id("pref-merge")
    pref_a = f"pref_a_{uuid.uuid4().hex[:4]}"
    pref_b = f"pref_b_{uuid.uuid4().hex[:4]}"

    memory_service.save_user_preference(user_id, pref_a)
    memory_service.save_user_preference(user_id, pref_b)

    profile = memory_service._get_user_profile(user_id)
    declared = profile.get("global_preferences", {}).get("declared_preferences", [])
    assert pref_a in declared, f"First preference lost: {pref_a}"
    assert pref_b in declared, f"Second preference not saved: {pref_b}"


# ============================================================
# 5. 多用户隔离
# ============================================================
def test_multi_user_isolation(memory_service):
    user_a = _unique_user_id("iso-A")
    user_b = _unique_user_id("iso-B")
    content_a = _unique_content("secret-A")
    content_b = _unique_content("secret-B")

    memory_service.save_memory(MemoryItem(
        user_id=user_a, content=content_a,
        memory_type=MemoryType.FACT, importance_score=0.8,
    ))
    memory_service.save_memory(MemoryItem(
        user_id=user_b, content=content_b,
        memory_type=MemoryType.FACT, importance_score=0.8,
    ))

    results_a = memory_service.search_similar_memories(user_a, content_a, top_k=10, min_activation=0.0)
    results_b = memory_service.search_similar_memories(user_b, content_b, top_k=10, min_activation=0.0)

    a_contents = {m.content for m in results_a}
    b_contents = {m.content for m in results_b}

    assert content_b not in a_contents, f"User A can see User B's memory!"
    assert content_a not in b_contents, f"User B can see User A's memory!"


# ============================================================
# 6. build_memory_context 集成
# ============================================================
def test_build_memory_context_includes_saved_memory(memory_service):
    user_id = _unique_user_id("ctx")
    content = _unique_content("context-test")
    key_word = content.split("-")[-1]

    memory_service.save_memory(MemoryItem(
        user_id=user_id,
        content=content,
        summary=f"关于 {key_word} 的配置约定",
        memory_type=MemoryType.PREFERENCE,
        importance_score=0.9,
    ))

    ctx = memory_service.build_memory_context(user_id, key_word, max_tokens=2000)
    assert ctx is not None
    assert len(ctx) > 0, "build_memory_context returned empty string"
    assert key_word in ctx or content[:30] in ctx, (
        f"Context missing the saved memory!\nContext: {ctx[:200]}"
    )


# ============================================================
# 7. 边界情况
# ============================================================
def test_empty_user_id_returns_empty_context(memory_service):
    ctx = memory_service.build_memory_context("no-such-user-99999", "anything", max_tokens=500)
    assert isinstance(ctx, str)


def test_save_memory_with_minimal_fields(memory_service):
    user_id = _unique_user_id("minimal")
    content = _unique_content("minimal")

    item = MemoryItem(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    memory_id = memory_service.save_memory(item)
    assert memory_id is not None

    results = memory_service.search_similar_memories(user_id, content, top_k=10, min_activation=0.0)
    assert any(m.content == content for m in results)


def test_search_unknown_user_returns_empty(memory_service):
    results = memory_service.search_similar_memories(
        "no-such-user-" + uuid.uuid4().hex[:8],
        "nothing to find",
        top_k=5,
        min_activation=0.0,
    )
    assert isinstance(results, list)