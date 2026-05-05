# -*- coding: utf-8 -*-
"""
TaskModel v2 - 智能体执行引擎版（Python）
------------------------------------------------
这是你未来平台级能力的核心数据结构。

设计目标：
1. 完全兼容 v1（旧 Worker / Node API 不会崩）
2. 新增智能体执行引擎所需的结构（steps / events / context）
3. 支持任务树、事件流、多步骤执行、工具调用、子任务
4. Worker 可以逐步升级，不需要一次性改完
5. Node API 只需要透传，不需要理解智能体逻辑
"""

import json
import time
from typing import Dict, Any, Optional, Tuple, List


class TaskModel:
    """统一的任务数据模型（v2）"""

    VERSION = "2.0"

    # ------------------------------------------------------------
    # 任务提交（Node → Redis → Worker）
    # ------------------------------------------------------------
    @staticmethod
    def create_task_submit(
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        source: str = "python-worker"
    ) -> Dict[str, Any]:
        """
        创建提交任务格式（v2）
        新增字段：
        - steps: 智能体执行步骤（任务树）
        - events: 事件流（token、工具调用、状态变化）
        - context: 智能体上下文（记忆、中间结果、子任务）
        """

        now = int(time.time() * 1000)

        return {
            "version": TaskModel.VERSION,
            "task_id": task_id,
            "type": task_type,
            "status": "pending",  # v2 新增：任务状态机
            "payload": payload,

            # 智能体上下文（可选字段，旧系统不会使用）
            "context": {
                "memory": {},
                "intermediate_results": [],
                "tool_outputs": [],
                "subtasks": []
            },

            # 智能体执行步骤（任务树）
            "steps": [],

            # 事件流（token、step_start、tool_call 等）
            "events": [],

            "meta": {
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "worker_id": None,
                "retry_count": 0,
                "source": source
            }
        }

    # ------------------------------------------------------------
    # 成功结果（Worker → Redis）
    # ------------------------------------------------------------
    @staticmethod
    def create_task_result_success(
        task_id: str,
        task_type: str,
        result: Any,
        worker_id: str = "python-worker-1",
        started_at: Optional[int] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建成功结果（v2）
        新增字段：
        - steps
        - events
        - context
        """

        now = int(time.time() * 1000)
        if started_at is None:
            started_at = now

        return {
            "version": TaskModel.VERSION,
            "task_id": task_id,
            "type": task_type,
            "status": "done",
            "result": result,
            "error": None,

            # v2 新增字段（Worker 可逐步填充）
            "steps": steps or [],
            "events": events or [],
            "context": context or {},

            "meta": {
                "started_at": started_at,
                "finished_at": now,
                "worker_id": worker_id,
                "duration_ms": now - started_at
            }
        }

    # ------------------------------------------------------------
    # 错误结果（Worker → Redis）
    # ------------------------------------------------------------
    @staticmethod
    def create_task_result_error(
        task_id: str,
        task_type: str,
        error_message: str,
        worker_id: str = "python-worker-1",
        error_code: Optional[str] = None,
        error_stack: Optional[str] = None,
        retryable: bool = True,
        started_at: Optional[int] = None,
        retry_count: int = 0,
        steps: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建失败结果（v2）
        """

        now = int(time.time() * 1000)
        if started_at is None:
            started_at = now

        return {
            "version": TaskModel.VERSION,
            "task_id": task_id,
            "type": task_type,
            "status": "error",
            "result": None,

            "error": {
                "message": error_message,
                "code": error_code or "UNKNOWN_ERROR",
                "stack": error_stack,
                "retryable": retryable
            },

            # v2 新增字段
            "steps": steps or [],
            "events": events or [],
            "context": context or {},

            "meta": {
                "started_at": started_at,
                "finished_at": now,
                "worker_id": worker_id,
                "duration_ms": now - started_at,
                "retry_count": retry_count
            }
        }

    # ------------------------------------------------------------
    # DLQ（死信队列）
    # ------------------------------------------------------------
    @staticmethod
    def create_dlq_item(
        original_task: Dict[str, Any],
        failure_record: Dict[str, Any],
        retry_count: int,
        first_failed_at: int
    ) -> Dict[str, Any]:
        """
        创建 DLQ 项目（兼容 v1/v2）
        """

        now = int(time.time() * 1000)

        return {
            "version": TaskModel.VERSION,
            "task_id": original_task["task_id"],
            "original_task": original_task,
            "failure_record": failure_record,
            "retry_count": retry_count,
            "first_failed_at": first_failed_at,
            "last_failed_at": now,
            "meta": {
                "created_at": now,
                "reason": "exceeded_max_retries"
                if failure_record.get("retryable")
                else "non_retryable"
            }
        }

    # ------------------------------------------------------------
    # JSON 美化打印
    # ------------------------------------------------------------
    @staticmethod
    def pretty_print(obj: Dict[str, Any]) -> str:
        """结构化打印 JSON"""
        return json.dumps(obj, indent=2, ensure_ascii=False)
