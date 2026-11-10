# -*- coding: utf-8 -*-
# pipeline_executor._contract — Pipeline 核心契约与制品定义
# ---------------------------------------------------------
# 本模块是 Pipeline Executor 的类型地基，零外部依赖。
# 所有阶段间数据传递必须通过明确的 Artifact 类型，不使用裸 dict。
# ---------------------------------------------------------

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ============================================================
# PipelineState — 管道生命周期状态机
# ============================================================

class PipelineState(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_states(cls) -> set:
        """终止状态：在这些状态上不会再调度任何阶段。"""
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}


# ============================================================
# Stage Artifacts — 类型化阶段间制品
# ============================================================

@dataclass
class PlanArtifact:
    """分析/计划阶段的产出 — 供 write 步骤消费。"""
    text: str = ""
    files_to_create: List[str] = field(default_factory=list)
    files_to_modify: List[str] = field(default_factory=list)
    architecture_notes: str = ""
    estimated_complexity: str = "medium"   # low / medium / high


@dataclass
class CodeArtifact:
    """代码生成/修改阶段的产出 — 供 test / doc 步骤消费。"""
    file_ops: List[Dict[str, Any]] = field(default_factory=list)
    entry_point: str = ""                  # 生成代码的主要入口文件
    language: str = ""                     # 语言标识（python / javascript / ...）


@dataclass
class TestArtifact:
    """测试阶段的产出 — 供 fix 步骤消费。"""
    passed: int = 0
    failed: int = 0
    total: int = 0
    output_text: str = ""
    exec_success: bool = False
    failures_detail: List[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0

    @property
    def summary(self) -> str:
        return f"{self.passed}/{self.total} PASSED"


@dataclass
class FixArtifact:
    """修复阶段的产出 — 供 retest 步骤消费。"""
    files_fixed: List[str] = field(default_factory=list)
    fix_description: str = ""
    success: bool = False


@dataclass
class ChangelogArtifact:
    """changelog 更新产出。"""
    updated: bool = False
    entry: str = ""
    file: str = ""


# ============================================================
# PipelineStage — 单个管段阶段
# ============================================================

@dataclass
class PipelineStage:
    """管道中的一个阶段（3~5 个步骤的序列）。

    每个阶段有自己的 Gate（准入条件）和 OnComplete（后处理回调），
    以及独立的超时和重试策略。

    字段:
        name: 阶段唯一标识（preparatory / generative / post）
        steps: 该阶段的步骤类型列表（如 ["analyze", "workspace", "plan"]）
        gate: 准入条件函数 context → bool
        on_complete: 完成回调 context → context（常用于提取 Artifact）
        retry: 本阶段最大重试次数（0 = 不重试）
        timeout_s: 阶段超时秒数（0 = 不限时）
        required: 是否必须成功才能进入下一阶段
    """
    name: str
    steps: List[str]
    gate: Optional[Callable[[dict], bool]] = None
    on_complete: Optional[Callable[[dict], dict]] = None
    retry: int = 0
    timeout_s: int = 0
    required: bool = True

    def can_enter(self, context: dict) -> bool:
        """检查当前上下文是否满足本阶段的准入条件。"""
        if self.gate is None:
            return True
        try:
            return self.gate(context)
        except Exception:
            return False

    def complete(self, context: dict) -> dict:
        """执行阶段完成回调，返回（可能修改后的）context。"""
        if self.on_complete is None:
            return context
        try:
            return self.on_complete(context)
        except Exception:
            return context


# ============================================================
# PipelineContract — 完整管道协议
# ============================================================

@dataclass
class PipelineContract:
    """一个完整的管道执行契约。

    字段:
        stages: 有序阶段列表
        artifacts: 阶段间共享的类型化制品（key → Artifact 实例）
        state: 管道当前状态
        current_stage_index: 当前正在执行的阶段索引（-1 为未开始）
        current_step_index: 当前阶段内的步骤索引（-1 为未开始）
        stage_results: 各阶段的 ["PENDING"/"RUNNING"/"COMPLETED"/"FAILED"] 状态
    """
    stages: List[PipelineStage] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    state: PipelineState = PipelineState.PENDING
    current_stage_index: int = -1
    current_step_index: int = -1
    stage_results: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.stage_results:
            self.stage_results = [PipelineState.PENDING.value] * len(self.stages)

    @property
    def current_stage(self) -> Optional[PipelineStage]:
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def advance_stage(self) -> bool:
        """移动到下一阶段。

        返回 True 表示有更多阶段待执行，False 表示管道完成。
        """
        self.current_stage_index += 1
        self.current_step_index = -1
        return self.current_stage_index < len(self.stages)

    def advance_step(self) -> bool:
        """移动到当前阶段的下一个步骤。

        返回 True 表示当前阶段有更多步骤，False 表示该阶段完成。
        """
        stage = self.current_stage
        if stage is None:
            return False
        self.current_step_index += 1
        return self.current_step_index < len(stage.steps)

    def current_step_type(self) -> Optional[str]:
        """获取当前步骤的类型字符串。"""
        stage = self.current_stage
        if stage is None or self.current_step_index < 0:
            return None
        if self.current_step_index < len(stage.steps):
            return stage.steps[self.current_step_index]
        return None

    def mark_stage_result(self, result: PipelineState):
        """标记当前阶段的结果。"""
        if 0 <= self.current_stage_index < len(self.stage_results):
            self.stage_results[self.current_stage_index] = result.value

    def is_terminal(self) -> bool:
        return self.state in PipelineState.terminal_states()

    def to_checkpoint_snapshot(self) -> dict:
        """提取可序列化的检查点快照。"""
        return {
            "state": self.state.value,
            "current_stage_index": self.current_stage_index,
            "current_step_index": self.current_step_index,
            "stage_results": list(self.stage_results),
        }


# ============================================================
# 工厂函数 — 为常见意图构造管道
# ============================================================

def make_write_code_pipeline() -> PipelineContract:
    """构造 write_code 意图的标准三阶段管道。

    Preparatory: analyze → workspace → plan
    Generative:  write → refine → test → fix
    PostProcess: changelog → doc → docstring → respond
    """
    return PipelineContract(stages=[
        # 阶段 1: Preparatory — 理解需求 + 读取代码库 + 制定方案
        PipelineStage(
            name="preparatory",
            steps=["analyze", "workspace", "plan"],
            retry=0,
            timeout_s=120,
            required=True,
            on_complete=_extract_plan_artifact,
        ),
        # 阶段 2: Generative — 写代码 + 测试 + 修复循环
        PipelineStage(
            name="generative",
            steps=["write", "refine", "test", "fix"],
            retry=1,
            timeout_s=300,
            required=True,
            on_complete=_extract_code_and_test_artifacts,
        ),
        # 阶段 3: PostProcess — 后处理
        PipelineStage(
            name="post",
            steps=["changelog", "doc", "docstring", "respond"],
            retry=0,
            timeout_s=120,
            required=False,
            on_complete=_extract_changelog_artifact,
        ),
    ])


def make_execute_operation_pipeline() -> PipelineContract:
    """构造 execute_operation 意图的单阶段管道。"""
    return PipelineContract(stages=[
        PipelineStage(
            name="operate",
            steps=["operate"],
            retry=0,
            timeout_s=300,
            required=True,
        ),
    ])


# ============================================================
# OnComplete 回调 — 从 context 提取 Artifact
# ============================================================

def _extract_plan_artifact(context: dict) -> dict:
    """从 context 的 intermediate_results 提取 PlanArtifact。"""
    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") == "plan":
            context.setdefault("_artifacts", {})["plan"] = PlanArtifact(
                text=result.get("text", ""),
                estimated_complexity=result.get("complexity", "medium"),
            )
            break
    return context


def _extract_code_and_test_artifacts(context: dict) -> dict:
    """从 context 提取 CodeArtifact 和 TestArtifact。"""
    file_ops = context.get("final_file_ops", [])
    if file_ops:
        context.setdefault("_artifacts", {})["code"] = CodeArtifact(
            file_ops=file_ops,
            language=_infer_language(file_ops),
        )

    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") == "test":
            text = result.get("text", "")
            passed, failed = _parse_test_counts(text)
            context.setdefault("_artifacts", {})["test"] = TestArtifact(
                passed=passed,
                failed=failed,
                total=passed + failed,
                output_text=text,
                exec_success=(failed == 0),
            )
            break
    return context


def _extract_changelog_artifact(context: dict) -> dict:
    """从 context 提取 ChangelogArtifact。"""
    for result in reversed(context.get("intermediate_results", [])):
        if result.get("type") == "changelog":
            context.setdefault("_artifacts", {})["changelog"] = ChangelogArtifact(
                updated=result.get("updated", False),
                entry=result.get("entry", ""),
                file=result.get("file", ""),
            )
            break
    return context


# ============================================================
# 辅助函数
# ============================================================

def _infer_language(file_ops: list) -> str:
    """从文件操作列表推断编程语言。"""
    exts = {op.get("path", "").rsplit(".", 1)[-1].lower() for op in file_ops if "." in op.get("path", "")}
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "rs": "rust", "go": "go", "java": "java", "cpp": "c++",
        "c": "c", "rb": "ruby", "php": "php", "swift": "swift",
        "kt": "kotlin", "cs": "csharp", "sh": "shell", "toml": "toml",
        "yaml": "yaml", "yml": "yaml", "json": "json", "md": "markdown",
    }
    for ext, lang in lang_map.items():
        if ext in exts:
            return lang
    return ""


def _parse_test_counts(text: str) -> tuple:
    """从测试输出文本解析 passed/failed 计数。"""
    import re
    passed = 0
    failed = 0
    for m in re.findall(r"(\d+)\s*(?:PASSED|passed)\b", text):
        passed += int(m)
    for m in re.findall(r"(\d+)\s*(?:FAILED|failed)\b", text):
        failed += int(m)
    return passed, failed