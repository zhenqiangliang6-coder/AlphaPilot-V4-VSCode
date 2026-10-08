import json

import pytest
import requests

from python_worker.agents.modelscope import modelscope_api
from python_worker.agents.modelscope import modelscope_worker_v3
from python_worker.agents.modelscope.step_executor import docstring_step
from python_worker import worker_config


class FakeResponse:
    def __init__(self, lines=None, body=None, error=None):
        self.lines = lines or []
        self.body = body
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def json(self):
        return self.body

    def iter_lines(self):
        yield from self.lines
        if self.error:
            raise self.error


def test_non_stream_request_uses_configured_timeout_and_response(monkeypatch):
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(modelscope_api, "REQUEST_TIMEOUT", (7, 600))
    observed = {}

    def post(*args, **kwargs):
        observed.update(kwargs)
        return FakeResponse(body={"choices": [{"message": {"content": "done"}}]})

    monkeypatch.setattr(modelscope_api.SESSION, "post", post)

    assert modelscope_api.call_modelscope("prompt") == "done"
    assert observed["timeout"] == (7, 600)
    assert observed["json"]["messages"][0]["content"] == "prompt"
    assert observed["headers"]["Authorization"] == "Bearer test-key"


def test_http_session_retries_post_requests_for_transient_server_errors():
    retry = modelscope_api.SESSION.get_adapter(modelscope_api.MODELSCOPE_URL).max_retries

    assert retry.total == modelscope_api.MODELSCOPE_MAX_RETRIES
    assert set(retry.status_forcelist) == {500, 502, 503, 504}
    assert "POST" in retry.allowed_methods
    assert retry.read == 0


def test_non_stream_request_retries_read_timeout(monkeypatch):
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_MAX_RETRIES", 2)
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_RETRY_BACKOFF_SECONDS", 0)
    responses = [
        requests.exceptions.ReadTimeout("slow response"),
        requests.exceptions.ReadTimeout("slow response"),
        FakeResponse(body={"choices": [{"message": {"content": "recovered"}}]}),
    ]
    calls = []

    def post(*_args, **_kwargs):
        calls.append(True)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(modelscope_api.SESSION, "post", post)

    assert modelscope_api.call_modelscope("prompt") == "recovered"
    assert len(calls) == 3


def test_stream_retries_read_timeout_before_yielding_any_content(monkeypatch):
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_MAX_RETRIES", 2)
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_RETRY_BACKOFF_SECONDS", 0)
    responses = [
        FakeResponse(error=requests.exceptions.ReadTimeout("slow response")),
        FakeResponse(
            lines=[
                b'data: {"choices":[{"delta":{"content":"part 1"}}]}',
                b'data: {"choices":[{"delta":{"content":"part 2"}}]}',
                b"data: [DONE]",
            ]
        ),
    ]
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(modelscope_api.STREAM_SESSION, "post", post)

    assert list(modelscope_api.call_modelscope_stream("prompt")) == [
        "part 1",
        "part 2",
    ]
    assert len(calls) == 2


def test_stream_does_not_restart_after_partial_output(monkeypatch):
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_MAX_RETRIES", 3)
    monkeypatch.setattr(modelscope_api, "MODELSCOPE_RETRY_BACKOFF_SECONDS", 0)
    calls = []
    response = FakeResponse(
        lines=[b'data: {"choices":[{"delta":{"content":"partial"}}]}'],
        error=requests.exceptions.ReadTimeout("stream interrupted"),
    )

    def post(*_args, **_kwargs):
        calls.append(True)
        return response

    monkeypatch.setattr(modelscope_api.STREAM_SESSION, "post", post)
    stream = modelscope_api.call_modelscope_stream("prompt")

    assert next(stream) == "partial"
    with pytest.raises(requests.exceptions.ReadTimeout):
        next(stream)
    assert len(calls) == 1


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttl = {}

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttl[key] = ex

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


def test_worker_checkpoint_round_trip_excludes_private_context(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(modelscope_worker_v3, "redis", fake_redis)
    context = {"intermediate_results": [{"type": "plan"}], "_respond_call": lambda: None}

    modelscope_worker_v3.save_worker_checkpoint(
        "task-1", "modelscope_generate", [{"status": "completed"}], [], context
    )
    checkpoint = modelscope_worker_v3.load_worker_checkpoint(
        "task-1", "modelscope_generate"
    )

    assert checkpoint["steps"] == [{"status": "completed"}]
    assert checkpoint["context"] == {"intermediate_results": [{"type": "plan"}]}
    assert "_respond_call" not in checkpoint["context"]
    assert fake_redis.ttl[modelscope_worker_v3._checkpoint_key("task-1")] == (
        modelscope_worker_v3.CHECKPOINT_TTL_SECONDS
    )
    modelscope_worker_v3.clear_worker_checkpoint("task-1")
    assert modelscope_worker_v3.load_worker_checkpoint(
        "task-1", "modelscope_generate"
    ) is None


def test_memory_redis_supports_expiring_checkpoint_values():
    memory_redis = worker_config.create_redis_client(redis_type="memory")
    memory_redis.set("checkpoint", "progress", ex=0)

    assert memory_redis.get("checkpoint") is None


def test_execute_task_skips_completed_steps_and_checkpoints_next(monkeypatch):
    plan = {
        "intent": "chat",
        "persona": "conversational",
        "execution_chain": ["analyze", "respond"],
        "approval": {"required": False, "before": []},
    }
    monkeypatch.setattr(
        modelscope_worker_v3,
        "prepare_worker_request",
        lambda *_args, **_kwargs: {
            "prompt": "hello",
            "execution_plan": plan,
            "meta": {"intent": "chat", "persona": "conversational"},
        },
    )
    monkeypatch.setattr(modelscope_worker_v3, "check_stop_flag", lambda _task_id: False)
    invoked = []

    def execute_step(_task_id, step, _events, _context):
        invoked.append(step["type"])
        step["output"] = {"text": "response"}

    monkeypatch.setattr(modelscope_worker_v3, "execute_step", execute_step)
    steps = [
        {
            "id": "step-1",
            "type": "analyze",
            "status": "completed",
            "output": {"text": "previously completed"},
        },
        {"id": "step-2", "type": "respond", "status": "pending"},
    ]
    context = {"meta": {"checkpoint_marker": True}, "intermediate_results": []}
    checkpoints = []

    result = modelscope_worker_v3.execute_task(
        "modelscope_generate",
        {"prompt": "hello"},
        "task-2",
        steps,
        [],
        context,
        checkpoint_callback=lambda: checkpoints.append(
            [step["status"] for step in steps]
        ),
    )

    assert result == "response"
    assert invoked == ["respond"]
    assert len(checkpoints) == 1
    assert context["meta"]["checkpoint_marker"] is True


def test_execute_task_does_not_checkpoint_a_failed_model_call(monkeypatch):
    plan = {
        "intent": "chat",
        "persona": "conversational",
        "execution_chain": ["respond"],
        "approval": {"required": False, "before": []},
    }
    monkeypatch.setattr(
        modelscope_worker_v3,
        "prepare_worker_request",
        lambda *_args, **_kwargs: {
            "prompt": "hello",
            "execution_plan": plan,
            "meta": {"intent": "chat", "persona": "conversational"},
        },
    )
    monkeypatch.setattr(modelscope_worker_v3, "check_stop_flag", lambda _task_id: False)
    monkeypatch.setattr(
        modelscope_worker_v3,
        "execute_step",
        lambda _task_id, step, _events, _context: step.update(
            output={"text": "request failed", "llm_success": False}
        ),
    )
    steps = []
    checkpoint_calls = []

    with pytest.raises(RuntimeError, match="ModelScope 调用未成功"):
        modelscope_worker_v3.execute_task(
            "modelscope_generate",
            {"prompt": "hello"},
            "task-3",
            steps,
            [],
            {"intermediate_results": []},
            checkpoint_callback=lambda: checkpoint_calls.append(True),
        )

    assert steps[0]["status"] == "failed"
    assert checkpoint_calls == []


def test_docstring_step_resumes_after_last_successful_file(monkeypatch):
    files = [
        {"path": "first.py", "content": "def first(): pass"},
        {"path": "second.py", "content": "def second(): pass"},
    ]
    responses = [
        "def first():\n    pass",
        requests.exceptions.ReadTimeout("slow response"),
        "def second():\n    pass",
    ]
    calls = []
    checkpoints = []
    step = {"id": "docstring", "type": "docstring", "status": "running"}

    monkeypatch.setattr(docstring_step, "get_python_files", lambda _file_ops: files)
    monkeypatch.setattr(
        docstring_step,
        "call_modelscope",
        lambda prompt: (
            calls.append(prompt),
            _raise_or_return(responses.pop(0)),
        )[1],
    )
    monkeypatch.setattr(
        docstring_step, "extract_code", lambda code, **_kwargs: code
    )
    context = {
        "final_file_ops": [{"path": "first.py"}, {"path": "second.py"}],
        "meta": {"persona": "engineer"},
        "_checkpoint_callback": lambda: checkpoints.append(
            json.loads(json.dumps(step["output"]["documented_files"]))
        ),
    }

    docstring_step.run_docstring_step(step, context, [])
    assert step["output"]["llm_success"] is False
    assert [item["path"] for item in checkpoints[0]] == ["first.py"]

    docstring_step.run_docstring_step(step, context, [])

    assert len(calls) == 3
    assert step["output"]["llm_success"] is True
    assert [item["path"] for item in step["output"]["documented_files"]] == [
        "first.py",
        "second.py",
    ]


def _raise_or_return(value):
    if isinstance(value, Exception):
        raise value
    return value
