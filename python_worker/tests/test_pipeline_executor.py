"""Pipeline Executor 单元测试 — 不依赖 Worker 框架的纯逻辑验证。"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline_executor.contract import (
    PipelineState, PipelineStage, PipelineContract,
    PlanArtifact, CodeArtifact, TestArtifact, FixArtifact, ChangelogArtifact,
    make_write_code_pipeline, make_execute_operation_pipeline,
    _parse_test_counts,
)
from pipeline_executor.checkpoint import PipelineCheckpoint, CheckpointStore, get_checkpoint_store
from pipeline_executor.stages import (
    PreparatoryStage, GenerativeStage, PostProcessStage, OperateStage,
    _gate_always_true, _gate_has_file_ops, _gate_has_workspace,
)
from pipeline_executor.pipeline import PipelineExecutor, PipelineResult


# ============================================================
# Contract 层测试
# ============================================================

def test_pipeline_state_enum():
    assert PipelineState.PENDING.value == "pending"
    assert PipelineState.RUNNING.value == "running"
    assert PipelineState.COMPLETED.value == "completed"
    assert PipelineState.FAILED.value == "failed"
    terminal = PipelineState.terminal_states()
    assert PipelineState.COMPLETED in terminal
    assert PipelineState.FAILED in terminal
    assert PipelineState.PENDING not in terminal


def test_plan_artifact():
    pa = PlanArtifact(text="build a login", files_to_create=["auth/login.py"])
    assert pa.estimated_complexity == "medium"
    assert len(pa.files_to_create) == 1


def test_test_artifact():
    ta = TestArtifact(passed=3, failed=1, total=4, exec_success=False)
    assert not ta.all_passed
    assert "3/4" in ta.summary

    tb = TestArtifact(passed=2, failed=0, total=2, exec_success=True)
    assert tb.all_passed


def test_pipeline_stage_basics():
    stage = PipelineStage(name="test", steps=["a", "b"])
    assert stage.can_enter({})
    assert stage.required is True

    gated = PipelineStage(name="gated", steps=["x"], gate=lambda c: c.get("ready", False))
    assert not gated.can_enter({"ready": False})
    assert gated.can_enter({"ready": True})


def test_pipeline_contract_advance():
    contract = PipelineContract(stages=[
        PipelineStage(name="s1", steps=["a", "b"]),
        PipelineStage(name="s2", steps=["c"]),
    ])
    assert contract.current_step_type() is None

    assert contract.advance_stage()   # → stage 0
    assert contract.current_stage.name == "s1"
    assert contract.advance_step()    # → step 0
    assert contract.current_step_type() == "a"
    assert contract.advance_step()    # → step 1
    assert contract.current_step_type() == "b"
    assert not contract.advance_step()  # stage 0 done

    assert contract.advance_stage()   # → stage 1
    assert contract.current_stage.name == "s2"
    assert contract.advance_step()    # → step 0
    assert contract.current_step_type() == "c"
    assert not contract.advance_step()  # stage 1 done

    assert not contract.advance_stage()  # pipeline done


def test_make_write_code_pipeline():
    contract = make_write_code_pipeline()
    assert len(contract.stages) == 3
    assert contract.stages[0].name == "preparatory"
    assert contract.stages[1].name == "generative"
    assert contract.stages[2].name == "post"
    assert "analyze" in contract.stages[0].steps
    assert "write" in contract.stages[1].steps
    assert "changelog" in contract.stages[2].steps


def test_parse_test_counts():
    assert _parse_test_counts("3 PASSED\n0 FAILED") == (3, 0)
    assert _parse_test_counts("1 passed\n2 failed") == (1, 2)
    assert _parse_test_counts("5 PASSED\n1 FAILED") == (5, 1)
    assert _parse_test_counts("no tests") == (0, 0)


# ============================================================
# Checkpoint 层测试
# ============================================================

def test_checkpoint_serialization():
    cp = PipelineCheckpoint(
        pipeline_id="test-123",
        state="running",
        current_stage=1,
        current_step=2,
        stage_results=["completed", "running", "pending"],
        completed_stages=["preparatory"],
    )
    data = cp.to_dict()
    assert data["pipeline_id"] == "test-123"
    assert data["current_stage"] == 1

    cp2 = PipelineCheckpoint.from_dict(data)
    assert cp2.pipeline_id == cp.pipeline_id
    assert cp2.current_step == cp.current_step
    assert cp2.is_resumable

    json_str = cp.to_json()
    cp3 = PipelineCheckpoint.from_json(json_str)
    assert cp3.completed_stages == ["preparatory"]


def test_checkpoint_store():
    store = CheckpointStore()
    cp = PipelineCheckpoint(pipeline_id="a1", state="running")
    store.save(cp)
    assert store.has("a1")

    loaded = store.load("a1")
    assert loaded.pipeline_id == "a1"

    store.delete("a1")
    assert not store.has("a1")


def test_checkpoint_is_resumable():
    running = PipelineCheckpoint(pipeline_id="r", state="running",
        completed_stages=["preparatory"], current_stage=0)
    assert running.is_resumable

    completed = PipelineCheckpoint(pipeline_id="c", state="completed",
        completed_stages=["preparatory", "generative"])
    assert not completed.is_resumable

    pending = PipelineCheckpoint(pipeline_id="p", state="pending")
    assert not pending.is_resumable


# ============================================================
# Stages 层测试
# ============================================================

def test_preparatory_stage():
    s = PreparatoryStage()
    assert s.name == "preparatory"
    assert s.required
    assert s.steps == ["analyze", "workspace", "plan"]
    assert s.gate is not None


def test_generative_stage():
    s = GenerativeStage()
    assert s.name == "generative"
    assert s.retry == 1
    assert "write" in s.steps


def test_post_process_stage():
    s = PostProcessStage()
    assert s.name == "post"
    assert not s.required  # 非阻塞


def test_gate_functions():
    assert _gate_always_true({})
    assert _gate_always_true(None)  # 无条件准入，永远 True

    assert _gate_has_file_ops({"final_file_ops": [{"path": "x.py"}]})
    assert not _gate_has_file_ops({"final_file_ops": []})

    assert _gate_has_workspace({"meta": {"workspace_path": "/tmp/test"}})
    assert not _gate_has_workspace({"meta": {}})


# ============================================================
# PipelineExecutor 层测试（Mock execute_step）
# ============================================================

def test_pipeline_executor_full_run():
    """使用 mock execute_step 验证完整的 PipelineExecutor 调度流程。"""
    from pipeline_executor.pipeline import set_execute_step

    executed_steps = []

    def mock_execute_step(task_id, step, events, context):
        executed_steps.append(step["type"])
        context.setdefault("intermediate_results", []).append({
            "type": step["type"],
            "text": f"{step['type']} completed",
        })
        if step["type"] == "test":
            context["final_file_ops"] = [{"path": "test.py", "op": "create"}]

    set_execute_step(mock_execute_step)

    contract = make_write_code_pipeline()
    executor = PipelineExecutor(contract, task_id="test-full-run")
    context = {"meta": {"workspace_path": "/tmp/test", "user_request": "test"}}

    result = executor.execute(context)

    assert result.success
    assert "preparatory" in result.stages_completed
    assert "generative" in result.stages_completed
    assert "post" in result.stages_completed
    assert len(executed_steps) == 11  # 3 + 4 + 4
    assert "analyze" in executed_steps
    assert "write" in executed_steps
    assert "changelog" in executed_steps


def test_pipeline_executor_gate_rejects():
    """Gate 拒绝时跳过阶段。"""
    from pipeline_executor.pipeline import set_execute_step

    executed = []

    def mock_execute_step(task_id, step, events, context):
        executed.append(step["type"])

    set_execute_step(mock_execute_step)

    contract = PipelineContract(stages=[
        PipelineStage(name="s1", steps=["analyze"], gate=lambda c: False),
        PipelineStage(name="s2", steps=["respond"], gate=lambda c: True),
    ])
    executor = PipelineExecutor(contract, task_id="test-gate")
    context = {"meta": {}}

    result = executor.execute(context)
    assert not result.success  # s1 failed and is required
    assert "s1" in result.stages_failed
    assert "analyze" not in executed  # gate rejected


def test_pipeline_executor_non_required_stage_fails():
    """非阻塞阶段失败不影响后续。"""
    from pipeline_executor.pipeline import set_execute_step

    executed = []

    def mock_execute_step(task_id, step, events, context):
        executed.append(step["type"])
        if step["type"] == "changelog":
            raise RuntimeError("changelog failed")

    set_execute_step(mock_execute_step)

    contract = PipelineContract(stages=[
        PipelineStage(name="gen", steps=["write"], required=True),
        PipelineStage(name="post", steps=["changelog"], required=False),
        PipelineStage(name="final", steps=["respond"], required=True),
    ])
    executor = PipelineExecutor(contract, task_id="test-nonreq")
    context = {"meta": {"workspace_path": "/tmp", "user_request": "test"}}

    result = executor.execute(context)
    assert result.success  # post 失败了但非阻塞
    assert "post" in result.stages_failed
    assert "final" in result.stages_completed
    assert "respond" in executed


def test_checkpoint_store_after_run():
    """执行后检查点被正确存储。"""
    from pipeline_executor.pipeline import set_execute_step

    def mock_execute_step(task_id, step, events, context):
        pass

    set_execute_step(mock_execute_step)

    contract = PipelineContract(stages=[
        PipelineStage(name="s1", steps=["respond"]),
    ])
    executor = PipelineExecutor(contract, task_id="test-ckpt")
    executor.execute({"meta": {}})

    store = get_checkpoint_store()
    cp = store.load("test-ckpt")
    assert cp is not None
    assert cp.completed_stages == ["s1"]
    assert cp.state == "completed"


if __name__ == "__main__":
    tests = [
        ("PipelineState enum", test_pipeline_state_enum),
        ("PlanArtifact", test_plan_artifact),
        ("TestArtifact", test_test_artifact),
        ("PipelineStage basics", test_pipeline_stage_basics),
        ("PipelineContract advance", test_pipeline_contract_advance),
        ("make_write_code_pipeline", test_make_write_code_pipeline),
        ("parse_test_counts", test_parse_test_counts),
        ("Checkpoint serialization", test_checkpoint_serialization),
        ("CheckpointStore", test_checkpoint_store),
        ("Checkpoint is_resumable", test_checkpoint_is_resumable),
        ("PreparatoryStage", test_preparatory_stage),
        ("GenerativeStage", test_generative_stage),
        ("PostProcessStage", test_post_process_stage),
        ("Gate functions", test_gate_functions),
        ("PipelineExecutor full run", test_pipeline_executor_full_run),
        ("PipelineExecutor gate rejects", test_pipeline_executor_gate_rejects),
        ("PipelineExecutor non-required stage", test_pipeline_executor_non_required_stage_fails),
        ("Checkpoint after run", test_checkpoint_store_after_run),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"FAIL: {name} - {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)