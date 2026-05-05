# -*- coding: utf-8 -*-
"""
统一的任务数据模型（TaskModel）- Python 版
所有系统中的 JSON 格式都必须遵循此规范
"""

import json
import time
from typing import Dict, Any, Optional, Tuple

class TaskModel:
    """统一的任务数据模型"""
    
    VERSION = "1.0"
    
    @staticmethod
    def create_task_submit(
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        source: str = "python-worker"
    ) -> Dict[str, Any]:
        """
        创建提交任务格式（Node → Redis → Worker）
        
        Args:
            task_id: 唯一任务标识
            task_type: 任务类型（add_numbers 等）
            payload: 业务数据
            source: 来源标识
            
        Returns:
            标准格式的任务对象
        """
        return {
            "version": TaskModel.VERSION,
            "task_id": task_id,
            "type": task_type,
            "payload": payload,
            "meta": {
                "created_at": int(time.time() * 1000),  # 毫秒时间戳
                "source": source
            }
        }
    
    @staticmethod
    def create_task_result_success(
        task_id: str,
        task_type: str,
        result: Any,
        worker_id: str = "python-worker-1",
        started_at: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建成功结果格式（Worker → Redis）
        
        Args:
            task_id: 任务 ID
            task_type: 任务类型
            result: 执行结果
            worker_id: Worker ID
            started_at: 开始时间（毫秒）
            
        Returns:
            标准格式的成功结果
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
            "meta": {
                "started_at": started_at,
                "finished_at": now,
                "worker_id": worker_id,
                "duration_ms": now - started_at
            }
        }
    
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
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        创建失败结果格式（Worker → Redis）
        
        Args:
            task_id: 任务 ID
            task_type: 任务类型
            error_message: 错误消息
            worker_id: Worker ID
            error_code: 错误代码
            error_stack: 栈信息
            retryable: 是否可重试
            started_at: 开始时间（毫秒）
            retry_count: 已重试次数
            
        Returns:
            标准格式的错误结果
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
            "meta": {
                "started_at": started_at,
                "finished_at": now,
                "worker_id": worker_id,
                "duration_ms": now - started_at,
                "retry_count": retry_count
            }
        }
    
    @staticmethod
    def create_dlq_item(
        original_task: Dict[str, Any],
        failure_record: Dict[str, Any],
        retry_count: int,
        first_failed_at: int
    ) -> Dict[str, Any]:
        """
        创建 DLQ 项目
        
        Args:
            original_task: 原始提交的任务
            failure_record: 最后一次失败记录（来自 error 字段）
            retry_count: 已重试次数
            first_failed_at: 第一次失败时间
            
        Returns:
            标准格式的 DLQ 项目
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
                "reason": "exceeded_max_retries" if failure_record.get("retryable") else "non_retryable"
            }
        }
    
    @staticmethod
    def validate_task_submit(task: Dict[str, Any]) -> Tuple[bool, list]:
        """
        验证任务提交格式
        
        Args:
            task: 要验证的任务对象
            
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        if task.get("version") != TaskModel.VERSION:
            errors.append("version must be '1.0'")
        if not task.get("task_id") or not isinstance(task["task_id"], str):
            errors.append("task_id must be a non-empty string")
        if not task.get("type") or not isinstance(task["type"], str):
            errors.append("type must be a non-empty string")
        if not isinstance(task.get("payload"), dict):
            errors.append("payload must be a dict")
        if not isinstance(task.get("meta"), dict):
            errors.append("meta must be a dict")
        if not isinstance(task.get("meta", {}).get("created_at"), int):
            errors.append("meta.created_at must be a number")
        if not task.get("meta", {}).get("source") or not isinstance(task.get("meta", {}).get("source"), str):
            errors.append("meta.source must be a non-empty string")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_task_result(result: Dict[str, Any]) -> Tuple[bool, list]:
        """
        验证任务结果格式
        
        Args:
            result: 要验证的结果对象
            
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        if result.get("version") != TaskModel.VERSION:
            errors.append("version must be '1.0'")
        if not result.get("task_id") or not isinstance(result["task_id"], str):
            errors.append("task_id must be a non-empty string")
        if not result.get("type") or not isinstance(result["type"], str):
            errors.append("type must be a non-empty string")
        if result.get("status") not in ["done", "error"]:
            errors.append('status must be "done" or "error"')
        if not isinstance(result.get("meta"), dict):
            errors.append("meta must be a dict")
        if not isinstance(result.get("meta", {}).get("started_at"), int):
            errors.append("meta.started_at must be a number")
        if not isinstance(result.get("meta", {}).get("finished_at"), int):
            errors.append("meta.finished_at must be a number")
        if not result.get("meta", {}).get("worker_id") or not isinstance(result.get("meta", {}).get("worker_id"), str):
            errors.append("meta.worker_id must be a non-empty string")
        
        # 状态特定验证
        if result.get("status") == "done":
            if result.get("result") is None:
                errors.append("result must not be None when status is 'done'")
            if result.get("error") is not None:
                errors.append("error must be None when status is 'done'")
        elif result.get("status") == "error":
            if result.get("result") is not None:
                errors.append("result must be None when status is 'error'")
            if not isinstance(result.get("error"), dict):
                errors.append("error must be a dict when status is 'error'")
        
        return len(errors) == 0, errors


def pretty_print(obj: Dict[str, Any]) -> str:
    """
    结构化打印 JSON
    
    Args:
        obj: 要打印的对象
        
    Returns:
        格式化的 JSON 字符串
    """
    return json.dumps(obj, indent=2, ensure_ascii=False)
