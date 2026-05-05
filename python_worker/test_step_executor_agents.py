# -*- coding: utf-8 -*-
import importlib
import inspect
import pytest


AGENTS = [
    "python_worker.agents.qwen",
    "python_worker.agents.Volcengine",
    "python_worker.agents.deepeek",
]


STEP_TYPES = ["analyze", "plan", "write", "refine", "test"]


def _safe_api_stub(prompt):
    # 返回包含可被 extract_code 提取的代码块，或简单文本
    return "```python\nprint('ok')\n```"


def _safe_run_python(code):
    return {"stdout": "ok\n", "stderr": "", "error": None}


@pytest.mark.parametrize("agent_pkg", AGENTS)
@pytest.mark.parametrize("step_type", STEP_TYPES)
def test_execute_step_agent_does_not_crash(monkeypatch, agent_pkg, step_type):
    """确保指定 agent 的每种 step 类型在受控替换下不会抛异常，并会写入 output 与 events"""

    # 导入 execute_step
    exec_mod = importlib.import_module(f"{agent_pkg}.step_executor.execute_step")
    execute_fn = getattr(exec_mod, "execute_step")

    # 尝试导入具体的 step 模块（若不存在则跳过）
    try:
        step_mod = importlib.import_module(f"{agent_pkg}.step_executor.{step_type}_step")
    except Exception:
        pytest.skip(f"{agent_pkg} 缺少 {step_type}_step 模块，跳过")

    # 替换可能的外部依赖：LLM 接口与 run_python
    if hasattr(step_mod, "call_qwen"):
        monkeypatch.setattr(step_mod, "call_qwen", lambda p: _safe_api_stub(p))
    if hasattr(step_mod, "call_doubao"):
        monkeypatch.setattr(step_mod, "call_doubao", lambda p: _safe_api_stub(p))
    if hasattr(step_mod, "call_deepseek"):
        monkeypatch.setattr(step_mod, "call_deepseek", lambda p: _safe_api_stub(p))

    # run_python 可能来自不同导入路径；优先替换 step_mod 局部引用
    if hasattr(step_mod, "run_python"):
        monkeypatch.setattr(step_mod, "run_python", lambda code: _safe_run_python(code))
    else:
        # 尝试替换公共位置
        try:
            ce = importlib.import_module("python_worker.code_executor")
            monkeypatch.setattr(ce, "run_python", lambda code: _safe_run_python(code))
        except Exception:
            pass

    # 准备 context 与 step
    context = {"intermediate_results": []}
    events = []
    step = {"id": "s1", "type": step_type, "input": {"prompt": "p"}}

    # 为 write/test/refine 预置依赖数据
    if step_type == "write":
        context["intermediate_results"].append({"type": "plan", "plan": "do something"})
    if step_type in ("test", "refine"):
        # write 输出形式：带 code 或 text
        context["intermediate_results"].append({"type": "write", "text": "```python\nprint(1)\n```", "code": "print(1)"})

    # 调用 execute_step；若支持 api_func，则传入 stub
    sig = inspect.signature(execute_fn)
    kwargs = {}
    if "api_func" in sig.parameters:
        kwargs["api_func"] = _safe_api_stub

    # 不抛异常为通过
    execute_fn("task-1", step, events, context, **kwargs) if kwargs else execute_fn("task-1", step, events, context)

    assert "output" in step
    assert events and events[-1]["event"] == "step_finished"
