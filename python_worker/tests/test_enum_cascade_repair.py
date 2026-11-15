# python_worker/tests/test_enum_cascade_repair.py
"""G10.30 题面显式枚举级联替换的确定性修复契约。

v9 第 1 遍 R9 的真实失败：题面写死三组状态值映射并要求「所有引用
一次性全部更新、不得遗留旧词」，LLM 多步写入只改了部分文件，候选
工作区 10 failed(AssertionError) → 两轮 stalled → 分层收敛回滚 20 个
既有文件修改 → 真实工作区 enums.py 里三个旧值一个没少，质量门必挂。

本文件锁死：映射只在题面明确给出级联语义时解析、替换覆盖枚举成员名
与字符串字面量、排除 main.py 与依赖目录、语法守卫、幂等、且不误伤
其他轮次题面。
"""

import ast
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from python_worker import delivery_gate as dg  # noqa: E402


ROUND9 = """修改 ShopFlow 的订单状态枚举值。请找出所有引用这些枚举的地方并一次性全部更新。

变更内容：
- "confirmed" → "processing" （确认 → 处理中）
- "shipped" → "in_transit" （已发货 → 运输中）
- "delivered" → "completed" （已送达 → 已完成）

要求：
1. 修改 OrderStatus 枚举定义 —— 唯一事实源是 backend/models/enums.py
2. 修改所有路由中引用这些状态值的地方
5. 不要遗留任何旧的状态值：工作区所有 .py 文件都不得再出现这三个词
6. 同步更新 next_states() 方法里引用的状态值及枚举成员名

注意：不要改动 backend/main.py。"""

ENUMS = '''from enum import Enum


class OrderStatus(str, Enum):
    """订单状态枚举，线性顺序: pending -> confirmed -> shipped -> delivered。"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    def next_states(self) -> list[str]:
        if self == OrderStatus.PENDING:
            return [OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value]
        elif self == OrderStatus.CONFIRMED:
            return [OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value]
        elif self == OrderStatus.SHIPPED:
            return [OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value]
        elif self == OrderStatus.DELIVERED:
            return []
        return []
'''

TESTS = '''"""Test updating order status (pending -> confirmed)."""
from backend.models.enums import OrderStatus


def test_valid_transition(client):
    resp = client.put("/orders/1/status", json={"new_status": OrderStatus.CONFIRMED.value})
    assert resp.json()["status"] == OrderStatus.CONFIRMED.value


def test_invalid_transition(client):
    # Try to jump from pending to delivered (invalid)
    resp = client.put("/orders/1/status", json={"new_status": OrderStatus.DELIVERED.value})
    assert resp.status_code == 422
'''

OLD_WORDS = ("confirmed", "shipped", "delivered",
             "CONFIRMED", "SHIPPED", "DELIVERED")
NEW_WORDS = ("processing", "in_transit", "completed",
             "PROCESSING", "IN_TRANSIT", "COMPLETED")


def test_round9_prompt_parses_three_pairs():
    pairs = dg._enum_cascade_pairs(ROUND9)
    assert pairs == [("confirmed", "processing"),
                     ("shipped", "in_transit"),
                     ("delivered", "completed")]


def test_cascade_replaces_definition_and_all_references():
    files = {
        "backend/models/enums.py": ENUMS,
        "tests/test_orders.py": TESTS,
    }
    out, fixes = dg._repair_enum_cascade(files, ROUND9)
    enum_src = out["backend/models/enums.py"]
    test_src = out["tests/test_orders.py"]
    for word in OLD_WORDS:
        assert word not in enum_src, f"枚举定义残留 {word}"
        assert word not in test_src, f"测试引用残留 {word}"
    for word in NEW_WORDS:
        assert word in enum_src, f"枚举定义缺少 {word}"
    assert "OrderStatus.PROCESSING.value" in test_src
    assert "OrderStatus.COMPLETED.value" in test_src
    assert "pending -> processing -> in_transit -> completed" in enum_src
    ast.parse(enum_src)
    ast.parse(test_src)
    assert len(fixes) == 2


def test_gate_cascade_fix_is_idempotent_and_pure():
    files = {"backend/models/enums.py": ENUMS, "tests/test_orders.py": TESTS}
    out, fixes = dg._repair_enum_cascade(files, ROUND9)
    again, fixes2 = dg._repair_enum_cascade(out, ROUND9)
    assert again == out
    assert fixes2 == []
    assert "CONFIRMED" in files["backend/models/enums.py"], "原始 files 不得被就地修改"


def test_plain_refactor_prompt_does_not_trigger():
    files = {"backend/models/enums.py": ENUMS}
    out, fixes = dg._repair_enum_cascade(
        files, "把后端路由中的业务逻辑抽取到服务层并迁移数据库操作")
    assert out == files
    assert fixes == []
    assert dg._enum_cascade_pairs("重构服务层") == []


def test_single_mapping_does_not_trigger():
    req = '修改枚举值，所有引用一并更新："confirmed" → "processing"'
    assert dg._enum_cascade_pairs(req) == []
    files = {"backend/models/enums.py": ENUMS}
    out, fixes = dg._repair_enum_cascade(files, req)
    assert out == files and fixes == []


def test_mapping_without_cascade_scope_does_not_trigger():
    req = '把文案里的 "confirmed" → "processing"、"shipped" → "in_transit" 全部替换'
    assert dg._enum_cascade_pairs(req) == []
    files = {"backend/models/enums.py": ENUMS}
    out, fixes = dg._repair_enum_cascade(files, req)
    assert out == files and fixes == []


def test_excluded_paths_and_non_python_files_untouched():
    files = {
        "backend/main.py": 'CONFIRMED = "confirmed"\n',
        ".venv/Lib/site-packages/pkg.py": 'delivered = "delivered"\n',
        "vendor/site-packages/x.py": 'SHIPPED = "shipped"\n',
        "backend/models/enums.py": ENUMS,
        "README.txt": "confirmed shipped delivered\n",
    }
    out, fixes = dg._repair_enum_cascade(files, ROUND9)
    for p in ("backend/main.py", ".venv/Lib/site-packages/pkg.py",
              "vendor/site-packages/x.py", "README.txt"):
        assert out[p] == files[p], f"不应改动 {p}"
    assert len(fixes) == 1 and fixes[0].startswith("backend/models/enums.py:")


def test_syntax_guard_skips_unparsable_file():
    files = {
        "backend/models/enums.py": 'CONFIRMED = "confirmed"\ndef broken(:\n',
    }
    out, fixes = dg._repair_enum_cascade(files, ROUND9)
    assert out == files
    assert fixes == []


def test_gate_feeds_cascade_fix_into_candidate(monkeypatch):
    """闸门主链路：替换发生在真实 pytest 之前，并进入 fixes 证据。"""
    monkeypatch.setattr(
        dg, "snapshot_workspace",
        lambda ws: {"tests/test_dummy.py": "def test_ok(): pass\n"})
    seen = {}

    def fake_pytest(files):
        seen["candidate"] = dict(files)
        return True, ""

    monkeypatch.setattr(dg, "_run_pytest", fake_pytest)
    monkeypatch.setattr(dg, "_finalize_verified_pass", lambda *a, **k: True)

    ctx = {
        "meta": {"workspace_path": "C:/tmp/ws", "user_request": ROUND9},
        "final_file_ops": [
            {"op": "update", "path": "backend/models/enums.py", "content": ENUMS},
            {"op": "update", "path": "tests/test_orders.py", "content": TESTS},
        ],
    }
    result = dg.gate(ctx, "refactor")
    assert result["ran"] is True
    assert any("枚举级联替换 3 组" in f for f in result["fixes"])
    enum_src = seen["candidate"]["backend/models/enums.py"]
    assert "CONFIRMED" not in enum_src
    assert "PROCESSING" in enum_src
