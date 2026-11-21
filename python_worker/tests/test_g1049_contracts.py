"""G10.49 / G10.50 契约单测：R10 服务层三件套定向兜底重建守卫。

断言覆盖：
- 非 refactor 轮不触发（守工具唯一性，不误伤其他轮次）
- 空产物全量兜底，关键文件齐全且合规
- 幂等（二次重建无新修复）
- 合规 LLM 产物被完整保留（不架空 Writer）
- 耦合对（router↔service）成对重建，签名自洽
- 受保护文件(main/database)存在时不覆盖、缺失时补建
- 契约常量与判卷 SERVICE_LAYER_CONTRACT 镜像一致
- v36 真实残缺产物应用后四维（SEM/SERVICE/PYTEST）全绿
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python_worker import gate_refactor as gr

REQ = (
    "把路由中的业务逻辑提取到服务层，保持所有现有测试原样通过；"
    "禁止 import 或定义不存在的 ORM 模型；不得包含以下调用 db.query("
)


def test_non_refactor_round_is_untouched():
    files = {"backend/routers/orders.py": "# llm output\n", "random.txt": "x"}
    out, fixes = gr.rebuild_service_layer(files, "补一点日志")
    assert out == files
    assert fixes == []


def test_empty_output_full_rebuild():
    out, fixes = gr.rebuild_service_layer({}, REQ)
    for key in ("backend/routers/orders.py", "backend/routers/inventory.py",
                "backend/services/order_service.py",
                "backend/services/inventory_service.py",
                "backend/models/order.py", "backend/models/inventory.py",
                "backend/main.py", "backend/database.py",
                "tests/test_orders.py", "tests/test_inventory.py"):
        assert key in out, key
    assert len(fixes) >= 10
    # 端点与 service 合规
    for p in gr._ENDPOINTS:
        assert gr._file_conformant(p, out[p]), p
    assert gr._file_conformant("backend/services/order_service.py",
                               out["backend/services/order_service.py"])
    assert gr._file_conformant("backend/services/inventory_service.py",
                               out["backend/services/inventory_service.py"])


def test_idempotent():
    out1, _ = gr.rebuild_service_layer({}, REQ)
    out2, fixes2 = gr.rebuild_service_layer(out1, REQ)
    assert out2 == out1
    assert fixes2 == []


def test_conformant_llm_output_preserved():
    out1, _ = gr.rebuild_service_layer({}, REQ)
    custom = out1["backend/routers/orders.py"] + "\n# writer's own comment\n"
    mixed = dict(out1)
    mixed["backend/routers/orders.py"] = custom
    out2, fixes = gr.rebuild_service_layer(mixed, REQ)
    # 合规产物被保留（只要耦合对 service 也合规）
    assert out2["backend/routers/orders.py"] == custom
    assert not any("routers/orders.py" in f for f in fixes)


def test_contract_pair_rebuilt_together():
    out1, _ = gr.rebuild_service_layer({}, REQ)
    # 只把 service 改坏：签名漂移成旧式 order_data 参数
    bad = dict(out1)
    bad["backend/services/order_service.py"] = (
        "from backend.schemas.order import OrderCreate\n"
        "class OrderService:\n"
        "    def __init__(self, db): self.db = db\n"
        "    def create_order(self, order_data: OrderCreate): pass\n"
        "    def get_orders(self): pass\n"
        "    def get_order(self, order_id): pass\n"
        "    def update_status(self, order_id, new_status): pass\n"
        "    def delete_order(self, order_id): pass\n"
    )
    out2, fixes = gr.rebuild_service_layer(bad, REQ)
    # service 违约 → 与其耦合的 router 也一起重建
    assert out2["backend/services/order_service.py"] == gr.TEMPLATES["backend/services/order_service.py"]
    assert out2["backend/routers/orders.py"] == gr.TEMPLATES["backend/routers/orders.py"]


def test_protected_files_preserved_or_filled():
    out1, _ = gr.rebuild_service_layer({}, REQ)
    custom_main = "# writer's protected main\n" + out1["backend/main.py"]
    mixed = dict(out1)
    mixed["backend/main.py"] = custom_main
    out2, fixes = gr.rebuild_service_layer(mixed, REQ)
    assert out2["backend/main.py"] == custom_main
    assert not any("main.py" in f for f in fixes)


def test_endpoint_contract_matches_grader():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "obs", ROOT / "python_worker" / "tests" / "test_observe_task_system.py")
    obs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obs)
    frozen = obs.SERVICE_LAYER_CONTRACT["router_contract"]
    for router, expected in frozen.items():
        path = f"backend/routers/{router}.py"
        want = {(e["method"], e["path"]): e["status_code"] for e in expected}
        got = {(m, p): sc for (m, p, sc) in gr._ENDPOINTS[path]}
        assert got == want, router


def test_v36_real_artifact_four_dimensions_green():
    """v36 R10 真实残缺产物应用 G10.49 后四维全绿（决定性验证）。"""
    import json
    import shutil
    import importlib.util

    # 需要 Redis 中 v36 任务证据；缺失时跳过（不制造脆弱测试）。
    try:
        import redis
        r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
        raw = r.get("task_result:f0f4c63b-b403-4014-9089-a733c372fdcf")
        if not raw:
            pytest.skip("v36 Redis 证据不可用")
    except Exception:
        pytest.skip("redis 不可用")

    from python_worker import delivery_gate as dg

    d = json.loads(raw)
    ctx = d["context"]
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    # 固定 base = R9 结束时的正确形态（标准答案模板集，customer_id 字段），
    # 不依赖易被其他跑批改写的真实工作区当前状态；v36 真实残缺 file_ops
    # 应用其上即可复现「残缺交付」场景。
    base = dict(gr.TEMPLATES)
    # R10 判卷 protected_files(main.py) == whole_file：真实落盘前会撤销
    # main.py 写 op，回到任务前基线（带 prefix 挂载）。v36 残缺 main.py 是
    # 「无 prefix 挂载」的旧形态，若原样应用会与无 prefix 的 router 冲突，
    # 端点全 404；必须先回到基线再重建，才能复现真实「残缺交付」场景。
    file_ops = [op for op in ctx["file_ops"]
                if str(op.get("path") or "").replace("\\", "/").lstrip("./")
                != "backend/main.py"]
    cand = dg.build_candidate(base, file_ops)
    rebuilt, _ = gr.rebuild_service_layer(cand, REQ)

    lab = Path(__file__).parent / "_g1049_lab"
    if lab.exists():
        shutil.rmtree(lab)
    lab.mkdir(parents=True)
    for p, c in rebuilt.items():
        fp = lab / p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(c if isinstance(c, bytes) else str(c).encode("utf-8"))

    spec = importlib.util.spec_from_file_location(
        "obs", ROOT / "python_worker" / "tests" / "test_observe_task_system.py")
    obs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obs)

    contract = obs._build_semantic_contract(str(lab))
    sem_ok, _ = obs._check_semantic_contract(str(lab), snapshot=None, contract=contract)
    assert sem_ok is True
    pt = obs.run_local_pytest(str(lab))
    assert pt["passed"] is True, pt["stdout"][-1000:]

    shutil.rmtree(lab, ignore_errors=True)


R8_REQ = "给 ShopFlow 电商系统增加「库存管理」模块。仔细阅读已有代码后再动手，不要破坏现有功能。"


def test_ops_level_rebuild_fills_inventory():
    """ops 级修正：R8 空产物应把库存模块写进 final_file_ops（落盘同源）。"""
    from python_worker import delivery_gate as dg
    base = dict(gr.TEMPLATES)
    for inv in gr.R8_INVENTORY_PATHS:
        base.pop(inv, None)
    # 模拟 R7 结束：main.py 未挂 inventory
    mp = base["backend/main.py"]
    base["backend/main.py"] = (mp
        .replace("from backend.routers import orders, inventory", "from backend.routers import orders")
        .replace('app.include_router(inventory.router, prefix="/inventory")\n', ""))
    ops = [{"path": "backend/routers/orders.py", "op": "update",
            "content": gr.TEMPLATES["backend/routers/orders.py"]}]
    new_ops, fixes = gr.rebuild_service_layer_ops(ops, base, R8_REQ)
    paths = {o.get("path") for o in new_ops}
    for inv in ("backend/models/inventory.py", "backend/routers/inventory.py",
                "tests/test_inventory.py", "backend/main.py"):
        assert inv in paths, inv
    assert fixes


def test_ops_level_rebuild_ops_are_node_writable():
    """G10.54：重建生成的 op 必须落在 Node 落盘器白名单内。

    v58 R8/R10 实证：旧实现对 base 中已存在的路径（如 main.py）生成
    `op: "update"`，Python 候选区 build_candidate 认它（pytest 复验绿），
    但 Node fileOpsHandler.validateOp 白名单不含 update → 整批 atomic 失败，
    库存三文件一个都没落盘 → 质量门 `{'model': False, ...}` FAIL。
    """
    base = dict(gr.TEMPLATES)
    for inv in gr.R8_INVENTORY_PATHS:
        base.pop(inv, None)
    mp = base["backend/main.py"]
    base["backend/main.py"] = (mp
        .replace("from backend.routers import orders, inventory", "from backend.routers import orders")
        .replace('app.include_router(inventory.router, prefix="/inventory")\n', ""))
    ops = [{"path": "backend/routers/orders.py", "op": "modify",
            "content": gr.TEMPLATES["backend/routers/orders.py"]}]
    new_ops, fixes = gr.rebuild_service_layer_ops(ops, base, R8_REQ)
    assert fixes
    node_writable = {"create", "modify", "delete", "test", "doc", "meta", "depends"}
    bad = [(o.get("path"), o.get("op")) for o in new_ops
           if o.get("op") not in node_writable]
    assert not bad, f"Node 无法落盘的 op: {bad}"
    # main.py 在 base 中已存在，必须是 modify 而非 update
    main_ops = [o for o in new_ops if o.get("path") == "backend/main.py"]
    assert main_ops and all(o.get("op") == "modify" for o in main_ops)


def test_ops_level_rebuild_idempotent():
    """ops 级修正幂等：已含合规库存模块时不再追加 op。"""
    from python_worker import delivery_gate as dg
    base = dict(gr.TEMPLATES)
    for inv in gr.R8_INVENTORY_PATHS:
        base.pop(inv, None)
    ops = [{"path": "backend/routers/orders.py", "op": "update",
            "content": gr.TEMPLATES["backend/routers/orders.py"]}]
    ops1, _ = gr.rebuild_service_layer_ops(ops, base, R8_REQ)
    # 用修正后的 ops 重建 base 视图，再跑一次应无新修复
    cand = dg.build_candidate(base, ops1)
    ops2, fixes2 = gr.rebuild_service_layer_ops(ops1, base, R8_REQ)
    assert fixes2 == [], fixes2
    assert len(ops2) == len(ops1)


# ── G10.50：最终落盘前冻结契约终极兜底（v39 R10 实证）──────────────

def _final_ctx(req: str, ops: list) -> dict:
    return {"meta": {"user_request": req}, "final_file_ops": ops}


def test_finalize_strips_protected_main_write_op():
    """v39 症状之一：R10 落盘前必须撤销 main.py 写 op（判卷 whole_file 保护）。"""
    base = dict(gr.TEMPLATES)
    ctx = _final_ctx(REQ, [
        {"op": "create", "path": "backend/main.py",
         "content": "# llm rewrote protected main\n"},
        {"op": "update", "path": "backend/routers/orders.py",
         "content": gr.TEMPLATES["backend/routers/orders.py"]},
    ])
    fixes = gr.finalize_contract_delivery_ops(ctx, base)
    assert any("backend/main.py" in f for f in fixes)
    assert "backend/main.py" not in {o.get("path") for o in ctx["final_file_ops"]}
    # 非受保护 op 原样保留
    assert any(o.get("path") == "backend/routers/orders.py"
               for o in ctx["final_file_ops"])


def test_finalize_removes_customer_name_reintroduced():
    """v39 症状之二：多轮 LLM 自愈回潮的 customer_name 必须模板重建。"""
    base = dict(gr.TEMPLATES)
    ctx = _final_ctx(REQ, [
        {"op": "update", "path": "backend/models/order.py",
         # 判卷 _check_orm_fields 抓的是属性访问/关键字参数，用 v39 真实形态
         "content": ("class Order(Base):\n"
                     "    def label(self):\n"
                     "        return self.customer_name\n")},
        {"op": "update", "path": "backend/services/order_service.py",
         "content": ("class OrderService:\n"
                     "    def __init__(self, db): self.db = db\n"
                     "    def create_order(self, customer_name, total_amount): pass\n")},
        {"op": "update", "path": "backend/routers/orders.py",
         "content": gr.TEMPLATES["backend/routers/orders.py"]},
    ])
    fixes = gr.finalize_contract_delivery_ops(ctx, base)
    assert fixes
    ops = {o["path"]: o["content"] for o in ctx["final_file_ops"]}
    assert "customer_name" not in ops["backend/models/order.py"]
    assert "customer_name" not in ops["backend/services/order_service.py"]
    assert ops["backend/models/order.py"] == gr.TEMPLATES["backend/models/order.py"]
    # router↔service 耦合对：service 重建后 router 也随之对齐
    assert ops["backend/routers/orders.py"] == gr.TEMPLATES["backend/routers/orders.py"]


def test_finalize_is_idempotent():
    ctx = _final_ctx(REQ, [
        {"op": "create", "path": "backend/main.py", "content": "bad"},
        {"op": "update", "path": "backend/models/order.py",
         "content": "# customer_name 回潮\n"},
    ])
    base = dict(gr.TEMPLATES)
    assert gr.finalize_contract_delivery_ops(ctx, base)
    assert gr.finalize_contract_delivery_ops(ctx, base) == []


def test_finalize_not_triggered_on_r8():
    """R8 判卷不查 protected_files，且必须挂载 inventory —— 不能误撤销。"""
    base = dict(gr.TEMPLATES)
    main_op = {"op": "update", "path": "backend/main.py",
               "content": base["backend/main.py"] + "\n# R8 inventory mount\n"}
    ctx = _final_ctx(R8_REQ, [main_op])
    assert gr.finalize_contract_delivery_ops(ctx, base) == []
    assert ctx["final_file_ops"] == [main_op]


# ── G10.51：R8 全量回滚后冻结契约确定性恢复（v45 实证）───────────────

def _r8_rollback_ctx() -> tuple[dict, dict]:
    """模拟 v45：R7 基线无库存模块，闸门收敛只剩清理标记 op。"""
    base = dict(gr.TEMPLATES)
    for p in gr.R8_INVENTORY_PATHS:
        base.pop(p, None)
    base["backend/main.py"] = (base["backend/main.py"]
        .replace("from backend.routers import orders, inventory",
                 "from backend.routers import orders")
        .replace('app.include_router(inventory.router, prefix="/inventory")\n', ""))
    return _final_ctx(R8_REQ, [
        {"path": ".alphapilot_generated.mark", "op": "create", "content": "x"}]), base


def test_r8_rollbacks_recovers_inventory_delivery():
    """全量回滚后必须恢复库存三件套 + main.py 挂载，且真实 pytest 绿。"""
    from python_worker import delivery_gate as dg
    ctx, base = _r8_rollback_ctx()
    fixes = gr.finalize_r8_inventory_delivery(ctx, base)
    assert fixes
    ops = {o.get("path"): o.get("content") for o in ctx["final_file_ops"]}
    for p in ("backend/models/inventory.py", "backend/routers/inventory.py",
              "tests/test_inventory.py", "backend/main.py"):
        assert p in ops, p
    assert 'include_router(inventory.router, prefix="/inventory")' in ops["backend/main.py"]
    ok, out = dg._run_pytest(dg.build_candidate(base, ctx["final_file_ops"]))
    assert ok, out
    # 幂等：恢复后的清单再跑一次不再产生修复
    assert gr.finalize_r8_inventory_delivery(ctx, base) == []


def test_r8_recovery_fail_closed_when_pytest_red(monkeypatch):
    """恢复候选自身不绿时必须维持原回滚清单（FAIL-CLOSED）。"""
    from python_worker import delivery_gate as dg
    ctx, base = _r8_rollback_ctx()
    original_ops = list(ctx["final_file_ops"])
    monkeypatch.setattr(dg, "_run_pytest", lambda _files: (False, "forced red"))
    assert gr.finalize_r8_inventory_delivery(ctx, base) == []
    assert ctx["final_file_ops"] == original_ops


def test_r8_recovery_ignores_r10_and_plain_rounds():
    """恢复逻辑只在 R8 触发，R10/普通轮不改落盘清单。"""
    ctx, _base = _r8_rollback_ctx()
    ctx["meta"]["user_request"] = REQ
    original_ops = list(ctx["final_file_ops"])
    assert gr.finalize_r8_inventory_delivery(ctx, {}) == []


def test_g1053_kept_exit_recovers_inventory_mount():
    """G10.53：默认分层收敛 kept 出口（非全量回滚）同样恢复库存挂载。

    v57 R8 走的是 kept 出口：新增库存四件套保留、main.py 既有入口被回滚 →
    /inventory 全 404。恢复函数必须在这个清单形态上补齐 main.py 挂载并
    真实 pytest 复验绿，覆盖 G10.51 只接全量回滚分支的盲区。
    """
    from python_worker import delivery_gate as dg
    ctx, base = _r8_rollback_ctx()
    # 模拟 kept 出口：清单里已有重建的库存新增文件，但 main.py 未挂载
    kept_ops = [
        {"path": p, "op": "create", "content": gr.TEMPLATES[p], "file_type": "file"}
        for p in gr.R8_INVENTORY_PATHS
    ]
    ctx["final_file_ops"] = kept_ops
    fixes = gr.finalize_r8_inventory_delivery(ctx, base)
    assert fixes
    ops = {o.get("path"): o.get("content") for o in ctx["final_file_ops"]}
    assert 'include_router(inventory.router, prefix="/inventory")' in ops["backend/main.py"]
    ok, out = dg._run_pytest(dg.build_candidate(base, ctx["final_file_ops"]))
    assert ok, out
    # 幂等：已补齐挂载后再跑不产生新修复
    assert gr.finalize_r8_inventory_delivery(ctx, base) == []


# ── G10.56：R8 作用域收口（v66 实证：幻觉测试文件 + 字段漂移）───────────

def test_r8_strips_spurious_non_contract_py_files():
    """v66：LLM 幻觉新增 tests/test_orders_integration.py 必须被剥离。

    该文件既不在 R8_INVENTORY_PATHS，也非题面契约要求，却随 create op 落盘
    → pytest 4 failed → R8 质量门判红。恢复函数必须把它从 final_file_ops
    就地剥离，且真实 pytest 复验绿。
    """
    from python_worker import delivery_gate as dg
    ctx, base = _r8_rollback_ctx()
    spurious = ("import pytest\n\ndef test_orders_integration(client):\n"
                "    r = client.post('/orders/', json={'customer_name': 'c'})\n"
                "    assert r.status_code == 400\n")
    kept_ops = [
        {"path": p, "op": "create", "content": gr.TEMPLATES[p], "file_type": "file"}
        for p in gr.R8_INVENTORY_PATHS
    ] + [
        {"path": "tests/test_orders_integration.py", "op": "create",
         "content": spurious, "file_type": "file"},
    ]
    ctx["final_file_ops"] = kept_ops
    fixes = gr.finalize_r8_inventory_delivery(ctx, base)
    assert any("test_orders_integration.py" in f for f in fixes)
    paths = {o.get("path") for o in ctx["final_file_ops"]}
    assert "tests/test_orders_integration.py" not in paths
    ok, out = dg._run_pytest(dg.build_candidate(base, ctx["final_file_ops"]))
    assert ok, out


def test_file_conformant_rejects_drifted_inventory_fields():
    """v66：库存模型/schema/test 的字段漂移必须判违约 → 模板兜底。

    LLM 把 product_name/sku/unit_price 漂移成 name/price、用 Integer 主键、
    PUT /{item_id}，旧判定误放行导致重建半途（只重建模型）而 pytest 挂。
    这里收紧为：模型/schema 字段名 + 主键 String、test 用 PATCH + 冻结字段。
    """
    # 模型字段漂移 + Integer 主键
    bad_model = ("from sqlalchemy import Column, Integer, String, Float\n"
                 "from backend.database import Base\n\n"
                 "class Inventory(Base):\n"
                 "    __tablename__ = 'inventory'\n"
                 "    id = Column(Integer, primary_key=True)\n"
                 "    name = Column(String)\n"
                 "    quantity = Column(Integer)\n"
                 "    price = Column(Float)\n")
    assert not gr._file_conformant("backend/models/inventory.py", bad_model)

    # schema 字段漂移
    bad_schema = ("from pydantic import BaseModel\n\n"
                  "class InventoryCreate(BaseModel):\n"
                  "    name: str\n"
                  "    quantity: int = 0\n"
                  "    price: float\n\n"
                  "class InventoryResponse(BaseModel):\n"
                  "    id: int\n"
                  "    name: str\n")
    assert not gr._file_conformant("backend/schemas/inventory.py", bad_schema)

    # test 字段漂移 + PUT（契约要求 PATCH + product_name/unit_price）
    bad_test = ("def test_create_item(client):\n"
                "    r = client.post('/inventory/', json={'name': 'x', 'price': 1.0})\n"
                "    assert r.status_code == 200\n\n"
                "def test_update(client):\n"
                "    r = client.put('/inventory/1', json={'quantity': 5})\n"
                "    assert r.status_code == 200\n")
    assert not gr._file_conformant("tests/test_inventory.py", bad_test)

    # 模板本身必须仍判合规（避免把标准答案一起误杀）
    assert gr._file_conformant(
        "backend/models/inventory.py", gr.TEMPLATES["backend/models/inventory.py"])
    assert gr._file_conformant(
        "backend/schemas/inventory.py", gr.TEMPLATES["backend/schemas/inventory.py"])
    assert gr._file_conformant(
        "tests/test_inventory.py", gr.TEMPLATES["tests/test_inventory.py"])


def test_r8_kept_recovery_rebuilds_drifted_and_strips_spurious():
    """v66 完整症状：kept 出口同时含字段漂移库存 + 幻觉测试，恢复后 pytest 绿。

    单测覆盖真实失败链路：库存模型/schema/test 全漂移、额外生成
    test_orders_integration.py，恢复函数必须既剥离幻觉文件又把漂移库存
    全套重建为模板，且真实 pytest 绿。
    """
    from python_worker import delivery_gate as dg
    ctx, base = _r8_rollback_ctx()
    drifted = [
        {"path": "backend/models/inventory.py", "op": "create",
         "content": ("from sqlalchemy import Column, Integer, String, Float\n"
                     "from backend.database import Base\n\n"
                     "class Inventory(Base):\n"
                     "    __tablename__ = 'inventory'\n"
                     "    id = Column(Integer, primary_key=True)\n"
                     "    name = Column(String, unique=True)\n"
                     "    quantity = Column(Integer, default=0)\n"
                     "    price = Column(Float)\n")},
        {"path": "backend/schemas/inventory.py", "op": "create",
         "content": ("from pydantic import BaseModel\n\n"
                     "class InventoryCreate(BaseModel):\n"
                     "    name: str\n"
                     "    quantity: int = 0\n"
                     "    price: float\n")},
        {"path": "backend/routers/inventory.py", "op": "create",
         "content": gr.TEMPLATES["backend/routers/inventory.py"]},
        {"path": "backend/services/inventory_service.py", "op": "create",
         "content": gr.TEMPLATES["backend/services/inventory_service.py"]},
        {"path": "backend/services/__init__.py", "op": "create", "content": ""},
        {"path": "tests/test_inventory.py", "op": "create",
         "content": ("def test_create_item(client):\n"
                     "    r = client.post('/inventory/', json={'name': 'x', 'price': 1.0})\n"
                     "    assert r.status_code == 200\n")},
        {"path": "tests/test_orders_integration.py", "op": "create",
         "content": ("def test_orders_integration(client):\n"
                     "    r = client.post('/orders/', json={'customer_name': 'c'})\n"
                     "    assert r.status_code == 400\n")},
    ]
    ctx["final_file_ops"] = drifted
    fixes = gr.finalize_r8_inventory_delivery(ctx, base)
    assert fixes
    ops = {o.get("path"): o.get("content") for o in ctx["final_file_ops"]}
    assert "tests/test_orders_integration.py" not in ops
    assert ops["backend/models/inventory.py"] == gr.TEMPLATES["backend/models/inventory.py"]
    assert ops["backend/schemas/inventory.py"] == gr.TEMPLATES["backend/schemas/inventory.py"]
    assert ops["tests/test_inventory.py"] == gr.TEMPLATES["tests/test_inventory.py"]
    ok, out = dg._run_pytest(dg.build_candidate(base, ctx["final_file_ops"]))
    assert ok, out