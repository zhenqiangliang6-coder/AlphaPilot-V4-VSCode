# -*- coding: utf-8 -*-
# pipeline_executor._checkpoint — Pipeline Checkpoint 序列化/恢复
# ---------------------------------------------------------
# 支持长时间任务的断点续跑。
# 检查点存储为 JSON 可序列化对象，可持久化到 Redis 或文件。
# ---------------------------------------------------------

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .contract import PipelineState


# ============================================================
# PipelineCheckpoint — 可序列化的执行检查点
# ============================================================

@dataclass
class PipelineCheckpoint:
    """管道执行过程中的一个快照点。

    检查点在每阶段开始前和结束后自动创建。
    包含足够的上下文信息用于从断点恢复执行。

    序列化格式（JSON）::

        {
            "pipeline_id": "task-abc-123",
            "state": "running",
            "current_stage": 1,
            "current_step": 2,
            "stage_results": ["completed", "running", "pending"],
            "completed_stages": ["preparatory"],
            "timestamp": 1761552000.0
        }
    """
    pipeline_id: str = ""
    state: str = PipelineState.PENDING.value
    current_stage: int = -1
    current_step: int = -1
    stage_results: List[str] = field(default_factory=list)
    completed_stages: List[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    # ========================================================
    # 序列化
    # ========================================================

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "state": self.state,
            "current_stage": self.current_stage,
            "current_step": self.current_step,
            "stage_results": list(self.stage_results),
            "completed_stages": list(self.completed_stages),
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    # ========================================================
    # 反序列化
    # ========================================================

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineCheckpoint":
        return cls(
            pipeline_id=data.get("pipeline_id", ""),
            state=data.get("state", PipelineState.PENDING.value),
            current_stage=data.get("current_stage", -1),
            current_step=data.get("current_step", -1),
            stage_results=data.get("stage_results", []),
            completed_stages=data.get("completed_stages", []),
            timestamp=data.get("timestamp", 0.0),
        )

    @classmethod
    def from_json(cls, text: str) -> Optional["PipelineCheckpoint"]:
        try:
            return cls.from_dict(json.loads(text))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    # ========================================================
    # 查询
    # ========================================================

    @property
    def is_terminal(self) -> bool:
        return self.state in {s.value for s in PipelineState.terminal_states()}

    @property
    def is_resumable(self) -> bool:
        """可以从中断点恢复执行。"""
        return (
            not self.is_terminal
            and self.current_stage >= 0
            and bool(self.completed_stages)
        )

    @property
    def next_stage_index(self) -> int:
        """下一个需要执行的阶段索引。"""
        if self.current_stage < 0:
            return 0
        return self.current_stage + 1

    @property
    def next_step_index(self) -> int:
        """当前阶段中下一个需要执行的步骤索引。"""
        return max(0, self.current_step + 1)

    # ========================================================
    # 更新
    # ========================================================

    def mark_stage_completed(self, stage_name: str, stage_index: int):
        self.completed_stages.append(stage_name)
        if stage_index < len(self.stage_results):
            self.stage_results[stage_index] = PipelineState.COMPLETED.value
        self.current_stage = stage_index
        self.current_step = -1
        self.timestamp = time.time()

    def mark_stage_failed(self, stage_index: int):
        if stage_index < len(self.stage_results):
            self.stage_results[stage_index] = PipelineState.FAILED.value
        self.state = PipelineState.FAILED.value
        self.timestamp = time.time()

    def mark_step_progress(self, stage_index: int, step_index: int):
        self.current_stage = stage_index
        self.current_step = step_index
        self.timestamp = time.time()

    def mark_completed(self):
        self.state = PipelineState.COMPLETED.value
        self.timestamp = time.time()


# ============================================================
# CheckpointStore — 检查点存储抽象
# ============================================================

class CheckpointStore:
    """检查点存储接口。

    当前实现为内存字典（进程内），未来可扩展为 Redis 持久化。
    """

    def __init__(self):
        self._store: Dict[str, PipelineCheckpoint] = {}

    def save(self, checkpoint: PipelineCheckpoint):
        self._store[checkpoint.pipeline_id] = checkpoint

    def load(self, pipeline_id: str) -> Optional[PipelineCheckpoint]:
        return self._store.get(pipeline_id)

    def delete(self, pipeline_id: str):
        self._store.pop(pipeline_id, None)

    def has(self, pipeline_id: str) -> bool:
        return pipeline_id in self._store

    def clear(self):
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# ============================================================
# 全局检查点存储（进程级单例）
# ============================================================

_checkpoint_store: Optional[CheckpointStore] = None


def get_checkpoint_store() -> CheckpointStore:
    global _checkpoint_store
    if _checkpoint_store is None:
        _checkpoint_store = CheckpointStore()
    return _checkpoint_store