# -*- coding: utf-8 -*-
# python_worker/orchestrator.py — 多 Worker 智能编排器
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - Orchestrator 是 python_worker 内部组件，不做跨层决策
#    - 所有分解/分发/聚合逻辑发生在 Worker 层
#    - 语言 Worker（node/ts/java）不做任何编排决策
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - 编排消息格式遵守 contracts/task-orchestration-v1.schema.json
#    - 子任务发布遵守 contracts/task-protocol-v1.schema.json
#    - 不引入新端点、不修改 Extension/Webview 协议
#
# ✅ Extension = 映射 | Webview = 投影
#    - Orchestrator 对 Extension 完全透明
#    - Extension 仍然只发一个 task → 收一个结果
#    - 编排是多 Worker 的内部实现细节
#
# 设计原则：
#   1. 零侵入 — 不改变现有单 Worker 路径
#   2. 智能拆解 — LLM 分析输入，自动识别多语言/多项目
#   3. 并行优先 — 无依赖子任务并行执行
#   4. 降级安全 — 任何编排失败自动回退单 Worker 路径
#   5. 渐进启用 — Feature toggle 控制，可随时关闭
#
# ---------------------------------------------------------

from __future__ import annotations

import concurrent.futures
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.qwen.step_executor.execute_step import execute_step

# ── Worker 队列映射 ──
# 与 contracts/task-orchestration-v1.schema.json #/$defs/workerQueueMapping 一致
LANGUAGE_TO_QUEUE: Dict[str, str] = {
    "python": "task_queue:qwen",
    "javascript": "node_worker",
    "typescript": "ts_worker",
    "java": "java_worker",
}

QUEUE_TO_TASK_TYPE: Dict[str, str] = {
    "task_queue:qwen": "qwen_generate",
    "node_worker": "node_generate",
    "ts_worker": "ts_generate",
    "java_worker": "java_generate",
}

QUEUE_TO_LANGUAGE: Dict[str, str] = {
    "task_queue:qwen": "python",
    "node_worker": "javascript",
    "ts_worker": "typescript",
    "java_worker": "java",
}


@dataclass
class SubTask:
    """单个子任务 — 与 orchestrationSubtask schema 一致。"""
    subtask_id: str
    worker_queue: str
    task_type: str
    target_language: str
    prompt: str
    workspace_path: str
    depends_on: List[str] = field(default_factory=list)
    index: int = 0
    priority: int = 50


@dataclass
class OrchestrationPlan:
    """编排计划 — 与 orchestrationPlan schema 一致。"""
    orchestration_id: str
    trace_id: str
    strategy: str  # "parallel" | "sequential" | "dag"
    subtasks: List[SubTask]
    original_prompt: str
    llm_analysis: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 600000

    @property
    def is_multi_worker(self) -> bool:
        """是否涉及多个不同的 Worker。"""
        queues = {s.worker_queue for s in self.subtasks}
        return len(queues) >= 2

    @property
    def languages(self) -> List[str]:
        return list({s.target_language for s in self.subtasks})


@dataclass
class SubTaskResult:
    """子任务执行结果。"""
    subtask_id: str
    status: str  # "done" | "failed" | "timeout" | "cancelled"
    worker_queue: str
    target_language: str
    result: Optional[Dict[str, Any]] = None
    duration_ms: int = 0
    workspace_path: str = ""
    generated_files: List[str] = field(default_factory=list)
    error: Optional[Dict[str, str]] = None


# ── LLM 多语言分解 Prompt ──
MULTI_LANGUAGE_DECOMPOSE_PROMPT = """你是多语言项目编排器。分析用户输入，判断是否包含多语言/多项目需求。

如果检测到多种编程语言或独立项目，拆解为独立的子任务。每个子任务必须：
- 包含完整的、可独立执行的 prompt
- 指定 target_language（python/java/javascript/typescript）
- 如果子任务之间无数据依赖，它们可以并行执行

输出格式（必须严格 JSON）：
{
  "is_multi_language": true/false,
  "reasoning": "<分析推理>",
  "strategy": "parallel" 或 "sequential",
  "languages_detected": ["typescript", "javascript"],
  "subtasks": [
    {
      "index": 0,
      "target_language": "typescript",
      "prompt": "<完整的独立 prompt>",
      "depends_on": []
    },
    {
      "index": 1,
      "target_language": "javascript",
      "prompt": "<完整的独立 prompt>",
      "depends_on": []
    }
  ]
}

判断标准：
- 用户在同一请求中提到两种及以上编程语言 → is_multi_language=true
- 用户提到多个独立的项目/模块（如"写一个前端和一个后端"）→ is_multi_language=true
- 用户只提一种语言、一个项目 → is_multi_language=false
- 即使 is_multi_language=false，也输出完整 JSON（subtasks 只有一项）

示例：
用户："用 TypeScript 写任务管理器，用 JavaScript 写 mini 后端"
输出：{"is_multi_language":true,"reasoning":"两个独立项目：TS 任务管理器 + JS 后端","strategy":"parallel","languages_detected":["typescript","javascript"],"subtasks":[{"index":0,"target_language":"typescript","prompt":"写一个 TypeScript 任务管理器，包含...","depends_on":[]},{"index":1,"target_language":"javascript","prompt":"写一个 JavaScript mini 后端，包含...","depends_on":[]}]}
"""


class Orchestrator:
    """多 Worker 智能编排器。

    职责：
        1. 分析用户输入 → 判断是否需要多 Worker 编排
        2. 拆解 → 子任务映射到各 Worker 队列
        3. 并行分发 → 等待结果 → 聚合

    使用方式:
        orch = Orchestrator(redis_client)
        plan = orch.analyze(user_prompt)            # LLM 分析
        if plan and plan.is_multi_worker:
            result = orch.execute(plan)             # 并行执行
        # 否则走现有单 Worker 路径
    """

    # ── Feature Toggles ──
    ENABLED = os.environ.get("ORCHESTRATOR_ENABLED", "true").lower() == "true"

    # 统一执行模式：Python Worker 自己写代码 + Adapter 编译测试（默认开启）
    # 不再分发到语言 Worker，改为 Python Worker 直接调用工具链
    # 设置 ORCHESTRATOR_UNIFIED_MODE=false 可回退旧 LPUSH 路径（已废弃）
    UNIFIED_MODE = os.environ.get("ORCHESTRATOR_UNIFIED_MODE", "true").lower() == "true"

    MAX_PARALLEL = int(os.environ.get("ORCHESTRATOR_MAX_PARALLEL", "4"))
    MULTI_LANGUAGE_THRESHOLD = int(os.environ.get("ORCHESTRATOR_MULTI_THRESHOLD", "2"))
    RESULT_POLL_INTERVAL_S = float(os.environ.get("ORCHESTRATOR_POLL_INTERVAL", "1.0"))
    RESULT_PREFIX = "task_result:"

    def __init__(self, redis_client):
        """初始化编排器。

        Args:
            redis_client: Redis 客户端实例（与 python_worker 共享同一连接）。
        """
        self.redis = redis_client

    # ── 公共 API ──

    def analyze(self, prompt: str) -> Optional[OrchestrationPlan]:
        """分析用户输入，判断是否需要多 Worker 编排。

        调用 LLM 进行语义分析。如果检测到多语言/多项目需求，
        生成 OrchestrationPlan；否则返回 None（走现有单 Worker 路径）。

        Args:
            prompt: 用户原始输入

        Returns:
            OrchestrationPlan 或 None（不需要编排）
        """
        if not self.ENABLED:
            return None

        classify = self._llm_classify_multi_language(prompt)
        if not classify or not classify.get("is_multi_language"):
            return None

        subtasks_raw = classify.get("subtasks", [])
        if len(subtasks_raw) < self.MULTI_LANGUAGE_THRESHOLD:
            return None

        # 校验：每个子任务必须指定有效的 target_language
        valid = [s for s in subtasks_raw
                 if s.get("target_language") in LANGUAGE_TO_QUEUE and s.get("prompt")]
        if len(valid) < self.MULTI_LANGUAGE_THRESHOLD:
            return None

        orch_id = f"orch-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{orch_id}"

        subtasks = []
        for s in valid:
            lang = s["target_language"]
            idx = s.get("index", len(subtasks))
            sid = f"{orch_id}-{idx}"
            ws = os.path.join(
                os.environ.get(
                    "ALPHAPILOT_WORKSPACE_ROOT",
                    os.path.join(os.path.expanduser("~"), "alphapilot_workspaces"),
                ),
                ".orchestrator",
                f"orch-{sid}",
            )
            subtasks.append(SubTask(
                subtask_id=sid,
                worker_queue=LANGUAGE_TO_QUEUE[lang],
                task_type=QUEUE_TO_TASK_TYPE.get(LANGUAGE_TO_QUEUE[lang], "qwen_generate"),
                target_language=lang,
                prompt=s["prompt"],
                workspace_path=ws,
                depends_on=s.get("depends_on", []),
                index=idx,
                priority=50,
            ))

        plan = OrchestrationPlan(
            orchestration_id=orch_id,
            trace_id=trace_id,
            strategy=classify.get("strategy", "parallel"),
            subtasks=subtasks,
            original_prompt=prompt,
            llm_analysis={
                "reasoning": classify.get("reasoning", ""),
                "languages_detected": classify.get("languages_detected", []),
            },
        )

        print(f"\n🔀 [Orchestrator] 多 Worker 编排计划:")
        print(f"   · 编排 ID: {orch_id}")
        print(f"   · 策略: {plan.strategy}")
        print(f"   · 语言: {plan.languages}")
        for s in plan.subtasks:
            print(f"   · [{s.target_language}] → {s.worker_queue}: {s.prompt[:60]}...")
        print()

        return plan

    def execute(self, plan: OrchestrationPlan) -> Dict[str, Any]:
        """执行编排计划。

        根据 strategy 选择执行模式：
        - parallel: 所有无依赖子任务并行分发，等待全部完成后聚合
        - sequential: 按 index 顺序执行
        - dag: 拓扑排序后按依赖层级执行

        Args:
            plan: 编排计划（由 analyze() 生成）

        Returns:
            聚合后的 orchestrationResult（符合 contracts schema）
        """
        t0 = time.time()

        # 为每个子任务创建工作区
        for s in plan.subtasks:
            os.makedirs(s.workspace_path, exist_ok=True)

        # ── 统一执行模式（已默认启用）──
        results = self._execute_via_step_executor(plan)

        return self._aggregate(plan, results, time.time() - t0)

    # ── 内部实现 ──

    # ── G9 收敛：编排器委托 step executor 执行子任务 ──

    def _execute_via_step_executor(self, plan: OrchestrationPlan) -> List[SubTaskResult]:
        """G9 收敛后：编排器委托 step executor 执行每个子任务。

        编排器职责：分解 → 分发 → 聚合。
        子任务执行：委托给 step executor 的 write / test / fix 管线。

        Strategy:
          - parallel: ThreadPoolExecutor 并行跑每个子任务
          - sequential: for 循环顺序跑每个子任务
        """
        if plan.strategy == "parallel" and len(plan.subtasks) > 1:
            return self._run_subtasks_parallel(plan)
        else:
            return self._run_subtasks_sequential(plan)

    def _run_subtasks_sequential(self, plan: OrchestrationPlan) -> List[SubTaskResult]:
        """顺序执行所有子任务。"""
        print(f"🧠 [Orchestrator:UNIFIED] 串行执行 {len(plan.subtasks)} 个子任务...")
        results: List[SubTaskResult] = []
        for st in sorted(plan.subtasks, key=lambda x: x.index):
            results.append(self._run_subtask(st, plan))
        return results

    def _run_subtasks_parallel(self, plan: OrchestrationPlan) -> List[SubTaskResult]:
        """并行执行所有子任务（ThreadPoolExecutor）。"""
        print(f"🧠 [Orchestrator:UNIFIED] 并行执行 {len(plan.subtasks)} 个子任务...")
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.MAX_PARALLEL, len(plan.subtasks))) as executor:
            futures = {
                executor.submit(self._run_subtask, st, plan): st
                for st in plan.subtasks
            }
            results_map: Dict[str, SubTaskResult] = {}
            for future in concurrent.futures.as_completed(futures):
                st = futures[future]
                try:
                    result = future.result(timeout=plan.timeout_ms / 1000)
                    results_map[st.subtask_id] = result
                except concurrent.futures.TimeoutError:
                    results_map[st.subtask_id] = SubTaskResult(
                        subtask_id=st.subtask_id,
                        status="timeout",
                        worker_queue=st.worker_queue,
                        target_language=st.target_language,
                    )
                except Exception as e:
                    results_map[st.subtask_id] = SubTaskResult(
                        subtask_id=st.subtask_id,
                        status="failed",
                        worker_queue=st.worker_queue,
                        target_language=st.target_language,
                        error={"message": str(e)},
                    )
        # 保持原始顺序
        return [results_map.get(st.subtask_id, SubTaskResult(
            subtask_id=st.subtask_id,
            status="failed",
            worker_queue=st.worker_queue,
            target_language=st.target_language,
            error={"message": "result not found"},
        )) for st in plan.subtasks]

    def _run_subtask(self, st: SubTask, plan: OrchestrationPlan) -> SubTaskResult:
        """G9 收敛：委托 step executor 执行子任务完整管线。

        管线：write_step -> 写入磁盘 -> 安装依赖 -> 编译 -> 测试 -> fix 闭环
        不再自建 LLM 调用链条，全部委托给 step executor。
        """
        t_start = time.time()
        lang = st.target_language

        print(f"\n   ┌─ [{lang}] {st.subtask_id}")
        print(f"   │  prompt: {st.prompt[:80]}...")

        adapter = _get_adapter(lang)
        if adapter is None:
            print(f"   │  ❌ 不支持的编程语言: {lang}")
            return SubTaskResult(
                subtask_id=st.subtask_id,
                status="failed",
                worker_queue=st.worker_queue,
                target_language=lang,
                duration_ms=int((time.time() - t_start) * 1000),
                error={"message": f"unsupported language: {lang}"},
            )

        ws = st.workspace_path
        task_id = st.subtask_id
        max_fix_rounds = int(os.environ.get("ORCHESTRATOR_FIX_ROUNDS", "3"))

        context: Dict[str, Any] = {
            "meta": {
                "workspace_path": ws,
                "user_request": st.prompt,
                "target_language": lang,
                "persona": "engineer",
                "intent": "write_code",
            },
            "workspace_scan": {},
            "intermediate_results": [],
            "final_file_ops": [],
        }
        events: list = []

        # ── 1. write_step：LLM 生成代码 ──
        write_step: Dict[str, Any] = {
            "type": "write",
            "input": {"prompt": st.prompt},
        }
        try:
            execute_step(task_id, write_step, events, context)
        except Exception as e:
            return SubTaskResult(
                subtask_id=st.subtask_id,
                status="failed",
                worker_queue=st.worker_queue,
                target_language=lang,
                duration_ms=int((time.time() - t_start) * 1000),
                error={"message": f"write_step failed: {e}"},
            )

        wo = write_step.get("output", {})
        if not wo.get("llm_success", True):
            return SubTaskResult(
                subtask_id=st.subtask_id,
                status="failed",
                worker_queue=st.worker_queue,
                target_language=lang,
                duration_ms=int((time.time() - t_start) * 1000),
                error={"message": "LLM code generation failed"},
            )

        # 将 file_ops 写入磁盘
        file_ops = context.get("final_file_ops", [])
        written_files: List[str] = []
        for fop in file_ops:
            content = fop.get("content", "")
            path = fop.get("path", "")
            if not content or not path:
                continue
            file_path = os.path.join(ws, path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            written_files.append(path)
            print(f"   │  📄 {path} ({len(content)} bytes)")

        if not written_files:
            return SubTaskResult(
                subtask_id=st.subtask_id,
                status="failed",
                worker_queue=st.worker_queue,
                target_language=lang,
                duration_ms=int((time.time() - t_start) * 1000),
                error={"message": "no files generated"},
            )

        print(f"   │  ✅ 代码生成 ({len(written_files)} files)")

        # ── 2. 安装依赖 ──
        deps = adapter.install_dependencies(ws)
        if deps.error:
            print(f"   │  ⚠️ 依赖安装: {deps.error[:60]}")
        else:
            print(f"   │  📦 依赖安装: {'OK' if deps.success else 'FAILED'} ({deps.duration_seconds:.1f}s)")

        # ── 3. 编译 + fix 闭环 ──
        compile_result = adapter.compile(ws)
        print(f"   │  🔨 编译: {'OK' if compile_result.success else 'FAILED'} ({compile_result.duration_seconds:.1f}s)")

        fix_round = 0
        while not compile_result.success and fix_round < max_fix_rounds:
            fix_round += 1
            print(f"   │  🔧 修复轮次 {fix_round}/{max_fix_rounds}: 编译错误")
            self._call_fix_step(
                task_id, st, ws,
                compile_result.stderr or compile_result.error or "",
                context, events,
            )
            compile_result = adapter.compile(ws)

        if not compile_result.success:
            print(f"   │  ❌ {max_fix_rounds} 轮修复后编译仍未通过")
            return SubTaskResult(
                subtask_id=st.subtask_id,
                status="failed",
                worker_queue=st.worker_queue,
                target_language=lang,
                duration_ms=int((time.time() - t_start) * 1000),
                result={"compile_error": compile_result.stderr[:1000]},
                error={"message": f"compile failed after {fix_round} fix rounds"},
            )

        # ── 4. 测试 ──
        test_result = adapter.run_tests(ws)
        print(f"   │  🧪 测试: {test_result.passed_tests}/{test_result.total_tests} passed"
              f" ({test_result.duration_seconds:.1f}s)")

        # ── 5. 测试 fix 闭环 ──
        fix_round = 0
        while not test_result.success and fix_round < max_fix_rounds:
            fix_round += 1
            print(f"   │  🔧 修复轮次 {fix_round}/{max_fix_rounds}: 测试失败")
            error_info = (
                f"{test_result.failed_tests} tests failed.\n"
                f"{test_result.stdout[:2000]}{test_result.stderr[:2000]}"
            )
            self._call_fix_step(task_id, st, ws, error_info, context, events)
            test_result = adapter.run_tests(ws)

        # ── 6. 收集结果 ──
        duration_ms = int((time.time() - t_start) * 1000)
        status = "done" if test_result.success else "test_failed"

        result = SubTaskResult(
            subtask_id=st.subtask_id,
            status=status,
            worker_queue=st.worker_queue,
            target_language=lang,
            duration_ms=duration_ms,
            workspace_path=ws,
            generated_files=written_files,
            result={
                "compile": compile_result.to_dict(),
                "test": test_result.to_dict(),
                "generated_files": written_files,
                "file_ops_count": len(file_ops),
            },
        )
        print(f"   └─ [{lang}] {status} ({duration_ms}ms)")
        return result

    def _call_fix_step(
        self,
        task_id: str,
        st: "SubTask",
        ws: str,
        error_info: str,
        context: Dict[str, Any],
        events: list,
    ) -> None:
        """调用 step executor 的 fix 步骤修复代码并写回磁盘。

        为 fix_step 构造独立上下文（含错误信息注入到 intermediate_results），
        修复后的 file_ops 直接写回工作区。
        """
        if not error_info:
            return

        ctx_copy: Dict[str, Any] = {
            "meta": context.get("meta", {}),
            "workspace_scan": context.get("workspace_scan", {}),
            "intermediate_results": [
                {"type": "test", "output": {"text": error_info}, "status": "failed"}
            ],
            "final_file_ops": [],
        }
        fix_events: list = []

        fix_step: Dict[str, Any] = {"type": "fix"}
        try:
            execute_step(task_id, fix_step, fix_events, ctx_copy)
        except Exception as e:
            print(f"   │  ⚠️ fix_step 异常: {e}")
            return

        file_ops = ctx_copy.get("final_file_ops", [])
        for fop in file_ops:
            content = fop.get("content", "")
            path = fop.get("path", "")
            if not content or not path:
                continue
            file_path = os.path.join(ws, path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(content)

        if file_ops:
            print(f"   │  📄 修复写入 {len(file_ops)} 个文件")


    def _aggregate(
        self,
        plan: OrchestrationPlan,
        results: List[SubTaskResult],
        total_duration_s: float,
    ) -> Dict[str, Any]:
        """聚合子任务结果。

        Args:
            plan: 编排计划
            results: 子任务执行结果列表
            total_duration_s: 总耗时（秒）

        Returns:
            符合 orchestrationResult schema 的聚合结果
        """
        all_done = all(r.status == "done" for r in results)
        any_done = any(r.status == "done" for r in results)
        all_failed = all(r.status != "done" for r in results)

        if all_done:
            agg_status = "all_success"
        elif any_done:
            agg_status = "partial_success"
        else:
            agg_status = "all_failed"

        # 按语言分组文件
        files_by_language: Dict[str, List[str]] = {}
        total_files = 0
        for r in results:
            lang = r.target_language
            if lang not in files_by_language:
                files_by_language[lang] = []
            files_by_language[lang].extend(r.generated_files)
            total_files += len(r.generated_files)

        # 生成摘要
        summary_parts = []
        for r in results:
            icon = "✅" if r.status == "done" else "❌"
            summary_parts.append(
                f"{icon} [{r.target_language}] {r.subtask_id}: "
                f"{r.status} ({r.duration_ms}ms, {len(r.generated_files)} files)"
            )
        summary = "\n".join(summary_parts)

        # 警告
        warnings = []
        if agg_status == "partial_success":
            failed = [r.subtask_id for r in results if r.status != "done"]
            warnings.append(f"部分子任务失败: {failed}")
        for r in results:
            if r.status == "timeout":
                warnings.append(f"{r.subtask_id} 超时未完成")

        result = {
            "protocol_version": "1.0",
            "orchestration_id": plan.orchestration_id,
            "trace_id": plan.trace_id,
            "status": agg_status,
            "subtasks_results": [
                {
                    "subtask_id": r.subtask_id,
                    "status": r.status,
                    "worker_queue": r.worker_queue,
                    "target_language": r.target_language,
                    "result": r.result,
                    "duration_ms": r.duration_ms,
                    "workspace_path": r.workspace_path,
                    "generated_files": r.generated_files,
                    "error": r.error,
                }
                for r in results
            ],
            "aggregated_output": {
                "summary": summary,
                "files_by_language": files_by_language,
                "total_files": total_files,
                "total_duration_ms": int(total_duration_s * 1000),
                "warnings": warnings,
            },
            "aggregated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        print(f"\n{'=' * 60}")
        print(f"📊 [Orchestrator] 聚合完成: {agg_status}")
        print(f"   · 总耗时: {total_duration_s:.1f}s")
        print(f"   · 总文件: {total_files}")
        for lang, files in files_by_language.items():
            print(f"   · [{lang}]: {len(files)} files")
        if warnings:
            for w in warnings:
                print(f"   ⚠️ {w}")
        print(f"{'=' * 60}\n")

        return result

    @staticmethod
    def _parse_classify_json(raw: str) -> Optional[Dict[str, Any]]:
        """容错 JSON 解析，处理 LLM 常见格式问题。

        三层回退：
          1. 标准 json.loads
          2. 去掉 markdown ``` 包裹后 json.loads
          3. ast.literal_eval（容忍单引号）
        """
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None

        text = raw.strip()

        # 尝试标准 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 去掉可能的 markdown 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 2:
                text = "\n".join(lines[1:-1]).strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # 容忍单引号（Python 字面量语法）
        try:
            import ast
            result = ast.literal_eval(text)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError):
            pass

        return None

    def _llm_classify_multi_language(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用 LLM 分析是否为多语言/多项目需求。

        使用与 intent_router._classification 相同的 LLM 调用路径，
        但使用专门的 MULTI_LANGUAGE_DECOMPOSE_PROMPT。

        Args:
            prompt: 用户原始输入

        Returns:
            分类结果 dict 或 None（LLM 调用失败时降级）
        """
        try:
            # 复用 intent_router 的 LLM 调用基础设施（含模型降级链）
            from intent_router._classification import (
                call_provider_for_classify,
                _resolve_qwen_classify_chain,
            )

            full_prompt = (
                f"{MULTI_LANGUAGE_DECOMPOSE_PROMPT}\n\n"
                f"用户输入:\n{prompt}\n\n"
                f"输出（严格 JSON）:"
            )

            chain = _resolve_qwen_classify_chain()
            max_timeout = int(os.environ.get("LLM_CLASSIFY_TIMEOUT", "60"))
            for idx, model in enumerate(chain):
                try:
                    raw = call_provider_for_classify(
                        prompt=full_prompt,
                        model_name="qwen",
                        model_override=model,
                        max_timeout=max_timeout,
                    )
                except Exception:
                    if len(chain) > 1:
                        print(f"   ⚠️ [Orchestrator] 模型 '{model}' 调用异常，尝试下一个...")
                    continue

                if not raw:
                    if len(chain) > 1:
                        print(f"   ⚠️ [Orchestrator] 模型 '{model}' 不可用，尝试下一个...")
                    continue

                # 解析 JSON 响应（内置容错：markdown 包裹 + 单引号修复）
                parsed = self._parse_classify_json(raw)
                if parsed is not None:
                    if idx > 0:
                        print(f"   ✅ [Orchestrator] 模型 '{model}' 重试成功 (链索引 {idx})")
                    return parsed

                if len(chain) > 1:
                    print(f"   ⚠️ [Orchestrator] 模型 '{model}' 返回非 JSON，尝试下一个...")

            return None

        except json.JSONDecodeError as e:
            print(f"   ⚠️ [Orchestrator] JSON 解析失败: {e}，降级单 Worker")
            return None
        except ImportError as e:
            print(f"   ⚠️ [Orchestrator] intent_router 导入失败: {e}，降级单 Worker")
            return None
        except Exception as e:
            print(f"   ⚠️ [Orchestrator] LLM classify 异常: {e}，降级单 Worker")
            return None


# ── LanguageAdapter 辅助函数（统一执行模式）──

def _get_adapter(language: str):
    try:
        from language_adapter import get_adapter
        return get_adapter(language)
    except ImportError:
        return None


# ── 便捷函数 ──

def create_orchestrator(redis_client) -> Orchestrator:
    """创建 Orchestrator 实例的工厂函数。

    自动检查 feature toggle，如果关闭则返回的实例 analyze() 总是返回 None。

    Args:
        redis_client: Redis 客户端实例

    Returns:
        Orchestrator 实例
    """
    orch = Orchestrator(redis_client)
    if not Orchestrator.ENABLED:
        print("ℹ️ [Orchestrator] Feature toggle OFF — 所有请求走单 Worker 路径")
    return orch


def is_orchestration_enabled() -> bool:
    """检查多 Worker 编排是否启用。"""
    return Orchestrator.ENABLED