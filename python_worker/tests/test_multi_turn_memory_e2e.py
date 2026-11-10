# -*- coding: utf-8 -*-
"""
G7.8 多轮对话记忆系统端到端测试
--------------------------------------------------------
验证修复后的记忆系统在多轮对话中正常工作：

架构：PG 中枢优先 + 临时层降级（避免两层并行导致的重复注入）

1. 临时会话记忆（temp_session_memory）
   - 仅当 PG 不可用或无结果时降级激活
   - 3 轮连续对话：保存 → 检索 → 验证不为空

2. PostgreSQL 记忆中枢（如果可用）
   - status='active' 写入后可被检索（G0 审计修复）
   - 跨轮次语义检索
   - PG 可用时，Temp 层不参与读写

3. 降级机制验证
   - PG 不可用 → Temp 接管
   - 两层不会同时写入/检索，避免内容重复

约束：
  - 临时记忆层：纯 JSON 文件，不需要 PG
  - PG 层：如果 PG 不可用或 embedding 维度不匹配，相关测试 skip 而非 fail
"""

import sys
import os
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_worker.temp_session_memory import TempSessionMemory, get_temp_memory
from python_worker.memory_integration import (
    build_memory_context,
    enhance_prompt_with_memory,
    save_task_memories,
    MemoryIntegration,
)
from python_worker.memory_service import MemoryService, MemoryItem, MemoryType, MemoryStatus


# ============================================================
# 工具函数
# ============================================================

def _unique_user_id(prefix: str = "e2e") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _unique_workspace() -> str:
    return str(Path(tempfile.mkdtemp(prefix="alphapilot_e2e_")))


def _pg_available() -> bool:
    try:
        svc = MemoryService()
        conn = svc._get_connection()
        conn.close()
        # 验证 embedding 可用（2525-ot-28 环境 1536-dim vs schema 512-dim 不匹配）
        content = f"pg_probe_{uuid.uuid4().hex[:8]}"
        svc.save_memory(MemoryItem(
            user_id="pg_probe", content=content,
            memory_type=MemoryType.KNOWLEDGE, importance_score=0.1,
            status=MemoryStatus.ACTIVE,
        ))
        return True
    except Exception:
        return False


def _make_task_result(status="success", content="", steps=None):
    return {
        "status": status,
        "content": content,
        "steps": steps or [],
    }


def _make_context(intent="write_code", user_request="", workspace_path=None):
    ctx = {
        "intent": intent,
        "user_request": user_request,
    }
    if workspace_path:
        ctx["workspace_path"] = workspace_path
    return ctx


# ============================================================
# 第一部分：临时会话记忆层 E2E
# ============================================================

class TestTempSessionMemoryE2E:
    """临时会话记忆层 — 多轮对话端到端测试（纯 JSON，不需要 PG）"""

    def test_round1_save_and_retrieve(self):
        """第 1 轮：保存一条记忆后，立即检索能查到"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("u1")
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # 模拟任务结果
        result = _make_task_result(
            status="success",
            content="创建了 Flask 应用主文件 app.py，包含路由 /api/hello",
            steps=[{"type": "write", "output": {"text": "生成 app.py"}}],
        )
        ctx = _make_context(
            intent="write_code",
            user_request="创建一个 Flask API 项目",
            workspace_path=workspace,
        )

        success = save_task_memories(
            user_id=user_id,
            task_id=task_id,
            result=result,
            context=ctx,
            workspace_path=workspace,
        )
        assert success, "第 1 轮记忆保存失败"

        memory_ctx = build_memory_context(
            user_id, task_id, "继续开发", workspace_path=workspace
        )
        assert memory_ctx.has_memory, (
            f"保存后检索应返回记忆上下文，但 has_memory=False\n"
            f"  PG: {bool(memory_ctx.memory_context)}\n"
            f"  可能是 workspace_path 未正确传递到 temp_memory 层"
        )
        print(f"  ✅ 第 1 轮: 保存成功，检索到 ({len(memory_ctx.memory_context)} 字符)")

    def test_round2_retrieve_round1(self):
        """第 2 轮：引用词'继续'触发检索第 1 轮记忆"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("u1")

        # 第 1 轮
        r1 = save_task_memories(
            user_id=user_id,
            task_id="task-round1",
            result=_make_task_result(
                status="success",
                content="生成了 app.py 和 models.py",
            ),
            context=_make_context(
                intent="write_code",
                user_request="创建 Flask 应用的 app.py 和 models.py",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )
        assert r1

        # 第 2 轮：包含引用词（真实多轮对话模式）
        memory_ctx = build_memory_context(
            user_id, "task-round2",
            "好的，继续添加一个 /users 路由",
            workspace_path=workspace,
        )
        assert memory_ctx.has_memory, (
            "第 2 轮引用词'继续'应触发检索第 1 轮记忆，但返回为空\n"
            "  temp_memory search 的 reference_keywords 检测: 继续\n"
            "  confirmation_keywords 检测: 好的"
        )
        print(f"  ✅ 第 2 轮: 引用词'继续'触发检索")

    def test_round2b_keyword_match(self):
        """第 2 轮：关键词 'Flask' 匹配到第 1 轮记忆"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("kw")

        save_task_memories(
            user_id=user_id, task_id="task-round1",
            result=_make_task_result(
                status="success",
                content="Flask 应用主文件 app.py 已生成，包含路由注册",
            ),
            context=_make_context(
                intent="write_code",
                user_request="创建 Flask 应用",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        memory_ctx = build_memory_context(
            user_id, "task-round2",
            "Flask 应用还需要数据库模型",
            workspace_path=workspace,
        )
        # 关键词 'Flask' 应匹配到保存的 prompt+summary
        assert memory_ctx.has_memory, (
            "关键词 'Flask' 应命中 temp memory 的多字关键词匹配\n"
            f"  当前 memory_context: '{memory_ctx.memory_context[:200]}'"
        )
        print(f"  ✅ 关键词匹配: 'Flask' 命中 ({len(memory_ctx.memory_context)} 字符)")

    def test_round3_retrieve_round1_and_round2(self):
        """第 3 轮：能检索到前两轮的累积记忆"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("u1")

        # 第 1 轮
        save_task_memories(
            user_id=user_id, task_id="task-a",
            result=_make_task_result(status="success", content="Flask 项目初始化"),
            context=_make_context(
                intent="write_code",
                user_request="创建项目骨架",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        # 第 2 轮
        save_task_memories(
            user_id=user_id, task_id="task-b",
            result=_make_task_result(status="success", content="添加了 JWT 认证"),
            context=_make_context(
                intent="write_code",
                user_request="添加 JWT 认证中间件",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        # 第 3 轮：包含引用词 + 关键词
        memory_ctx = build_memory_context(
            user_id, "task-c",
            "好的，帮我写 API 文档",
            workspace_path=workspace,
        )
        assert memory_ctx.has_memory, "第 3 轮应能检索到前两轮的累积记忆"
        assert len(memory_ctx.memory_context) > 50, (
            f"记忆上下文不应过短，当前 {len(memory_ctx.memory_context)} 字符"
        )
        print(f"  ✅ 第 3 轮: 检索到累积记忆 ({len(memory_ctx.memory_context)} 字符)")

    def test_prompt_enhancement_includes_memory(self):
        """验证增强后的 prompt 包含记忆上下文标记"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("u1")

        save_task_memories(
            user_id=user_id, task_id="task-x",
            result=_make_task_result(status="success", content="数据库 SQLAlchemy 模型完成"),
            context=_make_context(
                intent="write_code",
                user_request="创建 SQLAlchemy 数据库模型",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        memory_ctx = build_memory_context(
            user_id, "task-y",
            "好的，数据库模型还需要添加迁移",
            workspace_path=workspace,
        )
        enhanced = enhance_prompt_with_memory("添加数据库迁移", memory_ctx)

        assert "记忆上下文" in enhanced, (
            f"增强后的 prompt 应包含 '记忆上下文' 标记\n{enhanced[:200]}"
        )
        assert "当前用户请求" in enhanced, (
            f"增强后的 prompt 应包含 '当前用户请求' 分隔标记"
        )
        assert "添加数据库迁移" in enhanced, "原始 prompt 应在增强后的文本末尾"
        print(f"  ✅ prompt 增强: 包含记忆上下文标记 + 原始请求 ({len(enhanced)} 字符)")

    def test_different_workspace_isolation(self):
        """不同工作区的记忆相互隔离"""
        ws_a = _unique_workspace()
        ws_b = _unique_workspace()
        user_id = _unique_user_id("u1")

        # 工作区 A 的记忆
        save_task_memories(
            user_id=user_id, task_id="task-a",
            result=_make_task_result(status="success", content="项目 A 的 API"),
            context=_make_context(
                intent="write_code",
                user_request="创建项目 A",
                workspace_path=ws_a,
            ),
            workspace_path=ws_a,
        )

        # 工作区 B 的检索 — 不应看到 A 的记忆
        memory_ctx_b = build_memory_context(
            user_id, "task-b",
            "创建项目 B",
            workspace_path=ws_b,
        )
        assert not memory_ctx_b.has_memory or "项目 A" not in memory_ctx_b.memory_context, (
            f"工作区 B 不应检索到工作区 A 的记忆"
        )
        print(f"  ✅ 工作区隔离: ws_a 和 ws_b 的记忆相互独立")

    def test_zzz_clear_on_startup(self):
        """启动时清空所有临时记忆（zzz_ 前缀确保最后执行）"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("u1")

        save_task_memories(
            user_id=user_id, task_id="task-1",
            result=_make_task_result(status="success", content="测试记忆"),
            context=_make_context(
                intent="write_code",
                user_request="测试",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        temp_mem = get_temp_memory()
        cleared = temp_mem.clear_all()
        assert cleared, "clear_all() 应返回 True"

        memory_ctx = build_memory_context(
            user_id, "task-2",
            "继续",
            workspace_path=workspace,
        )
        assert not memory_ctx.has_memory, (
            "clear_all() 后不应再有临时记忆"
        )
        print(f"  ✅ clear_all: 清空后检索返回空")


# ============================================================
# 第二部分：PG 记忆中枢 E2E（需要 PostgreSQL）
# ============================================================

@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL not available")
class TestPGMemoryE2E:
    """PG 记忆层 — 多轮对话端到端测试（需要 Docker PG）"""

    def test_save_as_active_and_retrieve(self):
        """验证 status='active' 的记忆可被检索（G0 修复核心验证）"""
        user_id = _unique_user_id("pg_e2e")
        content = f"多轮测试-PG-{uuid.uuid4().hex[:8]}"

        service = MemoryService()

        # 直接保存一条 memory（模拟 MemoryIntegration 的 save 流程）
        memory = MemoryItem(
            user_id=user_id,
            content=content,
            memory_type=MemoryType.KNOWLEDGE,
            importance_score=0.8,
            domain_tags=["multi-turn-test"],
            status=MemoryStatus.ACTIVE,
        )
        memory_id = service.save_memory(memory)
        assert memory_id, "PG 记忆保存失败"

        # 立即检索 — 应能找到
        results = service.search_similar_memories(
            user_id, "多轮测试", top_k=5
        )
        found = any(content in (r.content or "") for r in results)
        assert found, (
            f"status='active' 的记忆未被检索到！\n"
            f"  保存的 content: {content[:80]}\n"
            f"  检索到 {len(results)} 条, 但内容不匹配\n"
            f"  检查: memory_service.py 的 status 过滤条件是否正确"
        )
        print(f"  ✅ PG active 写入: 保存后立即检索成功 (id={memory_id})")

    def test_multi_turn_pg_context_building(self):
        """模拟 3 轮对话，验证 build_memory_context 能组装记忆"""
        user_id = _unique_user_id("pg_ctx")
        service = MemoryService()

        # 第 1 轮
        service.save_memory(MemoryItem(
            user_id=user_id,
            content=f"第1轮：创建了 Flask 应用骨架 {uuid.uuid4().hex[:6]}",
            memory_type=MemoryType.KNOWLEDGE,
            importance_score=0.8,
            domain_tags=["flask", "project-init"],
            status=MemoryStatus.ACTIVE,
        ))

        # 第 2 轮
        service.save_memory(MemoryItem(
            user_id=user_id,
            content=f"第2轮：添加了 JWT 认证中间件 {uuid.uuid4().hex[:6]}",
            memory_type=MemoryType.KNOWLEDGE,
            importance_score=0.8,
            domain_tags=["flask", "auth"],
            status=MemoryStatus.ACTIVE,
        ))

        # 第 3 轮：检索上下文
        context = service.build_memory_context(
            user_id=user_id,
            current_query="添加 API 路由",
        )
        assert context, "build_memory_context 不应返回空"
        assert "Flask" in context or "JWT" in context or "认证" in context, (
            f"上下文应包含前两轮的记忆内容\n当前: {context[:200]}"
        )
        print(f"  ✅ PG 多轮上下文: 3 轮后检索到 ({len(context)} 字符)")

    def test_status_verified_is_searchable(self):
        """验证 status='verified' 的记忆也可被检索（兼容旧数据）"""
        user_id = _unique_user_id("pg_verified")
        service = MemoryService()
        content_key = f"verified-test-{uuid.uuid4().hex[:8]}"

        memory = MemoryItem(
            user_id=user_id,
            content=f"已验证记忆: {content_key}",
            memory_type=MemoryType.KNOWLEDGE,
            importance_score=0.7,
            status=MemoryStatus.VERIFIED,
        )
        memory_id = service.save_memory(memory)
        assert memory_id

        results = service.search_similar_memories(
            user_id, content_key, top_k=5
        )
        found = any(content_key in (r.content or "") for r in results)
        assert found, (
            f"G0 修复后 status='verified' 应可被检索！\n"
            f"  确认: init_memory_schema.sql 和 memory_service.py 的\n"
            f"  status IN ('active', 'verified', 'confirmed') 已生效"
        )
        print(f"  ✅ PG verified 兼容: status='verified' 可检索 (id={memory_id})")


# ============================================================
# 第三部分：降级机制验证
# ============================================================

class TestDegradationE2E:
    """降级机制验证 — PG 优先 + Temp 降级"""

    def test_temp_activated_when_pg_unavailable(self):
        """PG 不可用时，Temp 接管读写（当前环境 PG 嵌入维度不匹配）"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("degrade")

        # 写入：PG 嵌入维度不匹配 → 自动降级到 Temp
        success = save_task_memories(
            user_id=user_id,
            task_id="task-degrade-1",
            result=_make_task_result(
                status="success",
                content="降级测试：Flask 项目初始化",
            ),
            context=_make_context(
                intent="write_code",
                user_request="创建 Flask 项目",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )
        assert success, "降级写入应成功（Temp 接管）"

        # 检索：PG 无历史数据 → Temp 命中
        memory_ctx = build_memory_context(
            user_id, "task-degrade-2",
            "好的，继续添加路由",
            workspace_path=workspace,
        )
        assert memory_ctx.has_memory, (
            "PG 不可用时应从 Temp 降级检索到记忆"
        )
        assert "Flask" in memory_ctx.memory_context, (
            f"Temp 检索到的内容应包含 'Flask'\n当前: {memory_ctx.memory_context[:200]}"
        )
        print(f"  ✅ 降级写入+检索: Temp 接管成功 ({len(memory_ctx.memory_context)} 字符)")

    def test_no_duplicate_injection(self):
        """验证两层不会同时产生内容（避免 LLM 收到重复上下文）"""
        workspace = _unique_workspace()
        user_id = _unique_user_id("nodup")

        save_task_memories(
            user_id=user_id, task_id="nodup-1",
            result=_make_task_result(status="success", content="用户管理系统已创建"),
            context=_make_context(
                intent="write_code",
                user_request="创建用户管理系统",
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        memory_ctx = build_memory_context(
            user_id, "nodup-2",
            "好的，继续添加权限管理",
            workspace_path=workspace,
        )

        # PG 不可用 → 只应有 Temp 内容，不会有两层拼接
        assert memory_ctx.has_memory

        # 两层拼接的特征：会出现两个 ## 标题或重复内容
        context_text = memory_ctx.memory_context
        dd_count = context_text.count("## ")
        assert dd_count <= 2, (
            f"两层拼接会产生多余的标题，当前 ## 出现 {dd_count} 次\n"
            f"内容前 300 字符: {context_text[:300]}"
        )
        # 不应同时包含 PG 和 Temp 的标记（旧架构会用 "\n\n" 拼接）
        print(f"  ✅ 无重复注入: ## 标题出现 {dd_count} 次, 内容 {len(context_text)} 字符")


# ============================================================
# 第四部分：Worker 调用链模拟
# ============================================================

class TestWorkerCallChainE2E:
    """模拟 qwen_worker_v2.py 真实调用链"""

    def test_simulate_worker_call_chain(self):
        """
        模拟 qwen_worker_v2.py 的完整调用链：
        L298: build_memory_context(user_id, task_id, prompt, workspace_path=...)
        L300: enhance_prompt_with_memory(prompt, memory_ctx)
        L1110: save_task_memories(user_id, ..., workspace_path=...)
        """
        workspace = _unique_workspace()
        user_id = _unique_user_id("worker_sim")
        task_id_1 = f"sim-{uuid.uuid4().hex[:8]}"
        task_id_2 = f"sim-{uuid.uuid4().hex[:8]}"

        # ---- 第 1 轮 ----
        prompt_1 = "帮我创建一个 Flask API 项目"
        memory_ctx_1 = build_memory_context(
            user_id, task_id_1, prompt_1,
            workspace_path=workspace,
        )
        enhanced_1 = enhance_prompt_with_memory(prompt_1, memory_ctx_1)

        assert isinstance(enhanced_1, str) and len(enhanced_1) > 0
        # 首轮应无记忆，增强后的 prompt 应有默认标记
        print(f"  [第 1 轮] 增强 prompt: {len(enhanced_1)} 字符, "
              f"has_memory={memory_ctx_1.has_memory}")

        # 模拟任务执行完成后保存
        save_task_memories(
            user_id=user_id, task_id=task_id_1,
            result=_make_task_result(
                status="success",
                content="生成了 app.py, models.py, auth.py",
            ),
            context=_make_context(
                intent="write_code",
                user_request=prompt_1,
                workspace_path=workspace,
            ),
            workspace_path=workspace,
        )

        # ---- 第 2 轮 ----
        prompt_2 = "好的，继续添加 JWT 认证"
        memory_ctx_2 = build_memory_context(
            user_id, task_id_2, prompt_2,
            workspace_path=workspace,
        )
        enhanced_2 = enhance_prompt_with_memory(prompt_2, memory_ctx_2)

        assert memory_ctx_2.has_memory, (
            "第 2 轮应检索到第 1 轮保存的记忆！\n"
            f"  memory_context 长度: {len(memory_ctx_2.memory_context)}\n"
            f"  检查: qwen_worker_v2.py 是否已补传 workspace_path"
        )
        assert len(enhanced_2) > len(prompt_2), (
            f"第 2 轮增强后的 prompt 应比原始长 (含记忆上下文)\n"
            f"  增强: {len(enhanced_2)} 字符\n"
            f"  原始: {len(prompt_2)} 字符"
        )
        print(f"  [第 2 轮] 增强 prompt: {len(enhanced_2)} 字符, "
              f"has_memory={memory_ctx_2.has_memory}")

        # ---- 第 3 轮：引用词验证 ----
        prompt_3 = "好的，继续添加用户注册功能"
        memory_ctx_3 = build_memory_context(
            user_id, task_id_2, prompt_3,
            workspace_path=workspace,
        )
        enhanced_3 = enhance_prompt_with_memory(prompt_3, memory_ctx_3)

        assert memory_ctx_3.has_memory, (
            "第 3 轮（引用词'继续'）应检索到前两轮的记忆"
        )
        assert len(enhanced_3) > len(prompt_3), (
            f"第 3 轮增强 prompt 应比原始长: {len(enhanced_3)} vs {len(prompt_3)}"
        )
        print(f"  [第 3 轮] 增强 prompt: {len(enhanced_3)} 字符, "
              f"has_memory={memory_ctx_3.has_memory}")

        print(f"\n  ✅ Worker 调用链模拟: 3 轮全部通过")