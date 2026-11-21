# python_worker/tests/test_contract_subset_g1033.py
"""G10.33 题面契约子集交付。

v12 第 1 遍实证：R8 与 R9 的候选工作区都因 LLM 产出的坏导入在收集期
崩溃（-1 failed, ImportError），闸门自愈失败后分层收敛把「全部既有文件
修改」回滚，两轮各自只落盘 2 个 .alphapilot_generated.mark。于是 R8 的
结构契约（Inventory 类 / inventory 表）与 R9 的枚举级联都没落盘：
R9 质量门三个旧值全留，R10 语义契约提取不到 Inventory 直接 FAIL-CLOSED。

题面已写死的机械映射不该与同一批候选里未收敛的 LLM 改动同生共死。
闸门从真实基线独立重建这部分修复，真实 pytest 复验通过后单独交付。
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402
from python_worker.tests import test_observe_task_system as obs  # noqa: E402


ENUMS_OLD = (
    "class OrderStatus:\n"
    '    CONFIRMED = "confirmed"\n'
    '    SHIPPED = "shipped"\n'
    '    DELIVERED = "delivered"\n'
)
BASE = {
    "tests/test_ok.py": "def test_ok():\n    assert True\n",
    "backend/models/enums.py": ENUMS_OLD,
    "tests/test_orders.py": (
        "def test_transition():\n"
        '    assert "confirmed" == "confirmed"\n'
    ),
}
BAD_NEW = "tests/test_broken.py"
BAD_SRC = "from backend.models import DoesNotExist\n\ndef test_x(): assert False\n"
BAD_OUTPUT = ("ImportError while importing test module\n"
              "E   ImportError: cannot import name 'DoesNotExist'\n"
              "-1 failed")


def _ctx(request=None, ops=None):
    return {
        "meta": {
            "workspace_path": "C:/tmp/ws",
            "user_request": request if request is not None
            else obs.PROMPT_ROUND_9,
        },
        "final_file_ops": ops if ops is not None else [
            {"op": "create", "path": BAD_NEW, "content": BAD_SRC},
            {"op": "modify", "path": "backend/models/enums.py",
             "content": ENUMS_OLD},
        ],
    }


def _install(monkeypatch, contract_green=True):
    """模拟：任何含坏新增文件的候选收集期崩溃；契约子集可绿可红。"""
    monkeypatch.setattr(dg, "snapshot_workspace", lambda ws: dict(BASE))
    monkeypatch.setattr(dg, "_MAX_REPAIR_ROUNDS", 0)
    monkeypatch.setattr(dg, "_retry_with_deterministic_fix",
                        lambda cand, out, fixes: (cand, False, out))
    seen = []

    def fake_pytest(files):
        seen.append(dict(files))
        if BAD_NEW in files:
            return False, BAD_OUTPUT
        if not contract_green:
            return False, BAD_OUTPUT
        return True, ""

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    return seen


def test_changed_paths_is_pure_and_exact():
    """只返回内容真正变化的路径，且不修改入参。"""
    before = {"a.py": "x", "b.py": "y"}
    after = {"a.py": "x", "b.py": "z", "c.py": "w"}
    out = dg._changed_paths(before, after)
    assert out == {"b.py", "c.py"}
    assert before == {"a.py": "x", "b.py": "y"}
    assert dg._changed_paths(before, dict(before)) == set()


def test_enum_cascade_contract_survives_layered_convergence(monkeypatch):
    """分层收敛不得回滚题面写死的枚举级联；坏 LLM 文件必须被丢弃。"""
    _install(monkeypatch)
    ctx = _ctx()
    result = dg.gate(ctx, "write_code")

    assert result["ran"] is True
    assert result["contract_subset_delivery"] is True
    paths = [str(op.get("path")) for op in ctx["final_file_ops"]]
    assert "backend/models/enums.py" in paths
    assert "tests/test_orders.py" in paths
    assert BAD_NEW not in paths, "未验证的 LLM 坏文件不得进入交付清单"

    delivered = {str(op.get("path")): op.get("content")
                 for op in ctx["final_file_ops"] if op.get("content")}
    enums = delivered["backend/models/enums.py"]
    for old in ("confirmed", "shipped", "delivered"):
        assert old not in enums, f"旧枚举值 {old} 仍残留"
    for new in ("processing", "in_transit", "completed"):
        assert new in enums, f"新枚举值 {new} 未落盘"
    assert result["kept_new_files"] == sorted(
        {"backend/models/enums.py", "tests/test_orders.py"})
    assert "契约子集" in result["reason"]


def test_contract_subset_must_pass_real_pytest(monkeypatch):
    """契约子集自身让基线变红时，退回既有分层收敛，绝不强行落盘。"""
    _install(monkeypatch, contract_green=False)
    ctx = _ctx()
    result = dg.gate(ctx, "write_code")
    assert result.get("contract_subset_delivery") is not True
    assert "契约子集" not in result["reason"]


def test_no_explicit_contract_keeps_legacy_convergence(monkeypatch):
    """普通题面（无写死映射）不触发契约子集，原有分层语义不变。"""
    _install(monkeypatch)
    ctx = _ctx(request="给订单模块补一点日志，注意保持现有行为。")
    result = dg.gate(ctx, "write_code")
    assert result.get("contract_subset_delivery") is not True
    assert result.get("contract_paths") == []


def test_contract_subset_contains_no_llm_content(monkeypatch):
    """交付清单的契约文件源码来自基线重建，不含 LLM 补丁的任意字符串。"""
    seen = _install(monkeypatch)
    ctx = _ctx(ops=[
        {"op": "create", "path": BAD_NEW, "content": BAD_SRC},
        {"op": "modify", "path": "backend/models/enums.py",
         "content": ENUMS_OLD + "# LLM_UNVERIFIED_MARKER\n"},
    ])
    dg.gate(ctx, "write_code")
    delivered = {str(op.get("path")): op.get("content")
                 for op in ctx["final_file_ops"] if op.get("content")}
    assert "LLM_UNVERIFIED_MARKER" not in delivered["backend/models/enums.py"]
    assert any("processing" in (f.get("backend/models/enums.py") or "")
               for f in seen), "契约子集应经真实 pytest 复验"
