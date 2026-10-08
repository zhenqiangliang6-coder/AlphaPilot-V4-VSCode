import pytest

from python_worker.protocol.task_protocol import (
    PROTOCOL_VERSION,
    TaskProtocolError,
    validate_worker_task,
)


def test_v1_worker_task_requires_trace_id():
    task = {
        "protocol_version": PROTOCOL_VERSION,
        "trace_id": "trace-1",
        "task_id": "task-1",
        "payload": {"prompt": "hello"},
    }

    assert validate_worker_task(task) is task


def test_legacy_worker_task_remains_accepted():
    task = {"task_id": "task-1", "payload": {"prompt": "hello"}}

    assert validate_worker_task(task) is task


def test_unsupported_protocol_version_fails_closed():
    task = {
        "protocol_version": "2.0",
        "trace_id": "trace-1",
        "task_id": "task-1",
        "payload": {},
    }

    with pytest.raises(TaskProtocolError, match="Unsupported task protocol"):
        validate_worker_task(task)


def test_versioned_task_without_trace_id_is_rejected():
    task = {
        "protocol_version": PROTOCOL_VERSION,
        "task_id": "task-1",
        "payload": {},
    }

    with pytest.raises(TaskProtocolError, match="trace_id must be"):
        validate_worker_task(task)
