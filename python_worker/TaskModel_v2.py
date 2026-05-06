# -*- coding: utf-8 -*-
"""
TaskModel v2 - 智能体执行引擎版（Python）
------------------------------------------------
这是你未来平台级能力的核心数据结构。

设计目标：
1. 完全兼容 v1（旧 Worker / Node API 不会崩）
2. 新增智能体执行引擎所需的结构（steps / events / context）
3. 支持任务树、事件流、多步骤执行、工具调用、子任务
4. ⭐ 新增：模型无关的流式协议支持（对标Cursor/Claude Code）
5. Worker 可以逐步升级，不需要一次性改完
6. Node API 只需要透传，不需要理解智能体逻辑
"""

import json
import time
from typing import Dict, Any, Optional, Tuple, List


class TaskModel:
    """统一的任务数据模型（v2）"""

    VERSION = "2.0"

    # ------------------------------------------------------------
    # ⭐ 新增：支持的模型列表（可扩展）
    # ------------------------------------------------------------
    SUPPORTED_MODELS = {
        "qwen": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen2.5"],
        "deepseek": ["deepseek-chat", "deepseek-coder"],
        "doubao": ["doubao-pro", "doubao-lite"],
        "gpt": ["gpt-4", "gpt-4o", "gpt-5"],
        "claude": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
        "gemini": ["gemini-pro", "gemini-ultra"]
    }

    # ------------------------------------------------------------
    # ⭐ 新增：生成类任务的阶段定义
    # ------------------------------------------------------------
    GENERATION_PHASES = [
        "analyze",   # 分析需求
        "plan",      # 制定计划
        "write",     # 编写内容
        "refine",    # 优化改进
        "test"       # 测试验证（可选）
    ]

    # ------------------------------------------------------------
    # ⭐ 新增：流式通道类型
    # ------------------------------------------------------------
    STREAM_CHANNELS = {
        "reasoning": "思考过程（AI的内部推理）",
        "content": "最终产出（代码/文档/诗歌等）"
    }

    # ------------------------------------------------------------
    # 任务提交（Node → Redis → Worker）
    # ------------------------------------------------------------
    @staticmethod
    def create_task_submit(
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        source: str = "python-worker",
        model: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        创建提交任务格式（v2）
        
        ⭐ 新增参数：
        - model: 模型名称（如 "qwen2.5", "gpt-5"），放在 meta.model
        - stream: 是否启用流式输出，放在 meta.stream
        
        设计原则：
        - task_type 统一为 "task.generate"（模型无关）
        - 模型选择通过 meta.model 指定
        - 流式控制通过 meta.stream 显式声明
        
        示例：
        {
            "type": "task.generate",
            "payload": {"prompt": "写一个快速排序函数"},
            "meta": {
                "model": "qwen2.5",
                "stream": true
            }
        }
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
                "source": source,
                
                # ⭐ 新增：模型选择和流式控制
                "model": model or "qwen-turbo",  # 默认模型
                "stream": stream  # 是否启用流式
            }
        }

    # ------------------------------------------------------------
    # ⭐ 新增：验证模型名称
    # ------------------------------------------------------------
    @staticmethod
    def validate_model(model_name: str) -> Tuple[bool, str]:
        """
        验证模型名称是否合法
        
        返回：
        - (True, ""): 模型合法
        - (False, error_message): 模型不合法
        """
        if not model_name:
            return False, "模型名称不能为空"
        
        # 检查是否在所有支持的模型列表中
        for vendor, models in TaskModel.SUPPORTED_MODELS.items():
            if model_name in models:
                return True, ""
        
        # 允许自定义模型（未来扩展）
        return True, ""  # 暂时放宽限制

    # ------------------------------------------------------------
    # ⭐ 新增：从任务中提取模型信息
    # ------------------------------------------------------------
    @staticmethod
    def extract_model_info(task: Dict[str, Any]) -> Dict[str, Any]:
        """
        从任务中提取模型和流式配置
        
        返回：
        {
            "model": "qwen2.5",
            "vendor": "qwen",
            "stream": true,
            "phase": "write"  # 当前阶段（如果有）
        }
        """
        meta = task.get("meta", {})
        model = meta.get("model", "qwen-turbo")
        stream = meta.get("stream", False)
        
        # 提取厂商前缀
        vendor = model.split("-")[0] if "-" in model else model
        
        return {
            "model": model,
            "vendor": vendor,
            "stream": stream,
            "phase": None  # 由Worker在执行时设置
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
    # ⭐ 新增：创建流式chunk事件（模型无关）
    # ------------------------------------------------------------
    @staticmethod
    def create_stream_chunk(
        task_id: str,
        phase: str,
        channel: str,
        content: str,
        token_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建流式chunk事件（符合TaskModel v2）
        
        参数：
        - task_id: 任务ID
        - phase: 当前阶段 (analyze/plan/write/refine/test)
        - channel: 通道类型 (reasoning/content)
        - content: chunk内容
        - token_index: token索引（可选，用于调试）
        
        返回：
        {
            "event": "stream_chunk",
            "task_id": "...",
            "phase": "write",
            "channel": "content",
            "content": "def quick_sort",
            "timestamp": 1234567890
        }
        """
        return {
            "event": "stream_chunk",
            "task_id": task_id,
            "phase": phase,
            "channel": channel,
            "content": content,
            "timestamp": int(time.time() * 1000),
            "token_index": token_index
        }

    # ------------------------------------------------------------
    # ⭐ 新增：创建步骤开始事件
    # ------------------------------------------------------------
    @staticmethod
    def create_step_event(
        task_id: str,
        step_id: str,
        phase: str,
        status: str = "started"
    ) -> Dict[str, Any]:
        """
        创建步骤事件
        
        参数：
        - status: "started" | "completed" | "failed"
        """
        return {
            "event": f"step_{status}",
            "task_id": task_id,
            "step_id": step_id,
            "phase": phase,
            "timestamp": int(time.time() * 1000)
        }

    # ------------------------------------------------------------
    # JSON 美化打印
    # ------------------------------------------------------------
    @staticmethod
    def pretty_print(obj: Dict[str, Any]) -> str:
        """结构化打印 JSON"""
        return json.dumps(obj, indent=2, ensure_ascii=False)
