# -*- coding: utf-8 -*-
"""
tests/test_full_execution_memory_bridge.py
P3「execute_task → save_worker_memory 全链路闭环」基线（Eval Harness）

用途
====
锁定「Worker 执行入口 → 记忆持久化 → 下一轮 Prompt 注入」的 8 条安全契约。

契约映射
========
  F1 全局单例 Store：conversation_context.get_conversation_store() 返回进程级线程安全单例
  F2 写端：worker_runtime.save_conversation_memory() 把执行结果写回 ConversationStore
  F3 读端：worker_runtime.inject_conversation_memory() 读回历史注入 Prompt
  F4 闭环：写成功轮次 → 读回 → 注入字符串含历史结论
  F5 失败排除：outcome=failed 轮次绝不进入下一轮注入字符串
  F6 三级隔离：不同 conversation_id 的轮次互不泄漏
  F7 无 conversation_id 零注入：不报错、Prompt 原样返回
  F8 接线：save_worker_memory 在 context 携带 conversation_id 时自动写回闭环

设计原则（延续 P0/P1/P2「先基线后实现」）：
1. 不依赖外部数据库、不跨测试残留、零副作用。
2. 未实现的契约通过 pytest.importorskip / hasattr 探测自动 SKIP，实现后转 PASS。
3. 全部通过后，P2+P3 安全指标恒满足：
     failed_task_marked_success = 0
     cross_conversation_leak = 0
     unauthorized_injection = 0
"""

import inspect
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Copilot_Alphapilot/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker.conversation_context import (
    ConversationStore,
    ConversationTurn,
    build_conversation_context,
    inject_conversation_context,
)
from python_worker.conversation_context import save_conversation_turn


class TestP3FullLinkBaseline:
    """P3 8 条基线契约。"""

    def test_F1_global_store_singleton(self):
        """全局单例：get_conversation_store() 存在，多次调用返回同一实例。"""
        import python_worker.conversation_context as cc
        if not hasattr(cc, "get_conversation_store"):
            pytest.skip("P3 全局单例 get_conversation_store 未实现")

        store_1 = cc.get_conversation_store()
        store_2 = cc.get_conversation_store()

        assert store_1 is store_2, "全局 Store 必须是进程级单例"

    def test_F2_save_conversation_memory_writes_back(self):
        """写端：worker_runtime.save_conversation_memory() 写入后可从全局 Store 读回。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 写端未实现")
        if not hasattr(wr, "save_conversation_memory"):
            pytest.skip("P3 写端 save_conversation_memory 未实现")

        get_store = pytest.importorskip("python_worker.conversation_context").get_conversation_store

        turn = wr.save_conversation_memory(
            "conv-f2",
            intent="write_code",
            prompt="写一个 hello 函数",
            outcome="success",
            conclusion="def hello(): return 'hello'",
            ts=1000,
        )

        assert turn.turn >= 1
        turns = get_store().get_turns("conv-f2")
        assert any(t.prompt == "写一个 hello 函数" for t in turns)

    def test_F3_inject_conversation_memory_reads_back(self):
        """读端：inject_conversation_memory() 读回历史并注入 Prompt。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 读端未实现")
        if not hasattr(wr, "inject_conversation_memory"):
            pytest.skip("P3 读端 inject_conversation_memory 未实现")

        get_store = pytest.importorskip("python_worker.conversation_context").get_conversation_store
        conv_id = "conv-f3"
        # 先写一条成功历史
        save_conversation_turn(get_store(), conv_id, ConversationTurn(
            turn=1, prompt="定义 add", intent="write_code",
            outcome="success", conclusion="def add(a, b): return a + b",
        ))

        injected = wr.inject_conversation_memory("现在写 mul", conv_id)

        assert "def add(a, b)" in injected, "历史结论未注入下一轮 Prompt"

    def test_F4_closed_loop_write_then_read(self):
        """闭环：write 成功轮次 → read 注入字符串含历史结论。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 闭环未实现")
        if not (hasattr(wr, "save_conversation_memory") and hasattr(wr, "inject_conversation_memory")):
            pytest.skip("P3 写端/读端未实现")

        conv_id = "conv-f4"
        wr.save_conversation_memory(
            conv_id,
            intent="fix_code",
            prompt="修复编译错误",
            outcome="success",
            conclusion="已修复 SyntaxError",
        )

        injected = wr.inject_conversation_memory("继续重构", conv_id)

        assert "已修复 SyntaxError" in injected, "闭环：本轮成功结论未在下一轮出现"

    def test_F5_failed_turn_excluded(self):
        """失败排除：outcome=failed 的轮次绝不进入下一轮注入字符串。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 失败排除未实现")
        if not (hasattr(wr, "save_conversation_memory") and hasattr(wr, "inject_conversation_memory")):
            pytest.skip("P3 写端/读端未实现")

        conv_id = "conv-f5"
        wr.save_conversation_memory(
            conv_id,
            intent="fix_code",
            prompt="修一个崩溃 bug",
            outcome="failed",
            conclusion="修复失败：超时",
        )

        injected = wr.inject_conversation_memory("新的安全请求", conv_id)

        assert "修复失败" not in injected, "失败结论泄漏进下一轮"
        assert "新的安全请求" in injected, "当前请求必须保留"

    def test_F6_conversation_id_isolation(self):
        """三级隔离：不同 conversation_id 的轮次互不泄漏。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 隔离未实现")
        if not (hasattr(wr, "save_conversation_memory") and hasattr(wr, "inject_conversation_memory")):
            pytest.skip("P3 写端/读端未实现")

        wr.save_conversation_memory("conv-A", intent="chat", prompt="机密-A", outcome="success", conclusion="A 的结论")
        wr.save_conversation_memory("conv-B", intent="chat", prompt="机密-B", outcome="success", conclusion="B 的结论")

        injected_a = wr.inject_conversation_memory("A 的下一个请求", "conv-A")

        assert "B 的结论" not in injected_a, "跨会话 B 泄漏到 A"

    def test_F7_no_conversation_id_zero_injection(self):
        """无 conversation_id：零注入，Prompt 原样返回，不报错。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 零注入未实现")
        if not hasattr(wr, "inject_conversation_memory"):
            pytest.skip("P3 读端未实现")

        prompt = "独立任务，无会话"
        assert wr.inject_conversation_memory(prompt, "") == prompt

    def test_F8_save_worker_memory_auto_writes_back(self):
        """接线：save_worker_memory 在 context["meta"]["conversation_id"] 存在时自动写回闭环。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="P3 接线未实现")
        import python_worker.conversation_context as cc_mod_import
        if not hasattr(cc_mod_import, "get_conversation_store"):
            pytest.skip("P3 全局单例 get_conversation_store 未实现")

        conv_id = "conv-f8"
        # 用独立 store 断言，避免污染全局单例
        captured = {}

        def fake_save(*a, **kw):
            captured.update(kw)
            return True

        # 临时替换 save_task_memories 与 get_conversation_store
        import python_worker.worker_runtime as wr_mod
        orig_save = getattr(wr_mod, "save_task_memories", None)
        orig_get = getattr(wr_mod, "get_conversation_store", None)
        local_store = ConversationStore()
        try:
            wr_mod.save_task_memories = fake_save
            wr_mod.get_conversation_store = lambda: local_store
            wr_mod.save_worker_memory(
                user_id="u-f8",
                task_id="t-f8",
                task_type="write_code",
                intent="write_code",
                result="写好了 hello 函数",
                steps=[{"type": "write", "output": "完成"}],
                context={"meta": {
                    "user_request": "写 hello",
                    "workspace_path": "/tmp",
                    "conversation_id": conv_id,
                }},
            )
        finally:
            if orig_save is not None:
                wr_mod.save_task_memories = orig_save
            if orig_get is not None:
                wr_mod.get_conversation_store = orig_get

        turns = local_store.get_turns(conv_id)
        assert len(turns) >= 1, "save_worker_memory 未把本轮写回短期记忆"
        assert turns[-1].outcome == "success"

    def test_F9_prepare_worker_request_injects_and_preserves_conversation_id(self, monkeypatch):
        """端到端读回注入：prepare_worker_request 携带 conversation_id 时，
        1) meta 保留 conversation_id；2) prompt 被短期记忆历史注入。"""
        import python_worker.worker_runtime as wr
        local_store = ConversationStore()
        monkeypatch.setattr(wr, "get_conversation_store", lambda: local_store)
        # 隔离长期记忆，避免外部 DB 依赖
        monkeypatch.setattr(wr, "build_memory_context", lambda *a, **k: type(
            "M", (), {"has_memory": False}
        )())
        monkeypatch.setattr(wr, "enhance_prompt_with_memory", lambda prompt, ctx: prompt)

        conv_id = "conv-f9"
        save_conversation_turn(local_store, conv_id, ConversationTurn(
            turn=1, prompt="上轮：写 add", intent="write_code",
            outcome="success", conclusion="def add(a, b): return a + b",
        ))

        prepared = wr.prepare_worker_request(
            {"prompt": "现在写 mul", "conversation_id": conv_id, "workspace_path": "/tmp"},
            "t-f9",
            "write_code",
            "Test",
        )

        assert prepared["meta"]["conversation_id"] == conv_id, "meta 未保留 conversation_id"
        assert "def add(a, b)" in prepared["prompt"], "上一轮成功结论未注入本轮 Prompt"


def _mock_qwen_execute_deps(qwen, monkeypatch):
    """隔离 Qwen execute_task 的长期记忆 / 流式 / LLM 重逻辑依赖。"""
    monkeypatch.setattr(qwen, "MEMORY_ENABLED", False)  # 隔离长期记忆
    monkeypatch.setattr(qwen, "check_stop_flag", lambda _task_id: False)
    monkeypatch.setattr(qwen, "stream_start", lambda *_a, **_k: None)
    monkeypatch.setattr(qwen, "stream_chunk", lambda *_a, **_k: None)
    monkeypatch.setattr(
        qwen, "execute_step",
        lambda _task_id, step, _events, _context: step.update(
            output={"text": f"{step['type']} completed"}
        ),
    )
    # 隔离 LLM 重逻辑，避免 execute_task 端到端触发网络/推理阻塞
    monkeypatch.setattr(qwen, "run_execution_loop", lambda *_a, **_k: None)
    monkeypatch.setattr(qwen, "finalize_task", lambda *_a, **_k: "mocked")
    monkeypatch.setattr(qwen, "llm_decompose_task", lambda _prompt: [])
    # run_post_analyze 返回 (intent, persona_type, persona_config, execution_chain) 原值
    monkeypatch.setattr(
        qwen, "run_post_analyze",
        lambda *a: (a[4], a[5], a[6], a[15]),
    )


class TestP3QwenConversationBridge:
    """P3 延伸：Qwen Worker 的 conversation_id 提取路径补齐。"""

    def _mock_execute_deps(self, qwen, monkeypatch):
        return _mock_qwen_execute_deps(qwen, monkeypatch)

    def test_Q1_qwen_execute_task_reads_back_short_term_memory(self, monkeypatch, tmp_path):
        """读端：execute_task 在 conversation_id 存在时读回短期记忆注入 Prompt。"""
        qwen = pytest.importorskip(
            "python_worker.agents.qwen.qwen_worker_v2", reason="Qwen Worker v2 不可用"
        )
        if not getattr(qwen, "_SHORT_TERM_MEMORY_ENABLED", False):
            pytest.skip("Qwen Worker 短期记忆闭环未启用")

        injected = []
        monkeypatch.setattr(
            qwen, "inject_conversation_memory",
            lambda prompt, cid: (injected.append((prompt, cid)) or prompt),
        )
        self._mock_execute_deps(qwen, monkeypatch)

        context = {
            "final_file_ops": [],
            "intermediate_results": [],
            "tool_outputs": [],
            "meta": {"conversation_id": "q-conv-1"},
        }
        qwen.execute_task(
            "qwen_generate",
            {"prompt": "写 mul", "workspace_path": str(tmp_path)},
            "q-read-1",
            [],
            [],
            context,
        )

        assert injected, "conversation_id 存在时未调用 inject_conversation_memory"
        assert injected[0][1] == "q-conv-1", "conversation_id 透传错误"

    def test_Q2_qwen_no_conversation_id_zero_injection(self, monkeypatch, tmp_path):
        """无 conversation_id 零注入：不报错、不触发读回。"""
        qwen = pytest.importorskip(
            "python_worker.agents.qwen.qwen_worker_v2", reason="Qwen Worker v2 不可用"
        )
        if not getattr(qwen, "_SHORT_TERM_MEMORY_ENABLED", False):
            pytest.skip("Qwen Worker 短期记忆闭环未启用")

        injected = []
        monkeypatch.setattr(
            qwen, "inject_conversation_memory",
            lambda prompt, cid: (injected.append((prompt, cid)) or prompt),
        )
        self._mock_execute_deps(qwen, monkeypatch)

        context = {"final_file_ops": [], "intermediate_results": [], "tool_outputs": []}
        qwen.execute_task(
            "qwen_generate",
            {"prompt": "写 mul", "workspace_path": str(tmp_path)},
            "q-read-2",
            [],
            [],
            context,
        )

        assert injected == [], "无 conversation_id 时不应触发短期记忆注入"

    def test_Q3_qwen_write_side_outcome_derivation_safety(self):
        """写端 outcome 推导：失败步骤绝不误标 success（安全红线）。"""
        qwen = pytest.importorskip(
            "python_worker.agents.qwen.qwen_worker_v2", reason="Qwen Worker v2 不可用"
        )
        derive = getattr(qwen, "_derive_conversation_outcome", None)
        if derive is None:
            pytest.skip("Qwen Worker 写端 outcome 推导未实现")
        assert qwen.save_conversation_memory is not None, "写端 save_conversation_memory 未导入"

        assert derive([{"type": "code", "error": None}]) == "success"
        assert derive([{"type": "error"}]) == "failed"
        assert derive([{"type": "code", "error": "boom"}]) == "failed"
        assert derive([]) == "success"


def _mirror_node_resolve_conversation_id(body, meta, workspace_path=None):
    """复刻 node-api/index.js resolveConversationId 的确定性算法（契约基线）。

    前端显式传 conversation_id → 原样沿用；否则基于 user_id + project_id
    生成 SHA256 前 16 hex 的稳定 ID（conv- 前缀）。任何一侧算法变更都需同步本基线。
    """
    import hashlib
    cid = body.get("conversation_id")
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    user_id = (meta or {}).get("user_id") or "default-user"
    project_id = (meta or {}).get("project_id") or workspace_path or "default-project"
    raw = user_id + "\x00" + project_id
    return "conv-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class TestP3ConversationIdSourceContract:
    """P3 延伸：会话 ID 源头契约（前端不传 → 后端兜底生成 → Worker 三路径提取闭环）。

    锁定三处断裂的修复，防止回归：
      S1 三路径提取（顶层 / task_context / context）——防 Qwen 单路径退化
      S2 复用 worker_runtime 单一实现——防双实现漂移
      S3 后端生成的稳定 ID 能被 Qwen 端到端提取透传——防 confirm 流程丢 ID
      S4 Node resolveConversationId 确定性算法基线——防兜底 ID 不稳定 / 跨项目串号
    """

    def test_S1_extract_conversation_id_three_paths(self):
        """三路径提取：顶层 / task_context / context 任一位置都能提取，缺失返回 None。"""
        wr = pytest.importorskip("python_worker.worker_runtime", reason="worker_runtime 不可用")
        extract = getattr(wr, "_extract_conversation_id", None)
        if extract is None:
            pytest.skip("worker_runtime._extract_conversation_id 未实现")

        assert extract({"conversation_id": "cid-top"}) == "cid-top"
        assert extract({"task_context": {"conversation_id": "cid-ctx"}}) == "cid-ctx"
        assert extract({"context": {"conversation_id": "cid-plain"}}) == "cid-plain"
        assert extract({"task_context": {}, "context": {}}) is None
        assert extract({}) is None
        assert extract(None) is None

    def test_S2_qwen_reuses_worker_runtime_extract(self):
        """复用单一实现：Qwen 导入的 _extract_conversation_id 与 worker_runtime 同一对象。"""
        qwen = pytest.importorskip(
            "python_worker.agents.qwen.qwen_worker_v2", reason="Qwen Worker v2 不可用"
        )
        extract = getattr(qwen, "_extract_conversation_id", None)
        assert extract is not None, "Qwen 未导入 _extract_conversation_id"

        wr = pytest.importorskip("python_worker.worker_runtime", reason="worker_runtime 不可用")
        assert extract is wr._extract_conversation_id, "Qwen 必须复用 worker_runtime 单一实现"

    def test_S3_qwen_extracts_backend_generated_id_from_task_context(self, monkeypatch, tmp_path):
        """端到端提取：后端生成的 conv- 前缀 ID 写入 task_context，Qwen 提取并透传注入。"""
        qwen = pytest.importorskip(
            "python_worker.agents.qwen.qwen_worker_v2", reason="Qwen Worker v2 不可用"
        )
        if not getattr(qwen, "_SHORT_TERM_MEMORY_ENABLED", False):
            pytest.skip("Qwen Worker 短期记忆闭环未启用")

        injected = []
        monkeypatch.setattr(
            qwen, "inject_conversation_memory",
            lambda prompt, cid: (injected.append((prompt, cid)) or prompt),
        )
        _mock_qwen_execute_deps(qwen, monkeypatch)

        backend_generated_id = "conv-9f3c2b8d4e6a1b7c"
        payload = {
            "prompt": "写 mul",
            "workspace_path": str(tmp_path),
            "task_context": {"conversation_id": backend_generated_id},
        }
        context = {"final_file_ops": [], "intermediate_results": [], "tool_outputs": []}
        qwen.execute_task("qwen_generate", payload, "q-s3", [], [], context)

        assert injected, "task_context 携带 conversation_id 时未触发注入"
        assert injected[0][1] == backend_generated_id, "后端生成的 conversation_id 在 Worker 侧丢失"

    def test_S4_node_resolve_conversation_id_contract(self):
        """确定性算法基线：后端兜底生成稳定 ID，同 user+project 幂等，跨 project 隔离。"""
        # 前端不传 → 后端自动生成 conv- 前缀稳定 ID
        id_1 = _mirror_node_resolve_conversation_id(
            {"prompt": "写代码"}, {"user_id": "u-1", "project_id": "p-1"}
        )
        assert id_1.startswith("conv-"), "后端兜底 ID 必须以 conv- 前缀开头"

        # 同 user + 同 project 多轮 → 同一会话 ID（短期记忆自动衔接）
        id_2 = _mirror_node_resolve_conversation_id(
            {"prompt": "继续改"}, {"user_id": "u-1", "project_id": "p-1"}
        )
        assert id_1 == id_2, "同 user+project 多轮必须生成同一 conversation_id"

        # 不同 project → 不同会话 ID（跨项目隔离）
        id_3 = _mirror_node_resolve_conversation_id(
            {"prompt": "写代码"}, {"user_id": "u-1", "project_id": "p-2"}
        )
        assert id_1 != id_3, "不同 project 必须生成不同 conversation_id"

        # 前端显式续接 → 原样沿用（不覆盖）
        id_4 = _mirror_node_resolve_conversation_id(
            {"conversation_id": "conv-explicit"}, {"user_id": "u-1", "project_id": "p-1"}
        )
        assert id_4 == "conv-explicit", "前端显式 conversation_id 必须原样沿用"