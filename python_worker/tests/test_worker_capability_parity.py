from python_worker.agents.gemini.step_executor.execute_step import (
    STEP_DISPATCHER as GEMINI_STEPS,
)
from python_worker.agents.local_llm.step_executor.execute_step import (
    STEP_DISPATCHER as LOCAL_STEPS,
)
from python_worker.agents.maas.step_executor.execute_step import (
    STEP_DISPATCHER as MAAS_STEPS,
)
from python_worker.agents.modelscope.step_executor.execute_step import (
    STEP_DISPATCHER as MODELSCOPE_STEPS,
)
from python_worker.agents.gemini import gemini_worker_v2 as GEMINI_WORKER
from python_worker.agents.local_llm import local_worker_v3 as LOCAL_WORKER
from python_worker.agents.maas import maas_worker_v3 as MAAS_WORKER
from python_worker.agents.modelscope import modelscope_worker_v3 as MODELSCOPE_WORKER
from python_worker.worker_runtime import prepare_worker_request


def test_non_qwen_workers_dispatch_read_only_and_workspace_steps():
    for dispatcher in (GEMINI_STEPS, MAAS_STEPS, MODELSCOPE_STEPS, LOCAL_STEPS):
        assert "respond" in dispatcher
        assert "workspace" in dispatcher
        assert "docstring" in dispatcher


def test_non_qwen_worker_entrypoints_expose_protocol_aware_task_execution():
    for worker in (GEMINI_WORKER, MAAS_WORKER, MODELSCOPE_WORKER, LOCAL_WORKER):
        assert callable(worker.execute_task)
        assert "protocol_metadata" in worker.execute_task.__code__.co_varnames


def test_non_qwen_workers_execute_the_shared_read_only_chain_without_provider_calls(monkeypatch):
    workers = (
        (GEMINI_WORKER, "gemini_generate", "gemini"),
        (MAAS_WORKER, "maas_generate", "maas"),
        (MODELSCOPE_WORKER, "modelscope_generate", "modelscope"),
        (LOCAL_WORKER, "local_generate", "local"),
    )

    for worker, task_type, provider in workers:
        plan = {
            "intent": "chat",
            "persona": "conversational",
            "execution_chain": ["analyze", "plan", "respond"],
            "approval": {"required": False, "before": []},
        }
        prompt = "解释这项设计"
        prepared = {
            "prompt": prompt,
            "intent": plan["intent"],
            "persona": plan["persona"],
            "execution_plan": plan,
            "meta": {
                "intent": plan["intent"],
                "persona": plan["persona"],
                "user_request": prompt,
                "workspace_scan": None,
                "memory_user_id": None,
            },
            "memory_context": None,
        }
        monkeypatch.setattr(
            worker,
            "prepare_worker_request",
            lambda *_args, _prepared=prepared, **_kwargs: _prepared,
        )
        monkeypatch.setattr(worker, "check_stop_flag", lambda _task_id: False)

        def fake_execute_step(_task_id, step, _events, _context):
            step["output"] = {"text": f"{provider} mock response"}

        monkeypatch.setattr(worker, "execute_step", fake_execute_step)
        context = {"final_file_ops": [], "intermediate_results": []}
        steps = []
        result = worker.execute_task(
            task_type,
            {"prompt": prompt},
            f"parity-{provider}",
            steps,
            [],
            context,
            protocol_metadata={"protocol_version": "1.0", "trace_id": "trace-1"},
        )

        assert [step["type"] for step in steps] == ["analyze", "plan", "respond"]
        assert context["meta"]["model"] == provider
        assert result == f"{provider} mock response"


def test_shared_request_preparation_uses_qwen_capability_routing(monkeypatch):
    observed = {}

    def capture_plan(prompt, **kwargs):
        observed.update(kwargs)
        return {
            "intent": "chat",
            "persona": "conversational",
            "execution_chain": ["analyze", "plan", "respond"],
        }

    monkeypatch.setattr(
        "python_worker.worker_runtime.IntentRouter.plan_request", capture_plan
    )
    prepared = prepare_worker_request(
        {"prompt": "你好"},
        "parity-test",
        "gemini_generate",
        "Gemini",
        {"protocol_version": "1.0", "trace_id": "trace-parity"},
    )

    assert observed["worker"] == "qwen"
    assert prepared["execution_plan"]["execution_chain"] == [
        "analyze",
        "plan",
        "respond",
    ]
    assert prepared["meta"]["trace_id"] == "trace-parity"
