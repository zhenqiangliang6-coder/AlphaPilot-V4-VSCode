# python_worker/tests/test_g1043_contracts.py
"""G10.43 新增测试复用 conftest 隔离夹具守卫的契约测试。

真实故障（shopflow_v23_1 / shopflow_v24_1，2026-11-15 21:12 / 21:36）：
连续两代第 1 遍均 `2 failed, 5 passed`，R5–R8 四维全绿，R9/R10 都倒在

    assert pre_test.get("passed", False), "前置条件: pytest 未通过"

工作区 tests/test_inventory.py 是 LLM 在 R8 新建的，用**模块级**
`client = TestClient(app)`，测试函数都不接 client 参数 ⇒ 绕过了
tests/conftest.py 已提供的 `:memory:` + function-scope client fixture，
直连文件 DB backend/shopflow.db。R8 质量门第一次跑（DB 干净）绿，
R9/R10 前置第二次跑因残留数据（POST 重复 400 "already exists"、
扣减累积 4/1 != 7）必红。判卷前置断言本身正确（FAIL-CLOSED），
不是判卷 bug，也不能改判卷。

而 PROMPT_ROUND_8 题面已写死「不要改动 tests/conftest.py（夹具已建好
表）」，合规基线 tests/test_orders.py 一律 def test_x(client: TestClient)。
故这是「题面显式约束 + 生成物可确定性改写」的真实缺陷：G10.43 在
候选工作区跑 pytest 前，把新增测试改写为复用 conftest 隔离夹具
（注释模块级 TestClient(app) 赋值 + 给每个 test_* 补 client 参数），
由 _apply_back 同步回落盘清单（成长法第 35 条）。

契约：只在题面显式声明夹具已建好的增量轮（R8）触发；必须 conftest
真的定义了 client fixture；只处理本次新增的 tests/test_*.py；AST 语法
守卫；含非 test 辅助函数 / 多行 def / *args 的复杂生成物一律放弃
（FAIL-CLOSED，不制造 NameError）；合规生成物 / 既有文件 / 非适用轮次
/ 无 conftest 一律不误伤；幂等；已验证候选与最终落盘清单一致。
"""

import ast
import importlib.util
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import python_worker.delivery_gate as dg  # noqa: E402
from python_worker.delivery_gate import build_candidate  # noqa: E402


def _load_observe_module():
    """从绝对路径加载判卷模块，断言题面契约未被放宽。"""
    path = Path(__file__).with_name("test_observe_task_system.py")
    spec = importlib.util.spec_from_file_location("_g1043_observe_contract", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── R8 题面（PROMPT_ROUND_8 的关键片段，含题面显式夹具约束）──────────
R8_REQ = """给 ShopFlow 电商系统增加「库存管理」模块。仔细阅读已有代码后再动手，不要破坏现有功能。

新增内容：
5. tests/test_inventory.py — 测试所有库存 API + 库存扣减联动

注意：
- 不要修改 tests/test_orders.py 中已有的测试逻辑，也不要改动 tests/conftest.py（夹具已建好表）
- backend/main.py 必须用 include_router(inventory_router, prefix="/inventory") 注册库存路由
"""

PLAIN_REQ = "给订单模块补一点日志，保持现有行为。"
R5_REQ = "设计 ShopFlow 电商系统的架构，输出 docs/architecture_design.md。"
R6_REQ = "实现 ShopFlow 订单核心功能：模型、schema、路由与测试。"
R9_REQ = "修改 ShopFlow 的订单状态枚举值。请找出所有引用这些枚举的地方并一次性全部更新。"
R10_REQ = "重构 ShopFlow 后端：把路由中的业务逻辑提取到服务层。"


# ── 合规 conftest（R6 基线风格，定义 :memory: client fixture）──────────
CONFTEST_OK = '''import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import Base, get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL,
                       connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
'''

CONFTEST_NO_FIXTURE = '''from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)
'''

# 合规基线测试：所有 test_* 都接 client 参数（走隔离 fixture）
ORDERS_OK = '''import pytest
from fastapi.testclient import TestClient

def test_create_order(client: TestClient):
    r = client.post("/orders/", json={"user_id": "u", "total_amount": 1.0, "items": []})
    assert r.status_code == 200

def test_list_orders(client: TestClient):
    r = client.get("/orders/")
    assert r.status_code == 200
'''

# ── v24 真实 R8 违规生成物（shopflow_v24 工作区逐字快照）──────────────
BAD_INVENTORY_V24 = '''import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_create_inventory():
    response = client.post("/inventory/", json={
        "product_name": "Apple",
        "sku": "SKU001",
        "quantity": 100,
        "unit_price": 1.5
    })
    assert response.status_code == 200
    data = response.json()
    assert data["product_name"] == "Apple"
    assert data["quantity"] == 100

def test_create_inventory_duplicate():
    client.post("/inventory/", json={
        "product_name": "Banana",
        "sku": "SKU002",
        "quantity": 50,
        "unit_price": 2.0
    })
    response = client.post("/inventory/", json={
        "product_name": "Banana",
        "sku": "SKU002",
        "quantity": 50,
        "unit_price": 2.0
    })
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

def test_get_inventory_list():
    response = client.get("/inventory/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_inventory_item():
    client.post("/inventory/", json={
        "product_name": "Orange",
        "sku": "SKU003",
        "quantity": 30,
        "unit_price": 3.0
    })
    response = client.get("/inventory/Orange")
    assert response.status_code == 200
    assert response.json()["product_name"] == "Orange"

def test_update_inventory():
    client.post("/inventory/", json={
        "product_name": "Grape",
        "sku": "SKU004",
        "quantity": 20,
        "unit_price": 4.0
    })
    response = client.patch("/inventory/Grape", json={"quantity": 25})
    assert response.status_code == 200
    assert response.json()["quantity"] == 25

def test_order_deducts_inventory():
    client.post("/inventory/", json={
        "product_name": "Milk",
        "sku": "SKU005",
        "quantity": 10,
        "unit_price": 5.0
    })
    response = client.post("/orders/", json={
        "user_id": "test_user_01",
        "total_amount": 15.0,
        "items": [{"product_name": "Milk", "quantity": 3}]
    })
    assert response.status_code in [200, 201]

    inv_response = client.get("/inventory/Milk")
    assert inv_response.json()["quantity"] == 7

def test_order_product_not_exist():
    response = client.post("/orders/", json={
        "user_id": "test_user_02",
        "total_amount": 10.0,
        "items": [{"product_name": "NotExist", "quantity": 1}]
    })
    assert response.status_code == 400
    assert "does not exist in inventory" in response.json()["detail"]

def test_order_insufficient_stock():
    client.post("/inventory/", json={
        "product_name": "Bread",
        "sku": "SKU006",
        "quantity": 2,
        "unit_price": 1.0
    })
    response = client.post("/orders/", json={
        "user_id": "test_user_03",
        "total_amount": 5.0,
        "items": [{"product_name": "Bread", "quantity": 5}]
    })
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]
'''


def _files(bad=BAD_INVENTORY_V24, conftest=CONFTEST_OK):
    return {
        "backend/__init__.py": "",
        "tests/__init__.py": "",
        "tests/conftest.py": conftest,
        "tests/test_orders.py": ORDERS_OK,
        "tests/test_inventory.py": bad,
    }


def _base_paths(files):
    # 模拟 gate()：tests/test_inventory.py 是本次新增，其余都在 base 里
    return set(files) - {"tests/test_inventory.py"}


# ── 1. 启用边界：题面显式夹具约束 ────────────────────────────────────

def test_fixture_round_boundary():
    assert dg._g1043_fixture_round(R8_REQ) is True
    for req in ("", PLAIN_REQ, R5_REQ, R6_REQ, R9_REQ, R10_REQ):
        assert dg._g1043_fixture_round(req) is False, req[:30]
    # 防 user_request 被截断：只保留开头也应命中
    assert dg._g1043_fixture_round("给 ShopFlow 电商系统增加「库存管理」模块") is True


def test_judging_prompt_contract_not_relaxed():
    """题面契约未被放宽：R8 仍显式声明 conftest 夹具已建好表。"""
    obs = _load_observe_module()
    p = obs.PROMPT_ROUND_8
    assert "夹具已建好表" in p
    assert "不要改动 tests/conftest.py" in p
    assert "tests/test_inventory.py" in p


def test_conftest_detection():
    assert dg._g1043_conftest_has_client_fixture(CONFTEST_OK) is True
    assert dg._g1043_conftest_has_client_fixture(CONFTEST_NO_FIXTURE) is False
    assert dg._g1043_conftest_has_client_fixture(None) is False
    assert dg._g1043_conftest_has_client_fixture(123) is False


# ── 2. AST 扫描与改写：v24 真实违规生成物 ────────────────────────────

def test_scan_detects_v24_module_client_and_bare_tests():
    assign_lines, staged, safe = dg._g1043_scan(BAD_INVENTORY_V24)
    assert safe is True
    assert assign_lines == {5}
    assert len(staged) == 8
    # staged 全部是「无 client 参数」的 test 函数（v24 里都是无参 def）
    assert all(raw_params.strip() == "" for _, raw_params in staged)


def test_rewrite_injects_client_and_comments_assignment():
    assign_lines, staged, safe = dg._g1043_scan(BAD_INVENTORY_V24)
    ns = dg._g1043_rewrite(BAD_INVENTORY_V24, assign_lines, staged)
    tree = ast.parse(ns)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(fns) == 8
    assert all("client" in [a.arg for a in n.args.args] for n in fns)
    # 模块级 client = TestClient(app) 赋值已消失（改为注释）
    assert not any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "client" for t in n.targets)
        for n in tree.body
    )
    assert "# G10.43" in ns
    # 不增删行，保持 lineno 稳定
    assert len(ns.splitlines()) == len(BAD_INVENTORY_V24.splitlines())


def test_repair_v24_end_to_end():
    files = _files()
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert len(fixes) == 1
    assert "G10.43" in fixes[0]
    assert "8 个 test 补 client 参数" in fixes[0]
    ns = out["tests/test_inventory.py"]
    assert ns != BAD_INVENTORY_V24
    assert all("client" in [a.arg for a in n.args.args]
               for n in ast.parse(ns).body if isinstance(n, ast.FunctionDef))
    # 其余文件一字不动
    for p in ("tests/conftest.py", "tests/test_orders.py",
              "backend/__init__.py", "tests/__init__.py"):
        assert out[p] == files[p], p


# ── 3. 不误伤边界 ────────────────────────────────────────────────────

def test_non_r8_request_untouched():
    files = _files()
    for req in ("", PLAIN_REQ, R5_REQ, R6_REQ, R9_REQ, R10_REQ):
        out, fixes = dg._repair_new_test_db_isolation(
            files, req, _base_paths(files))
        assert fixes == [], req[:30]
        assert out["tests/test_inventory.py"] == BAD_INVENTORY_V24


def test_missing_conftest_client_fixture_untouched():
    files = _files(conftest=CONFTEST_NO_FIXTURE)
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert fixes == []
    assert out["tests/test_inventory.py"] == BAD_INVENTORY_V24


def test_non_new_test_file_untouched():
    """R9/R10 时 test_inventory.py 已在 base 里（非新增）→ 守卫不介入。"""
    files = _files()
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, set(files))
    assert fixes == []
    assert out["tests/test_inventory.py"] == BAD_INVENTORY_V24


def test_conftest_and_compliant_baseline_never_rewritten():
    files = _files()
    out, _ = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert out["tests/conftest.py"] == CONFTEST_OK
    assert out["tests/test_orders.py"] == ORDERS_OK


def test_compliant_new_test_untouched():
    """新建测试本来就接 client 参数 → 无 staged，不改。"""
    good = '''from fastapi.testclient import TestClient

def test_a(client: TestClient):
    assert client.get("/x/").status_code == 200
'''
    files = _files(bad=good)
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert fixes == []
    assert out["tests/test_inventory.py"] == good


# ── 4. FAIL-CLOSED：无法保证安全的复杂生成物一律放弃 ─────────────────

def test_non_test_helper_function_is_skipped():
    """有非 test 辅助函数引用裸 client → 改写会制造 NameError，放弃。"""
    src = '''from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def _helper():
    return client.get("/inventory/")

def test_a():
    assert _helper().status_code == 200
'''
    _, _, safe = dg._g1043_scan(src)
    assert safe is False
    files = _files(bad=src)
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert fixes == []
    assert out["tests/test_inventory.py"] == src


def test_multiline_def_is_skipped():
    src = '''from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def test_a(
):
    assert client.get("/inventory/").status_code == 200
'''
    _, _, safe = dg._g1043_scan(src)
    assert safe is False


def test_star_args_is_skipped():
    src = '''from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)

def test_a(*args):
    assert client.get("/inventory/").status_code == 200
'''
    _, _, safe = dg._g1043_scan(src)
    assert safe is False


def test_syntax_error_source_untouched():
    src = "def test_a(:\n    pass\n"
    _, _, safe = dg._g1043_scan(src)
    assert safe is False
    files = _files(bad=src)
    out, fixes = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert fixes == []


def test_no_module_client_assignment_untouched():
    src = '''from fastapi.testclient import TestClient
from backend.main import app

def test_a(TestClient=TestClient, app=app):
    c = TestClient(app)
    assert c.get("/inventory/").status_code == 200
'''
    _, _, safe = dg._g1043_scan(src)
    assert safe is False


# ── 5. 幂等 / 落盘清单一致性 / gate 接入 ──────────────────────────────

def test_idempotent():
    files = _files()
    out1, f1 = dg._repair_new_test_db_isolation(files, R8_REQ, _base_paths(files))
    assert f1
    out2, f2 = dg._repair_new_test_db_isolation(out1, R8_REQ, _base_paths(files))
    assert f2 == []
    assert out2["tests/test_inventory.py"] == out1["tests/test_inventory.py"]


def test_delivery_manifest_matches_verified_candidate():
    """成长法第 35 条：已验证候选必须与最终落盘清单是同一对象。"""
    files = _files()
    ops = [{"op": "create", "path": "tests/test_inventory.py",
            "content": BAD_INVENTORY_V24, "file_type": "file"}]
    ctx = {"final_file_ops": ops}
    candidate = build_candidate(files, ops)
    fixed, fixes = dg._repair_new_test_db_isolation(
        candidate, R8_REQ, _base_paths(files))
    assert fixes
    dg._apply_back(ctx, fixed, files)
    delivered = build_candidate(files, ctx["final_file_ops"])
    assert delivered["tests/test_inventory.py"] == fixed["tests/test_inventory.py"]


def test_gate_wires_g1043_into_fixes_and_repair_loop():
    src = inspect.getsource(dg.gate)
    assert "_repair_new_test_db_isolation" in src
    assert "isolation_fixes" in src
    assert "isolation" in src
    assert src.count("_repair_new_test_db_isolation") >= 2  # 主链 + 逐轮重对齐


# ── 6. 真实 pytest 对照：改写前跨轮红 / 改写后跨轮绿 ─────────────────
# 自包含最小项目：backend/main.py 用文件 store.json 持久化（精确复刻
# backend/shopflow.db 跨进程残留）；conftest 的 client fixture 用
# monkeypatch 把 store 切到 tmp_path 独立文件（精确复刻 :memory: 隔离）。

MAIN_MINI = '''import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
STORE_FILE = os.path.join(os.path.dirname(__file__), "store.json")


def _load():
    try:
        with open(STORE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(d):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)


class InvIn(BaseModel):
    product_name: str
    quantity: int


@app.post("/inventory/")
def create(inv: InvIn):
    d = _load()
    if inv.product_name in d:
        raise HTTPException(400, "already exists")
    d[inv.product_name] = inv.quantity
    _save(d)
    return {"product_name": inv.product_name, "quantity": inv.quantity}
'''

CONFTEST_MINI = '''import pytest
from fastapi.testclient import TestClient
import backend.main as m


@pytest.fixture(scope="function")
def client(tmp_path, monkeypatch):
    # 每个测试用独立临时 store，模拟 conftest 的 :memory: 隔离
    monkeypatch.setattr(m, "STORE_FILE", str(tmp_path / "store.json"))
    with TestClient(m.app) as c:
        yield c
'''

BAD_INVENTORY_MINI = '''import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_create_inventory():
    r = client.post("/inventory/", json={"product_name": "Apple", "quantity": 100})
    assert r.status_code == 200
'''


def _write_mini_project(root: Path, test_src: str):
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "main.py").write_text(MAIN_MINI, encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(CONFTEST_MINI, encoding="utf-8")
    (root / "tests" / "test_inventory.py").write_text(test_src, encoding="utf-8")


def _run_pytest_twice(root: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    results = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--disable-warnings"],
            cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
        )
        results.append((r.returncode, r.stdout))
    return results


def test_real_pytest_isolation_control_vs_g1043(tmp_path):
    # 先由守卫产出改写后的测试源码
    files = {
        "tests/conftest.py": CONFTEST_MINI,
        "tests/test_inventory.py": BAD_INVENTORY_MINI,
    }
    fixed, fixes = dg._repair_new_test_db_isolation(
        files, R8_REQ, {"tests/conftest.py"})
    assert fixes, "守卫应改写精简版违规生成物"
    good = fixed["tests/test_inventory.py"]
    assert "def test_create_inventory(client):" in good

    ctrl = tmp_path / "ctrl"
    ctrl.mkdir()
    _write_mini_project(ctrl, BAD_INVENTORY_MINI)
    ctrl_res = _run_pytest_twice(ctrl)

    fix = tmp_path / "fix"
    fix.mkdir()
    _write_mini_project(fix, good)
    fix_res = _run_pytest_twice(fix)

    # 未改写：第 1 遍可能因空 store 绿，但文件 store 残留后至少第 2 遍红
    assert any(rc != 0 for rc, _ in ctrl_res), (
        f"对照组应复现跨轮残留失败：{ctrl_res}")
    # 改写后：连跑两遍都必须全绿
    assert all(rc == 0 for rc, _ in fix_res), (
        f"G10.43 改写后应连跑两遍全绿：{fix_res}")
