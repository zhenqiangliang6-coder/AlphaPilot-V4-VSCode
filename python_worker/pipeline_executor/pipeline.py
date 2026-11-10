# -*- coding: utf-8 -*-
# pipeline_executor._pipeline — PipelineExecutor 主调度器
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相 — 全部在 Worker 进程内运行，不依赖外部编排
# ✅ 协议 = 宪法 — 通过现有 execute_step + stream_chunk 与 Extension 交互
#
# 职责：
#   1. 按 PipelineContract 定义的阶段和步骤顺序调度
#   2. 执行 Gate 准入检查
#   3. 每个步骤通过现有的 step_executor.execute_step 执行
#   4. 阶段完成后调用 on_complete 回调提取 Artifact
#   5. 检查点自动记录（每阶段前后）
#   6. 失败时自动重试（按阶段 retry 配置）
# ---------------------------------------------------------

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contract import PipelineContract, PipelineStage, PipelineState, PlanArtifact, CodeArtifact, TestArtifact, FixArtifact, ChangelogArtifact
from .checkpoint import PipelineCheckpoint, get_checkpoint_store

# ⚠️ 延迟导入：避免循环依赖。execute_step 在 Worker 初始化后才可用。
_execute_step_fn: Optional[Callable] = None


def set_execute_step(fn: Callable):
    """注入 execute_step 函数引用。

    必须在 Worker 初始化时调用一次，在 execute_task 之前。
    这是解耦的设计：PipelineExecutor 不直接导入 Worker 内部模块。
    """
    global _execute_step_fn
    _execute_step_fn = fn


# ============================================================
# PipelineResult — 管道执行结果
# ============================================================

class PipelineResult:
    """管道执行完毕后的结构化结果。

    字段:
        success: 管道整体是否成功（所有 required 阶段通过）
        state: 最终管道状态
        stages_completed: 成功完成的阶段名列表
        stages_failed: 失败的阶段名列表
        artifacts: 提取的类型化制品
        total_time_s: 总耗时（秒）
        error: 如果失败，这里是最新的错误信息
    """

    def __init__(self):
        self.success: bool = False
        self.state: PipelineState = PipelineState.PENDING
        self.stages_completed: List[str] = []
        self.stages_failed: List[str] = []
        self.artifacts: Dict[str, Any] = {}
        self.total_time_s: float = 0.0
        self.error: str = ""


# ============================================================
# PipelineExecutor — 管道执行器
# ============================================================

class PipelineExecutor:
    """通用多阶段管道执行器。

    用法::

        contract = make_write_code_pipeline()
        executor = PipelineExecutor(contract, task_id="task-123")
        result = executor.execute(context)

    或从检查点恢复::

        executor = PipelineExecutor.restore("task-123")
        if executor:
            result = executor.execute(context)
    """

    def __init__(
        self,
        contract: PipelineContract,
        task_id: str = "",
        events: Optional[List[dict]] = None,
        on_stage_start: Optional[Callable] = None,
        on_stage_end: Optional[Callable] = None,
        on_step_start: Optional[Callable] = None,
        on_step_end: Optional[Callable] = None,
    ):
        self.contract = contract
        self.task_id = task_id
        self.events = events or []
        self.result = PipelineResult()

        # 可选生命周期钩子（stream_chunk 等）
        self.on_stage_start = on_stage_start
        self.on_stage_end = on_stage_end
        self.on_step_start = on_step_start
        self.on_step_end = on_step_end

        # 检查点存储
        self.checkpoint_store = get_checkpoint_store()

    # ========================================================
    # 主执行入口
    # ========================================================

    def execute(self, context: dict) -> PipelineResult:
        """执行完整的管道。

        返回 PipelineResult，同时 context 被就地修改（累积 intermediate_results 等）。
        """
        t0 = time.time()

        if self.contract.is_terminal():
            return self._already_terminal()

        self.contract.state = PipelineState.RUNNING
        self._save_checkpoint()

        while self.contract.advance_stage():
            stage = self.contract.current_stage
            if stage is None:
                break

            stage_name = stage.name
            success = False

            for attempt in range(stage.retry + 1):
                if attempt > 0:
                    print(f"\n🔄 [Pipeline] 阶段 '{stage_name}' 第 {attempt + 1}/{stage.retry + 1} 次重试")

                success = self._execute_stage(stage, context)
                if success:
                    break

            if success:
                self.contract.mark_stage_result(PipelineState.COMPLETED)
                self.result.stages_completed.append(stage_name)
                self._save_checkpoint()
            else:
                self.contract.mark_stage_result(PipelineState.FAILED)
                self.result.stages_failed.append(stage_name)
                self._save_checkpoint()

                if stage.required:
                    self.contract.state = PipelineState.FAILED
                    self.result.error = f"阶段 '{stage_name}' 失败（required）"
                    break
                else:
                    print(f"   ⚠️ [Pipeline] 非阻塞阶段 '{stage_name}' 失败，继续执行")
                    continue

        else:
            # while 正常结束 = 所有阶段完成
            self.contract.state = PipelineState.COMPLETED

        self._finalize(context)
        self.result.total_time_s = time.time() - t0
        return self.result

    # ========================================================
    # 单阶段执行
    # ========================================================

    def _execute_stage(self, stage: PipelineStage, context: dict) -> bool:
        """执行单个阶段内的全部步骤。"""
        stage_name = stage.name

        # Gate 检查
        if not stage.can_enter(context):
            print(f"\n🚫 [Pipeline] Gate 拒绝进入阶段 '{stage_name}'")
            return False

        self._hook_stage_start(stage_name)

        self.contract.current_step_index = -1
        while self.contract.advance_step():
            step_type = self.contract.current_step_type()
            if step_type is None:
                continue

            self._hook_step_start(stage_name, step_type)
            ok = self._execute_single_step(step_type, context)
            self._hook_step_end(stage_name, step_type, ok)

            if not ok:
                # 当前阶段内步骤失败
                self._hook_stage_end(stage_name, False)
                return False

            self._save_checkpoint()

        # 阶段完成回调和 Artifact 提取
        context = stage.complete(context)

        # 从 _artifacts 提取到 result
        artifacts = context.get("_artifacts", {})
        self.result.artifacts.update(artifacts)

        self._hook_stage_end(stage_name, True)
        return True

    # ========================================================
    # 单步骤执行
    # ========================================================

    def _execute_single_step(self, step_type: str, context: dict) -> bool:
        """调用现有的 step_executor.execute_step 执行单个步骤。"""
        global _execute_step_fn

        if _execute_step_fn is None:
            print(f"\n⚠️ [Pipeline] execute_step 未注入，无法执行步骤 '{step_type}'")
            return False

        step = {
            "type": step_type,
            "status": "running",
            "output": {},
            "input": {
                "prompt": context.get("meta", {}).get("user_request", ""),
            },
        }

        try:
            _execute_step_fn(self.task_id, step, self.events, context)
            return True
        except Exception as e:
            step["status"] = "failed"
            step["output"] = {"text": str(e)}
            print(f"\n❌ [Pipeline] 步骤 '{step_type}' 执行异常: {e}")
            return False

    # ========================================================
    # 收尾
    # ========================================================

    def _finalize(self, context: dict):
        """管道执行完毕的收尾工作。"""
        if self.contract.state == PipelineState.COMPLETED:
            self.result.success = True
            self.result.state = PipelineState.COMPLETED
        else:
            self.result.state = self.contract.state

        self._save_checkpoint()
        self._log_result()

    def _log_result(self):
        """打印管道执行摘要。"""
        print(f"\n{'=' * 60}")
        print(f"Pipeline 执行{'✅ 成功' if self.result.success else '❌ 失败'}")
        print(f"  耗时: {self.result.total_time_s:.1f}s")
        print(f"  完成阶段: {self.result.stages_completed}")
        if self.result.stages_failed:
            print(f"  失败阶段: {self.result.stages_failed}")
        if self.result.artifacts:
            print(f"  制品: {list(self.result.artifacts.keys())}")
        if self.result.error:
            print(f"  错误: {self.result.error}")
        print(f"{'=' * 60}\n")

    # ========================================================
    # 检查点
    # ========================================================

    def _save_checkpoint(self):
        checkpoint = PipelineCheckpoint(
            pipeline_id=self.task_id,
            state=self.contract.state.value,
            current_stage=self.contract.current_stage_index,
            current_step=self.contract.current_step_index,
            stage_results=list(self.contract.stage_results),
            completed_stages=list(self.result.stages_completed),
        )
        self.checkpoint_store.save(checkpoint)

    # ========================================================
    # 恢复
    # ========================================================

    @classmethod
    def restore(cls, task_id: str) -> Optional["PipelineExecutor"]:
        """从检查点恢复执行器。"""
        store = get_checkpoint_store()
        checkpoint = store.load(task_id)
        if checkpoint is None:
            return None
        if checkpoint.is_terminal:
            return None

        contract = PipelineContract(
            stage_results=checkpoint.stage_results,
            state=PipelineState(checkpoint.state),
        )
        contract.current_stage_index = checkpoint.next_stage_index
        contract.current_step_index = checkpoint.next_step_index

        executor = cls(contract, task_id=task_id)
        executor.result.stages_completed = list(checkpoint.completed_stages)
        return executor

    # ========================================================
    # 钩子
    # ========================================================

    def _hook_stage_start(self, stage_name: str):
        if self.on_stage_start:
            try:
                self.on_stage_start(stage_name)
            except Exception:
                pass

    def _hook_stage_end(self, stage_name: str, success: bool):
        if self.on_stage_end:
            try:
                self.on_stage_end(stage_name, success)
            except Exception:
                pass

    def _hook_step_start(self, stage_name: str, step_type: str):
        if self.on_step_start:
            try:
                self.on_step_start(stage_name, step_type)
            except Exception:
                pass

    def _hook_step_end(self, stage_name: str, step_type: str, success: bool):
        if self.on_step_end:
            try:
                self.on_step_end(stage_name, step_type, success)
            except Exception:
                pass

    def _already_terminal(self) -> PipelineResult:
        self.result.state = self.contract.state
        self.result.error = f"管道已处于终止状态: {self.contract.state.value}"
        return self.result