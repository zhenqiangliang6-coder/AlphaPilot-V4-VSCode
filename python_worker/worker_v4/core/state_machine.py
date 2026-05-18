# python_worker/worker_v4/core/state_machine.py

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time


class StepStatus(Enum):
    """步骤状态机的所有状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class StepState:
    """记录单个步骤的状态信息（可追踪、可恢复）"""
    step_id: str
    step_type: str
    status: StepStatus = StepStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_running(self):
        self.status = StepStatus.RUNNING
        self.started_at = time.time()

    def mark_success(self, metadata: Dict[str, Any] = None):
        self.status = StepStatus.SUCCESS
        self.finished_at = time.time()
        if metadata:
            self.metadata.update(metadata)

    def mark_failed(self, error_message: str):
        self.status = StepStatus.FAILED
        self.error_message = error_message
        self.finished_at = time.time()

    def mark_retrying(self):
        self.status = StepStatus.RETRYING
        self.retries += 1

    def mark_timeout(self):
        self.status = StepStatus.TIMEOUT
        self.finished_at = time.time()

    def is_finished(self) -> bool:
        return self.status in {
            StepStatus.SUCCESS,
            StepStatus.FAILED,
            StepStatus.TIMEOUT,
            StepStatus.CANCELLED,
        }


class StepStateMachine:
    """Worker V4 的状态机核心：管理步骤生命周期"""

    def __init__(self):
        self.steps: Dict[str, StepState] = {}

    def create_step(self, step_id: str, step_type: str) -> StepState:
        step = StepState(step_id=step_id, step_type=step_type)
        self.steps[step_id] = step
        return step

    def get_step(self, step_id: str) -> StepState:
        return self.steps[step_id]

    def start_step(self, step_id: str):
        step = self.get_step(step_id)
        step.mark_running()
        return step

    def finish_step(self, step_id: str, metadata: Dict[str, Any] = None):
        step = self.get_step(step_id)
        step.mark_success(metadata)
        return step

    def fail_step(self, step_id: str, error_message: str):
        step = self.get_step(step_id)
        step.mark_failed(error_message)
        return step

    def retry_step(self, step_id: str):
        step = self.get_step(step_id)
        step.mark_retrying()
        return step

    def timeout_step(self, step_id: str):
        step = self.get_step(step_id)
        step.mark_timeout()
        return step

    def is_step_finished(self, step_id: str) -> bool:
        return self.get_step(step_id).is_finished()
