from typing import Any, Dict


PROTOCOL_VERSION = "1.0"


class TaskProtocolError(ValueError):
    pass


def validate_worker_task(task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        raise TaskProtocolError("Task envelope must be an object")

    protocol_version = task.get("protocol_version")
    if protocol_version is not None and protocol_version != PROTOCOL_VERSION:
        raise TaskProtocolError(
            f"Unsupported task protocol version: {protocol_version}"
        )

    for field in ("task_id", "payload"):
        if field not in task:
            raise TaskProtocolError(f"Task envelope is missing required field: {field}")

    if not isinstance(task["task_id"], str) or not task["task_id"].strip():
        raise TaskProtocolError("task_id must be a non-empty string")
    if not isinstance(task["payload"], dict):
        raise TaskProtocolError("payload must be an object")
    task_type = task.get("type", task.get("task_type"))
    if task_type is not None and (not isinstance(task_type, str) or not task_type.strip()):
        raise TaskProtocolError("type must be a non-empty string when provided")

    if protocol_version == PROTOCOL_VERSION:
        trace_id = task.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id.strip() or len(trace_id) > 128:
            raise TaskProtocolError("trace_id must be a non-empty string of at most 128 characters")

    return task
