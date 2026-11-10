# -*- coding: utf-8 -*-
"""
test_observe_task_system.py — AlphaPilot 真实链路端到端观察测试
─────────────────────────────────────────────────────────────────
用途：模拟 VSCode Extension 用户输入，经过完整生产执行链：
      POST /task/submit → Node.js API → Redis → Worker → LLM
      → FileOps → pytest → stream_chunk → /task/notify → 结果观察

前置条件（测试启动前必须手动启动）：
  1. Node.js API:  cd node-api && node index.js    (默认 http://localhost:3000)
  2. Redis:        docker run -p 6379:6379 redis   (或本地 redis-server)
  3. Worker:       python -m python_worker.agents.qwen.qwen_worker_v2
                   (需设置环境变量 LLM_PROVIDER=modelscope)

运行方式：
  python -m pytest tests/test_observe_task_system.py -v --tb=short -s 2>&1

🏪 ShopFlow 电商项目 — 6 轮贯穿测试
─────────────────────────────────────────────
Round 5: architecture   → 架构设计（Markdown，不写代码）
Round 6: write_code     → 核心实现（Order + CRUD + pytest）
Round 7: fix_code       → Bug 精准修复（真实 traceback → 定位 → 修复）
Round 8: write_code     → 增量功能追加（库存系统，阅读已有代码后扩展）
Round 9: refactor       → 跨文件级联修改（改枚举值，4+ 文件同步变更）
Round 10: refactor      → 重构提取服务层（router → service，不破坏行为）

四维验收原则：
  1. 链路成功：任务确实经过 Node.js → Redis → Worker
  2. 执行成功：Worker 确实完成了任务执行
  3. 质量成功：测试、结构和业务不变量均满足要求
  4. 治理成功：文件变更经过授权、保护、验证和审计
  四项分别记录，不能用一个 pytest passed 替代。
"""

import ast
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import subprocess
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

import pytest
import requests


# ═══════════════════════════════════════════════════════════════
# 环境配置
# ═══════════════════════════════════════════════════════════════

NODE_API_URL = os.getenv("ALPHAPILOT_NODE_API_URL", "http://localhost:3000")
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

DEFAULT_WORKSPACE = os.getenv(
    "SHOPFLOW_WORKSPACE",
    r"C:\Users\49772\Desktop\shopflow_ecommerce"
)

TASK_SUBMIT_TIMEOUT = 30       # POST /task/submit 超时（秒）
TASK_POLL_INTERVAL = 5         # Redis 轮询间隔（秒）
TASK_EXECUTION_TIMEOUT = 900   # 单轮任务最大等待时间（秒）= 15分钟
PYTEST_TIMEOUT = 120           # 本地 pytest 验证超时（秒）

SHOPFLOW_CONVERSATION_ID = f"shopflow-{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════
# ShopFlow 6 轮 Prompt（保留原有定义）
# ═══════════════════════════════════════════════════════════════

PROMPT_ROUND_5 = """为一个电商订单系统（ShopFlow）设计 backend 架构。只输出设计文档，不要写任何实现代码。

要求：
1. 模块划分：说明 models/、routers/、services/、schemas/、tests/ 各自职责
2. 数据模型设计：列出 Order、OrderItem 的字段和关系
3. OrderStatus 枚举：pending → confirmed → shipped → delivered → cancelled
4. API 契约：每个端点的 method、path、request body（如有）、response 格式
   - 创建订单 POST /orders
   - 查询订单列表 GET /orders
   - 查询单个订单 GET /orders/{order_id}
   - 更新订单状态 PATCH /orders/{order_id}/status
   - 删除订单 DELETE /orders/{order_id}
5. 数据流：请求 → 路由 → 服务层 → 数据模型 → 数据库 → 响应
6. 技术栈：FastAPI + SQLAlchemy + SQLite + pytest

输出格式：Markdown 文档，用 # FILE: 写入 architecture_design.md"""

PROMPT_ROUND_6 = """基于上一轮的架构设计，实现 ShopFlow 电商订单系统核心功能。

后端（FastAPI + SQLAlchemy + SQLite）：
1. backend/models/order.py
   - Order 模型: id (str UUID), customer_name (str), status (str, OrderStatus 枚举), total_price (float), created_at (datetime)
   - OrderItem 模型: id (str UUID), order_id (外键→Order), product_name (str), quantity (int), unit_price (float)
   - OrderStatus 枚举: pending / confirmed / shipped / delivered / cancelled

2. backend/schemas/order.py — Pydantic schemas (OrderCreate, OrderUpdate, OrderResponse)

3. backend/routers/orders.py — REST API:
   - POST /orders — 创建订单（含订单项列表）
   - GET /orders — 查询所有订单
   - GET /orders/{order_id} — 查询单个订单
   - PATCH /orders/{order_id}/status — 更新订单状态
   - DELETE /orders/{order_id} — 删除订单

4. backend/database.py — SQLAlchemy engine + SessionLocal

5. backend/main.py — FastAPI app, 注册路由, CORS, 自动建表

6. backend/__init__.py — 空文件

7. tests/test_orders.py — pytest 测试覆盖所有 API 端点:
   - 创建订单 → 201
   - 查询列表 → 200, 数据非空
   - 查询单个 → 200, 数据正确
   - 更新状态 → 200, status 已变更
   - 删除 → 200, 再次查询返回 404
   - 无效状态转换 → 422 (如从 delivered 改回 pending)

技术栈：FastAPI + SQLAlchemy + SQLite（数据库文件存于 backend/shopflow.db）+ pytest + httpx（测试客户端）

⭐⭐⭐ 文件结构强制约束（若不遵守 pytest 将失败）：
- backend/models/ 必须是目录（Python 包），内放 order.py + 空 __init__.py
- backend/schemas/ 必须是目录（Python 包），内放 order.py + 空 __init__.py  
- 禁止创建扁平的 backend/models.py 或 backend/schemas.py 单文件
- router 的 import 必须使用: from backend.models.order import Order, OrderItem, OrderStatus
- router 的 import 必须使用: from backend.schemas.order import OrderCreate, OrderResponse, OrderUpdateStatus"""

PROMPT_ROUND_7 = """运行 pytest 时出现以下错误，请定位根因并修复所有有问题的文件。

注意：
- 可能同时存在多个 Bug（包括代码生成阶段遗留的问题），请逐一排查并修复
- 从 traceback 入手，逐文件排查，找到每个错误的真正原因
- 不要猜测式修改，必须理解错误后再动手

⭐⭐⭐ 禁止操作（违反时 pytest 会失败）：
- 禁止将 backend/models/ 或 backend/schemas/ 包结构改为扁平文件
- 禁止修改 backend/main.py 中的路由注册方式
- 禁止重写测试文件（tests/）
- 禁止修改变量名、类名、数据库结构
- 只允许修改包含 bug 的源文件，且只允许最小行数变更"""

PROMPT_ROUND_8 = """给 ShopFlow 电商系统增加「库存管理」模块。仔细阅读已有代码后再动手，不要破坏现有功能。

新增内容：
1. backend/models/inventory.py
   - Inventory 模型: id (str UUID), product_name (str, 唯一), sku (str), quantity (int, 库存数量), unit_price (float)
   - 不要重复定义 Order/OrderItem 模型，从 backend.models.order 导入

2. backend/schemas/inventory.py — InventoryCreate, InventoryUpdate, InventoryResponse

3. backend/routers/inventory.py — REST API:
   - POST /inventory — 入库
   - GET /inventory — 库存列表
   - GET /inventory/{product_name} — 查询单品库存
   - PATCH /inventory/{product_name} — 更新库存

4. 下单时库存扣减——修改 POST /orders 逻辑：
   - 创建订单前先检查库存是否充足
   - 库存不足返回 400 错误
   - 下单成功后扣减对应库存

5. tests/test_inventory.py — 测试所有库存 API + 库存扣减联动

注意：不要修改 tests/test_orders.py 中已有的测试逻辑。backend/main.py 需注册 inventory 路由。backend/database.py 如使用 Base.metadata.create_all 则无需改动。"""

PROMPT_ROUND_9 = """修改 ShopFlow 的订单状态枚举值。请找出所有引用这些枚举的地方并一次性全部更新。

变更内容：
- "confirmed" → "processing" （确认 → 处理中）
- "shipped" → "in_transit" （已发货 → 运输中）
- "delivered" → "completed" （已送达 → 已完成）

要求：
1. 修改 OrderStatus 枚举定义
2. 修改所有路由中引用这些状态值的地方
3. 修改所有测试中的状态断言
4. 修改所有 schemas 中引用这些值的地方
5. 不要遗留任何旧的状态值

正确的枚举顺序应为: pending → processing → in_transit → completed → cancelled"""

# ────────────────────────────────────────────────────────────────
# R10 统一服务层契约（单一事实源）
# PROMPT 与验收测试 svc_checks 均从此契约派生，杜绝命名断裂
# ────────────────────────────────────────────────────────────────
SERVICE_LAYER_CONTRACT = {
    "order_service": {
        "class": "OrderService",
        "constant": "VALID_TRANSITIONS",
        "methods": [
            "create_order", "get_orders", "get_order",
            "update_status", "delete_order",
        ],
        "module_functions": ["get_order", "validate_transition"],
        "instance_based": True,
        "init_params": ["self", "db"],
    },
    "inventory_service": {
        "class": "InventoryService",
        "methods": [
            "create_inventory", "get_inventory_list",
            "get_inventory", "update_inventory",
        ],
        "instance_based": True,
        "init_params": ["self", "db"],
    },
    "router_forbidden": [
        "db.query(", "db.add(", "db.commit(",
        "db.delete(", "db.merge(", "db.execute(",
    ],
    "order_status_values": [
        "pending", "processing", "in_transit", "completed", "cancelled",
    ],
    # ── G10.1 语义契约 ────────────────────────────────────────
    # models 字段由 _extract_model_contract 从真实 ORM 源码运行时提取（禁止硬编码）
    # 其余为冻结的负向约束/行为契约（策略常量）
    "models": {},
    "forbidden_imports": ["OrderItem"],
    "forbidden_fields": ["customer_name", "stock", "price"],
    "router_contract": {
        "orders": [
            {"method": "POST", "path": "/", "status_code": 200},
            {"method": "GET", "path": "/", "status_code": 200},
            {"method": "GET", "path": "/{order_id}", "status_code": 200},
            {"method": "PUT", "path": "/{order_id}/status", "status_code": 200},
            {"method": "DELETE", "path": "/{order_id}", "status_code": 204},
        ],
        "inventory": [
            {"method": "POST", "path": "/", "status_code": 200},
            {"method": "GET", "path": "/", "status_code": 200},
            {"method": "GET", "path": "/{product_name}", "status_code": 200},
            {"method": "PATCH", "path": "/{product_name}", "status_code": 200},
        ],
    },
    "error_messages": {
        "product_not_exist": "does not exist in inventory",
        "insufficient_stock": "Insufficient stock",
        "duplicate_product": "already exists",
    },
    "protected_files": {
        "backend/main.py": {"mode": "whole_file"},
    },
    "enum_contract": {
        "module_path": "backend/models/enums.py",
        "class_name": "OrderStatus",
        "values": ["pending", "processing", "in_transit", "completed", "cancelled"],
        "transition_method": "next_states",
    },
}

_oc = SERVICE_LAYER_CONTRACT["order_service"]
_ic = SERVICE_LAYER_CONTRACT["inventory_service"]


class ContractExtractionError(RuntimeError):
    """真实模型契约提取不完整时抛出（FAIL-CLOSED）。

    禁止在契约缺失时回退为「空模型契约」继续生成 PROMPT，
    否则模型文件读取失败反而会让 Worker 获得更宽松的执行空间。
    """


def _inherits_base(node: ast.ClassDef) -> bool:
    """判断 ORM 模型类是否继承声明式基类 Base。"""
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Base":
            return True
    return False


def _parse_column_call(value) -> dict | None:
    """解析 SQLAlchemy Column(...) 调用，提取类型/主键/nullable/默认值/JSON。"""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not (isinstance(func, ast.Name) and func.id == "Column"):
        return None
    col_type = None
    if value.args:
        first = value.args[0]
        if isinstance(first, ast.Name):
            col_type = first.id
        elif isinstance(first, ast.Attribute):
            col_type = first.attr
        elif isinstance(first, ast.Constant) and isinstance(first.value, str):
            col_type = first.value
    info = {
        "type": col_type,
        "primary_key": False,
        "nullable": True,
        "has_default": False,
        "is_json": col_type == "JSON",
    }
    for kw in value.keywords:
        if kw.arg == "primary_key":
            info["primary_key"] = bool(kw.value.value) if isinstance(kw.value, ast.Constant) else True
        elif kw.arg == "nullable":
            info["nullable"] = bool(kw.value.value) if isinstance(kw.value, ast.Constant) else True
        elif kw.arg == "default":
            info["has_default"] = True
    return info


def _looks_like_orm_declaration(value) -> bool:
    """识别暂不支持的 ORM 声明方式（如 SQLAlchemy 2.0 mapped_column）。"""
    if isinstance(value, ast.Call):
        fn = value.func
        if isinstance(fn, ast.Name) and fn.id == "mapped_column":
            return True
        if isinstance(fn, ast.Attribute) and fn.attr == "mapped_column":
            return True
    return False


def _parse_orm_class(node: ast.ClassDef, rel: str, errors: list) -> dict | None:
    """解析单个 ORM 模型类，提取 __tablename__ 与字段元数据。

    对暂不支持的声明方式报告「提取不完整」而非静默跳过。
    """
    model = {
        "tablename": None,
        "fields": {},
        "primary_key_field": None,
        "primary_key_type": None,
    }
    unsupported = []
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id == "__tablename__":
                    if isinstance(stmt.value, ast.Constant):
                        model["tablename"] = stmt.value.value
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                fname = stmt.targets[0].id
                if fname == "__tablename__":
                    continue
                col = _parse_column_call(stmt.value)
                if col is not None:
                    model["fields"][fname] = col
                    if col.get("primary_key"):
                        model["primary_key_field"] = fname
                        model["primary_key_type"] = col.get("type")
                elif _looks_like_orm_declaration(stmt.value):
                    unsupported.append(fname)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            # Mapped[...] 声明（SQLAlchemy 2.0 风格）：暂不支持，报告不完整
            unsupported.append(stmt.target.id)
    if unsupported:
        errors.append(
            f"{rel}:{node.name} 存在暂不支持的 ORM 声明方式（字段: {', '.join(sorted(set(unsupported)))}）"
        )
        return None
    if model["tablename"] is None:
        errors.append(f"{rel}:{node.name} 缺少 __tablename__ 声明")
        return None
    return model


def _extract_enum_from_file(path: Path) -> dict:
    """从枚举源码提取类名、枚举值、next_states 是否存在。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_enum = False
        for b in node.bases:
            if isinstance(b, ast.Name) and b.id in ("Enum", "enum"):
                is_enum = True
            if isinstance(b, ast.Attribute) and b.attr == "Enum":
                is_enum = True
        if not is_enum:
            continue
        values = []
        has_next_states = False
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and isinstance(stmt.value, ast.Constant):
                        values.append(stmt.value.value)
            elif isinstance(stmt, ast.FunctionDef) and stmt.name == "next_states":
                has_next_states = True
        return {
            "class_name": node.name,
            "values": values,
            "has_next_states": has_next_states,
        }
    return {"class_name": None, "values": [], "has_next_states": False}


def _extract_model_contract(ws_path) -> dict:
    """从真实 ORM 源码运行时提取模型契约（字段/类型/主键/nullable/默认值/JSON）。

    FAIL-CLOSED：任何提取不完整都记录到 extraction_errors 并使 complete=False，
    调用方必须据此中止，绝不回退为「空模型契约」给 Worker 更宽松空间。

    Returns:
        {
            "complete": bool,
            "source_files": [str, ...],
            "models": {模型名: {...}, "__enum__": {...}},
            "source_hashes": {相对路径: sha256},
            "extraction_errors": [str, ...],
        }
    """
    ws = Path(ws_path)
    model_files = [
        ws / "backend" / "models" / "order.py",
        ws / "backend" / "models" / "inventory.py",
        ws / "backend" / "models" / "enums.py",
    ]
    result = {
        "complete": True,
        "source_files": [],
        "models": {},
        "source_hashes": {},
        "extraction_errors": [],
    }

    for mf in model_files:
        try:
            rel = mf.relative_to(ws).as_posix()
        except ValueError:
            rel = mf.as_posix()
        if not mf.is_file():
            result["complete"] = False
            result["extraction_errors"].append(f"模型文件缺失: {rel}")
            continue
        raw = mf.read_bytes()
        result["source_hashes"][rel] = hashlib.sha256(raw).hexdigest()
        result["source_files"].append(rel)
        try:
            tree = ast.parse(raw.decode("utf-8"))
        except Exception as e:
            result["complete"] = False
            result["extraction_errors"].append(f"模型文件无法解析: {rel} ({e})")
            continue

        if mf.name == "enums.py":
            try:
                result["models"]["__enum__"] = _extract_enum_from_file(mf)
            except Exception as e:
                result["complete"] = False
                result["extraction_errors"].append(f"枚举提取失败: {e}")
            continue

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _inherits_base(node):
                model = _parse_orm_class(node, rel, result["extraction_errors"])
                if model is None:
                    result["complete"] = False
                else:
                    result["models"][node.name] = model

    if "Order" not in result["models"] or "Inventory" not in result["models"]:
        result["complete"] = False
        result["extraction_errors"].append(
            f"未提取到完整模型（Order/Inventory）: {sorted(k for k in result['models'] if not k.startswith('__'))}"
        )

    return result


def _build_semantic_contract(ws_path) -> dict:
    """组装语义契约：真实模型 + 冻结策略常量。

    FAIL-CLOSED：模型提取不完整时抛 ContractExtractionError。
    """
    extracted = _extract_model_contract(ws_path)
    if not extracted["complete"]:
        raise ContractExtractionError(
            "真实模型契约提取不完整，禁止生成 PROMPT："
            + " | ".join(extracted["extraction_errors"])
        )
    contract = dict(SERVICE_LAYER_CONTRACT)
    contract["models"] = extracted["models"]
    contract["_model_source_files"] = extracted["source_files"]
    contract["_model_source_hashes"] = extracted["source_hashes"]
    return contract


def _format_model_contract_block(contract: dict) -> str:
    """将运行时提取的模型契约渲染为 PROMPT 文本块。"""
    lines = [
        "【以下字段、类型、主键、nullable、默认值均从 backend/models/ 源码提取，禁止偏离、禁止虚构字段】"
    ]
    for model_name, model in contract["models"].items():
        if model_name.startswith("__"):
            continue
        lines.append(f"- {model_name}（表名: {model['tablename']}）:")
        for fname, finfo in model["fields"].items():
            flags = []
            if finfo.get("primary_key"):
                flags.append("主键")
            if not finfo.get("nullable"):
                flags.append("必填")
            if finfo.get("is_json"):
                flags.append("JSON 列")
            flag_str = f"（{', '.join(flags)}）" if flags else ""
            default_str = "，有默认值" if finfo.get("has_default") else ""
            lines.append(f"    * {fname}: {finfo.get('type') or '?'}{flag_str}{default_str}")
    return "\n".join(lines)


def build_prompt_round_10(ws_path: str) -> str:
    """从真实源码提取模型契约后，派生完整 PROMPT_ROUND_10。

    契约提取失败时 FAIL-CLOSED，绝不返回不含模型信息的 PROMPT。
    """
    contract = _build_semantic_contract(ws_path)
    model_block = _format_model_contract_block(contract)
    return _PROMPT_ROUND_10_TEMPLATE.replace("{model_contract_block}", model_block)


_PROMPT_ROUND_10_TEMPLATE = f"""重构 ShopFlow 后端：检查已有服务层，将路由中的业务逻辑提取到服务层。

请先阅读项目中已有的 backend/services/ 目录内容，确认哪些文件和方法已存在。

【统一服务层契约 —— 以下命名必须逐字一致，禁止使用别名或近义词】

1. 完善 backend/services/order_service.py（该文件已存在，不得删除或退化）：
   - 必须保留类：{_oc['class']}，且必须支持实例化 {_oc['class']}(db)
   - 必须定义状态转换常量：{_oc['constant']}（dict，键值对声明合法状态转换）
   - 必须定义模块级函数：
     * get_order(db, order_id) —— 按 id 查询单个订单并返回
     * validate_transition(current_status, new_status) -> bool —— 校验状态转换是否合法
   - 类方法命名必须精确为：{', '.join(_oc['methods'])}
     （特别注意：状态更新方法名是 update_status，不是 update_order_status）
   - 所有类方法必须是实例方法（第一个参数为 self），禁止 @staticmethod / @classmethod
   - create_order() 必须保留库存扣减逻辑（与 Inventory 表集成；库存不足或商品不存在时拒绝下单并返回 400）
   - 状态机枚举值（小写，按顺序）：{', '.join(SERVICE_LAYER_CONTRACT['order_status_values'])}
     合法转换以 {_oc['constant']} 为准；非法转换必须拒绝（例如 pending 不能直接跳到 completed）

2. 新建 backend/services/inventory_service.py（该文件不存在，需要创建）：
   - 创建类：{_ic['class']}，且必须支持实例化 {_ic['class']}(db)
   - 类方法命名必须精确为：{', '.join(_ic['methods'])}
   - 所有类方法必须是实例方法（第一个参数为 self），禁止 @staticmethod / @classmethod
   - 将 routers/inventory.py 中的数据库操作迁移过来

3. 修改 backend/routers/orders.py —— 路由只负责解析参数、调用 {_oc['class']}、返回响应，不得包含任何数据库查询或业务逻辑：
   - 端点集合必须精确为（不得新增/删除任何端点）：
     * POST /orders/ 返回 200（不是 201）
     * GET /orders/ 返回 200
     * GET /orders/<order_id> 返回 200
     * PUT /orders/<order_id>/status 返回 200，请求体 JSON 含 new_status 字段（小写状态字符串）
     * DELETE /orders/<order_id> 返回 204
   - 不得包含以下调用：{', '.join(SERVICE_LAYER_CONTRACT['router_forbidden'])}

4. 修改 backend/routers/inventory.py —— 路由只负责解析参数、调用 {_ic['class']}、返回响应：
   - 端点集合必须精确为（不得新增/删除任何端点）：
     * POST /inventory/ 返回 200
     * GET /inventory/ 返回 200（列表）
     * GET /inventory/<product_name> 返回 200
     * PATCH /inventory/<product_name> 返回 200
   - 禁止新增 /inventory/list 或任何列表专用端点（列表用 GET /inventory/）
   - 不得包含以下调用：{', '.join(SERVICE_LAYER_CONTRACT['router_forbidden'])}

5. 不改变任何外部 API 行为 —— 所有现有测试必须原样通过。

6. backend/main.py 属于受保护文件：read_root() 必须原样返回 {{"message": "ShopFlow API is running"}}，其余内容禁止修改。

{{model_contract_block}}

【禁止事项】
   - 禁止 import 或定义不存在的 ORM 模型：{', '.join(SERVICE_LAYER_CONTRACT['forbidden_imports'])}
   - 禁止使用不存在的字段名：{', '.join(SERVICE_LAYER_CONTRACT['forbidden_fields'])}（正确字段见上方模型契约）
   - 禁止改变枚举定义：backend/models/enums.py 中 {SERVICE_LAYER_CONTRACT['enum_contract']['class_name']} 枚举值必须为 {', '.join(SERVICE_LAYER_CONTRACT['enum_contract']['values'])}，状态转换复用其 {SERVICE_LAYER_CONTRACT['enum_contract']['transition_method']}() 方法
"""

# 向后兼容：PROMPT_ROUND_10 保留为模板别名（完整 PROMPT 应使用 build_prompt_round_10(ws_path) 派生）
PROMPT_ROUND_10 = _PROMPT_ROUND_10_TEMPLATE


# ═══════════════════════════════════════════════════════════════
# Redis 连接（用于轮询结果 + 审计授权）
# ═══════════════════════════════════════════════════════════════

def _get_redis():
    import redis as redis_py
    return redis_py.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_timeout=10,
        socket_connect_timeout=10,
    )


# ═══════════════════════════════════════════════════════════════
# 服务可达性检查
# ═══════════════════════════════════════════════════════════════

def _check_node_api():
    try:
        resp = requests.get(f"{NODE_API_URL}/", timeout=5)
        return True
    except Exception:
        try:
            resp = requests.get(f"{NODE_API_URL}/health", timeout=5)
            return resp.status_code < 500
        except Exception:
            return False


def _check_redis():
    try:
        r = _get_redis()
        return r.ping()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 真实链路任务提交与观察
# ═══════════════════════════════════════════════════════════════

def submit_task_via_api(
    prompt: str,
    workspace_path: str,
    task_type: str = "qwen_generate",
    collaboration_mode: str = "automatic",
    conversation_id: str | None = None,
) -> dict:
    """
    模拟 VSCode Extension 提交任务：通过 POST /task/submit 推入 Redis 队列。

    Args:
        prompt: 用户任务描述
        workspace_path: 目标工作区路径
        task_type: 任务类型（对应 Worker 队列）
        collaboration_mode: 协作模式
        conversation_id: 多轮对话 ID

    Returns:
        {
            "status": "submitted",
            "task_id": "...",
            "trace_id": "...",
        }
    """
    payload = {
        "type": task_type,
        "payload": {
            "prompt": prompt,
            "workspace_path": str(workspace_path),
            "collaboration_mode": collaboration_mode,
        },
        "source": "vscode-plugin",
        "meta": {
            "user_id": "test-runner",
            "project_id": "shopflow-ecommerce",
        },
    }

    if conversation_id:
        payload["conversation_id"] = conversation_id

    print(f"\n📤 [API] 提交任务到 {NODE_API_URL}/task/submit ...")
    print(f"   type={task_type}, prompt={len(prompt)} chars, workspace={workspace_path}")

    try:
        resp = requests.post(
            f"{NODE_API_URL}/task/submit",
            json=payload,
            timeout=TASK_SUBMIT_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()

        task_id = result.get("task_id")
        status = result.get("status", "")

        if status == "confirmation_required":
            confirm_id = result.get("confirmation", {}).get("confirmation_id", "")
            print(f"   🔔 [API] 需要确认: {confirm_id}")
            confirm_resp = requests.post(
                f"{NODE_API_URL}/task/confirm",
                json={"confirmation_id": confirm_id, "task_id": task_id},
                timeout=TASK_SUBMIT_TIMEOUT,
            )
            confirm_resp.raise_for_status()
            confirm_result = confirm_resp.json()
            print(f"   ✅ [API] 已确认 → 任务提交: task_id={task_id}")

        print(f"   ✅ [API] 任务已提交: task_id={task_id}")
        print(f"   queue={result.get('queue', 'N/A')}, model={result.get('model', 'N/A')}")
        return result
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"无法连接 Node.js API ({NODE_API_URL})。"
            f"请确认 Node API 已启动: cd node-api && node index.js"
        )
    except requests.exceptions.HTTPError as e:
        err_body = e.response.text[:500] if e.response else str(e)
        raise RuntimeError(f"Node API 返回错误 ({e.response.status_code}): {err_body}")


def poll_task_result(
    task_id: str,
    timeout_seconds: int = TASK_EXECUTION_TIMEOUT,
    poll_interval: int = TASK_POLL_INTERVAL,
) -> dict | None:
    """
    轮询 Redis 等待 Worker 完成任务，返回 result_data。

    Worker 完成时写入 redis key: task_result:{task_id}

    Returns:
        result_data dict 或超时返回 None
    """
    result_key = f"task_result:{task_id}"
    r = _get_redis()
    started = time.monotonic()

    print(f"\n⏳ [POLL] 等待 Worker 完成 {task_id} ...")

    while (time.monotonic() - started) < timeout_seconds:
        try:
            raw = r.get(result_key)
            if raw:
                elapsed = time.monotonic() - started
                print(f"   ✅ [POLL] 结果就绪 ({elapsed:.1f}s)")
                result = json.loads(raw)
                # ⚠️ Race Condition 防御：
                # Worker 写 Redis 后异步调 /task/notify 写盘，
                # 等待 5s 确保 Node.js FileOpsHandler 写盘完成
                print(f"   ⏳ [WAIT] 等待 5s 确保 /task/notify 写盘完成...")
                time.sleep(5)
                return result
        except Exception as e:
            print(f"   ⚠️ [POLL] Redis 读取异常: {e}")

        elapsed = time.monotonic() - started
        if int(elapsed) % 30 == 0 and elapsed > 0:
            print(f"   ⏳ [POLL] 等待中 ... ({int(elapsed)}s)")

        time.sleep(poll_interval)

    print(f"   ⚠️ [POLL] 超时 ({timeout_seconds}s)，任务可能仍在执行或 Worker 未启动")
    return None


def check_authorization_stored(task_id: str) -> bool:
    """检查 R6 授权是否已写入 Redis (auth:{task_id})"""
    r = _get_redis()
    auth_key = f"auth:{task_id}"
    try:
        raw = r.get(auth_key)
        return raw is not None
    except Exception:
        return False


def record_verdict(
    round_num: int,
    round_label: str,
    chain_ok: bool,
    execution_ok: bool,
    quality_ok: bool,
    governance_ok: bool,
    detail: dict | None = None,
) -> dict:
    """记录四维验收结果"""
    verdict = {
        "round": round_num,
        "label": round_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chain_success": chain_ok,
        "execution_success": execution_ok,
        "quality_success": quality_ok,
        "governance_success": governance_ok,
        "overall": chain_ok and execution_ok and quality_ok and governance_ok,
        "detail": detail or {},
    }
    print(f"\n{'─'*60}")
    print(f"  📊 Round {round_num} ({round_label}) 四维验收:")
    print(f"     链路成功:   {'✅' if chain_ok else '❌'}")
    print(f"     执行成功:   {'✅' if execution_ok else '❌'}")
    print(f"     质量成功:   {'✅' if quality_ok else '❌'}")
    print(f"     治理成功:   {'✅' if governance_ok else '❌'}")
    print(f"     综合:       {'✅ 通过' if verdict['overall'] else '❌ 未通过'}")
    print(f"{'─'*60}")
    return verdict


def _ast_inspect_python_file(path: Path) -> dict | None:
    """
    用 AST 精确解析 Python 文件，严格区分模块级函数与类方法。

    这是对早期「字符串包含检查」的修复：`f"def {fn}" in content` 无法区分
    `def get_order(db, order_id)`（模块级）与 `def get_order(self, ...)`（类方法），
    会导致 Worker 只实现类方法、漏掉模块级函数时依然误判通过。

    返回:
      {
        "module_functions": {函数名: [参数名列表]},   # 仅模块顶层 def
        "classes": {类名: {方法名: [参数名列表]}},     # 仅类内实例方法
        "module_assigns": set(),                      # 模块级赋值常量名
      }
    解析失败返回 None（文件不是有效 Python）。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    info = {
        "module_functions": {},
        "classes": {},
        "module_assigns": set(),
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            info["module_functions"][node.name] = [
                a.arg for a in node.args.args
            ]
        elif isinstance(node, ast.ClassDef):
            methods = {}
            for m in node.body:
                if isinstance(m, ast.FunctionDef):
                    methods[m.name] = [a.arg for a in m.args.args]
            info["classes"][node.name] = methods
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    info["module_assigns"].add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                info["module_assigns"].add(node.target.id)
    return info


# =====================================================================
# 治理机制 G1/G4：执行前快照 + 原子回滚
# =====================================================================
# 背景：R10 事故的深层根因是 _rollback_workspace 只有测试用例、从未实现，
#       Worker 直接裸写唯一真相工作区，失败后无法自动恢复，只能人工翻
#       VS Code Local History。以下函数补齐 G1（快照）与 G4（回滚）原语，
#       由独立故障注入测试 _test_rollback_standalone.py 验证。

_SKIP_SNAPSHOT_DIRS = {
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    ".pytest_cache", ".idea", ".vscode", "dist", "build",
    ".mypy_cache", ".ruff_cache", ".alphapilot",
}


def _snapshot_workspace(ws_path) -> dict:
    """G1: 执行前自动快照。

    遍历工作区所有跟踪文件，记录相对路径、内容、SHA256、大小、修改时间。
    跳过虚拟环境、缓存、VCS、构建产物等非源码目录。

    二进制文件（含 NUL 字节，如 .db/.sqlite/.png）用 base64 完整保留原始字节，
    避免文本解码（errors="replace"）丢失字节，导致回滚时损坏数据库等二进制文件。

    Returns:
        {相对路径: {
            "content": str,          # 文本文件：原文
            "content_b64": str,      # 二进制文件：base64 编码（is_binary=True 时有效）
            "is_binary": bool,
            "sha256": str, "size": int, "mtime": float,
        }}
    """
    ws = Path(ws_path)
    snapshot = {}
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_SNAPSHOT_DIRS for part in p.parts):
            continue
        try:
            raw = p.read_bytes()
            st = p.stat()
        except Exception:
            continue
        rel = p.relative_to(ws).as_posix()
        is_binary = b"\x00" in raw
        snapshot[rel] = {
            "content": "" if is_binary else raw.decode("utf-8", errors="replace"),
            "content_b64": base64.b64encode(raw).decode("ascii") if is_binary else "",
            "is_binary": is_binary,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": st.st_size,
            "mtime": st.st_mtime,
        }
    return snapshot


def _rollback_workspace(ws, snapshot: dict) -> dict:
    """G4: 原子回滚 —— 将工作区恢复到快照状态（bit-for-bit）。

    - 恢复所有快照文件内容（含被 Worker 删除的文件）
      * 文本文件：原样写回（newline="" 关闭 Windows 换行转换）
      * 二进制文件：base64 解码写回原始字节，避免文本化损坏 .db 等二进制文件
    - 删除不在快照中的新增文件（Worker 产生的污染产物）
    - 清理因此产生的空目录

    snapshot 兼容三种格式：
      - {相对路径: 内容字符串}                 （_test_rollback_standalone.py 使用）
      - {相对路径: {"content": ...}}           （_snapshot_workspace 文本输出）
      - {相对路径: {"is_binary": True, "content_b64": ...}}  （二进制）

    Returns:
        {"restored": int, "deleted_new": list[str], "errors": list[str]}
    """
    ws = Path(ws)
    snapshot_keys = set(snapshot.keys())

    restored = 0
    deleted_new = []
    errors = []

    # 1. 恢复快照中的每个文件（含重建被删除文件），bit-for-bit
    for rel, val in snapshot.items():
        target = ws / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(val, dict) and val.get("is_binary"):
                # 二进制文件：base64 解码写回原始字节
                target.write_bytes(base64.b64decode(val.get("content_b64", "")))
            else:
                content = val.get("content", "") if isinstance(val, dict) else val
                # newline="" 关闭 Windows 换行转换，原样写回，避免 \r\n 被二次转成 \r\r\n
                with open(target, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
            restored += 1
        except Exception as e:
            errors.append(f"restore {rel}: {e}")

    # 2. 删除不在快照中的新增文件
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_SNAPSHOT_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ws).as_posix()
        if rel not in snapshot_keys:
            try:
                p.unlink()
                deleted_new.append(rel)
            except Exception as e:
                errors.append(f"delete {rel}: {e}")

    # 3. 自底向上清理空目录
    for p in sorted(ws.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if not p.is_dir():
            continue
        if any(part in _SKIP_SNAPSHOT_DIRS for part in p.parts):
            continue
        try:
            if not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass

    return {"restored": restored, "deleted_new": deleted_new, "errors": errors}


# =====================================================================
# 统一任务状态机（治理唯一准入原则）
# =====================================================================
# 只有 QUALITY_GATE 全部通过，才允许 ACCEPT Worker 的修改。
# 测试失败不能通过自动重试掩盖，也不能覆盖原始基线。
class TaskState:
    PREPARE = "PREPARE"
    SNAPSHOT = "SNAPSHOT"
    VERIFY_BASELINE = "VERIFY_BASELINE"
    WORKER_EXECUTE = "WORKER_EXECUTE"
    QUALITY_GATE = "QUALITY_GATE"
    ACCEPT = "ACCEPT"
    QUARANTINE = "QUARANTINE"
    PRESERVE_DIFF = "PRESERVE_DIFF"
    BASELINE_SAFE = "BASELINE_SAFE"


# 合法状态流转：PREPARE → SNAPSHOT → VERIFY_BASELINE → WORKER_EXECUTE → QUALITY_GATE
#              QUALITY_GATE → ACCEPT（PASS）
#              QUALITY_GATE → QUARANTINE → PRESERVE_DIFF → BASELINE_SAFE（FAIL）
_STATE_TRANSITIONS = {
    TaskState.PREPARE: [TaskState.SNAPSHOT],
    TaskState.SNAPSHOT: [TaskState.VERIFY_BASELINE],
    TaskState.VERIFY_BASELINE: [TaskState.WORKER_EXECUTE, TaskState.BASELINE_SAFE],
    TaskState.WORKER_EXECUTE: [TaskState.QUALITY_GATE],
    TaskState.QUALITY_GATE: [TaskState.ACCEPT, TaskState.QUARANTINE],
    TaskState.QUARANTINE: [TaskState.PRESERVE_DIFF],
    TaskState.PRESERVE_DIFF: [TaskState.BASELINE_SAFE],
    TaskState.ACCEPT: [],
    TaskState.BASELINE_SAFE: [],
}


def _advance_state(machine: dict, next_state: str) -> None:
    """校验并推进状态机，非法流转立即抛错（防止绕过门禁）。"""
    current = machine["state"]
    allowed = _STATE_TRANSITIONS.get(current, [])
    if next_state not in allowed:
        raise RuntimeError(
            f"非法状态流转: {current} -> {next_state}（允许: {allowed}）"
        )
    machine["state"] = next_state
    machine["history"].append(next_state)


def _diff_workspace(ws_path, snapshot: dict) -> dict:
    """对比快照与当前工作区，基于 SHA256 识别文件变更。

    Returns:
        {"added": [...], "modified": [...], "deleted": [...], "unchanged": [...]}
    """
    current = _snapshot_workspace(ws_path)
    before = snapshot

    added = []
    modified = []
    deleted = []
    unchanged = []

    for rel, cur in current.items():
        prev = before.get(rel)
        if prev is None:
            added.append(rel)
        elif isinstance(prev, dict):
            if cur.get("sha256") != prev.get("sha256"):
                modified.append(rel)
            else:
                unchanged.append(rel)
        else:
            # 快照为简单 {路径: 内容} 格式时，退化用内容比对
            if cur.get("content") != prev:
                modified.append(rel)
            else:
                unchanged.append(rel)

    for rel in before:
        if rel not in current:
            deleted.append(rel)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "unchanged": sorted(unchanged),
    }


def _check_service_layer_contract(ws_path) -> tuple[bool, dict]:
    """R10 服务层契约检查（AST 精确分离模块级函数/类方法 + router 越界检测）。

    Returns:
        (passed: bool, checks: dict)
    """
    ws = Path(ws_path)
    checks = {}
    orders_svc = ws / "backend/services/order_service.py"
    inv_svc = ws / "backend/services/inventory_service.py"

    if orders_svc.exists():
        svc_info = _ast_inspect_python_file(orders_svc)
        if svc_info is None:
            checks["OrderService"] = False
            checks[_oc["constant"]] = False
            for method in _oc["methods"]:
                checks[f"method:{method}"] = False
            for fn in _oc["module_functions"]:
                checks[f"module_fn:{fn}"] = False
        else:
            checks["OrderService"] = _oc["class"] in svc_info["classes"]
            checks[_oc["constant"]] = _oc["constant"] in svc_info["module_assigns"]
            cls_methods = svc_info["classes"].get(_oc["class"], {})
            for method in _oc["methods"]:
                checks[f"method:{method}"] = method in cls_methods
            for fn in _oc["module_functions"]:
                checks[f"module_fn:{fn}"] = fn in svc_info["module_functions"]
            checks["sig:get_order"] = (
                svc_info["module_functions"].get("get_order") == ["db", "order_id"]
            )
            checks["sig:validate_transition"] = (
                svc_info["module_functions"].get("validate_transition")
                == ["current_status", "new_status"]
            )
    else:
        checks["OrderService"] = False
        checks[_oc["constant"]] = False
        for method in _oc["methods"]:
            checks[f"method:{method}"] = False
        for fn in _oc["module_functions"]:
            checks[f"module_fn:{fn}"] = False

    if inv_svc.exists():
        inv_info = _ast_inspect_python_file(inv_svc)
        if inv_info is None:
            checks["InventoryService"] = False
            for method in _ic["methods"]:
                checks[f"method:{method}"] = False
        else:
            checks["InventoryService"] = _ic["class"] in inv_info["classes"]
            inv_methods = inv_info["classes"].get(_ic["class"], {})
            for method in _ic["methods"]:
                checks[f"method:{method}"] = method in inv_methods
    else:
        checks["InventoryService"] = False
        for method in _ic["methods"]:
            checks[f"method:{method}"] = False

    inv_router = ws / "backend/routers" / "inventory.py"
    router_clean = True
    if inv_router.exists():
        router_content = inv_router.read_text(encoding="utf-8")
        for forbidden in SERVICE_LAYER_CONTRACT["router_forbidden"]:
            if forbidden in router_content:
                router_clean = False
                checks[f"forbidden_in_router:{forbidden}"] = True
    checks["router_clean"] = router_clean

    passed = all(v for k, v in checks.items() if not k.startswith("forbidden_in_router:"))
    return passed, checks


# ═══════════════════════════════════════════════════════════════
# G10.1 语义契约门禁（四层：Import / ORM / Router / 调用签名）
#       + 枚举契约 + 非目标文件保护
# 原则：仅做静态 AST 分析，绝不 import/执行被检查模块。
# ═══════════════════════════════════════════════════════════════

def _check_imports(ws_path, contract: dict) -> dict:
    """Import 目标存在性检查（静态 AST，不执行被检查代码）。

    只拦截「禁止导入/使用的模型名」（如 OrderItem），并把无法静态判定
    的情况记录为 UNKNOWN 而非直接 PASS/FAIL，避免误报。
    """
    ws = Path(ws_path)
    forbidden = set(contract.get("forbidden_imports", []))
    findings = []
    violations = []

    backend_dir = ws / "backend"
    if not backend_dir.is_dir():
        return {"passed": False, "findings": [], "violations": ["backend 目录不存在"]}

    for py_file in sorted(backend_dir.rglob("*.py")):
        rel = py_file.relative_to(ws).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            findings.append({"file": rel, "kind": "UNKNOWN", "detail": "无法解析"})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in forbidden:
                        violations.append(f"{rel}: 禁止导入模型 {alias.name}")
                        findings.append({"file": rel, "name": alias.name,
                                         "kind": "INVALID_INTERNAL_TARGET"})
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        if alias.name in forbidden:
                            violations.append(
                                f"{rel}: 禁止导入对象 {node.module}.{alias.name}"
                            )
                            findings.append({"file": rel,
                                             "name": f"{node.module}.{alias.name}",
                                             "kind": "INVALID_INTERNAL_TARGET"})
            elif isinstance(node, ast.Name):
                if node.id in forbidden:
                    # 裸用禁止模型（未 import 直接引用）
                    violations.append(f"{rel}: 使用了禁止模型 {node.id}")
                    findings.append({"file": rel, "name": node.id,
                                     "kind": "INVALID_INTERNAL_TARGET"})

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations}


def _check_orm_fields(ws_path, contract: dict) -> dict:
    """ORM 字段合法性检查（静态 AST）。

    1. 禁止字段名（customer_name/stock/price）不得作为属性或关键字参数出现。
    2. Order(...)/Inventory(...) 构造的关键字参数必须对应真实字段。
    """
    ws = Path(ws_path)
    forbidden_fields = set(contract.get("forbidden_fields", []))
    model_fields = {}
    for mname, model in contract.get("models", {}).items():
        if mname.startswith("__"):
            continue
        model_fields[mname] = set(model.get("fields", {}).keys())

    violations = []
    findings = []
    backend_dir = ws / "backend"
    if not backend_dir.is_dir():
        return {"passed": False, "findings": [], "violations": ["backend 目录不存在"]}

    for py_file in sorted(backend_dir.rglob("*.py")):
        rel = py_file.relative_to(ws).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.attr, str):
                if node.attr in forbidden_fields:
                    violations.append(f"{rel}: 使用了禁止字段 .{node.attr}")
                    findings.append({"file": rel, "field": node.attr,
                                     "kind": "FORBIDDEN_FIELD"})
            elif isinstance(node, ast.keyword):
                if node.arg in forbidden_fields:
                    violations.append(f"{rel}: 使用了禁止字段参数 {node.arg}=")
                    findings.append({"file": rel, "field": node.arg,
                                     "kind": "FORBIDDEN_FIELD"})
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in model_fields:
                    valid = model_fields[node.func.id]
                    for kw in node.keywords:
                        if kw.arg and kw.arg not in valid:
                            violations.append(
                                f"{rel}: {node.func.id} 不存在字段 {kw.arg}"
                            )
                            findings.append({"file": rel, "model": node.func.id,
                                             "field": kw.arg, "kind": "UNKNOWN_FIELD"})

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations}


def _extract_router_endpoints(tree: ast.AST) -> dict:
    """从路由模块 AST 提取端点集合 {(method, path): {"status_code": ...}}。"""
    endpoints = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            method = None
            if isinstance(dec.func, ast.Attribute):
                # 归一化为大写 HTTP 方法，与 SERVICE_LAYER_CONTRACT["router_contract"] 一致
                method = dec.func.attr.upper()
            path = None
            if dec.args and isinstance(dec.args[0], ast.Constant):
                path = dec.args[0].value
            status_code = None
            for kw in dec.keywords:
                if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                    status_code = kw.value.value
            if method and path is not None:
                endpoints[(method, path)] = {"status_code": status_code}
    return endpoints


def _check_router_contract(ws_path, contract: dict) -> dict:
    """路由端点完整集合检查：方法与路径集合匹配 + 状态码一致 + 无额外端点。"""
    ws = Path(ws_path)
    router_contract = contract.get("router_contract", {})
    findings = []
    violations = []
    actual = {}

    for router_name, expected in router_contract.items():
        rfile = ws / "backend" / "routers" / f"{router_name}.py"
        if not rfile.is_file():
            violations.append(f"路由文件缺失: backend/routers/{router_name}.py")
            continue
        try:
            tree = ast.parse(rfile.read_text(encoding="utf-8"))
        except Exception as e:
            violations.append(f"路由文件无法解析: {router_name}.py ({e})")
            continue
        endpoints = _extract_router_endpoints(tree)
        # 用字符串键（"METHOD path"）落证据，保证 JSON 可序列化（元组键会导致
        # _quarantine_failure 写 failure_evidence.json 时 TypeError）
        actual[router_name] = {
            f"{method} {path}": info for (method, path), info in endpoints.items()
        }
        expected_set = {(e["method"], e["path"]) for e in expected}
        actual_set = set(endpoints.keys())

        for e in expected:
            key = (e["method"], e["path"])
            if key in endpoints:
                got = endpoints[key].get("status_code")
                if got is not None and got != e["status_code"]:
                    violations.append(
                        f"{router_name}: {e['method']} {e['path']} "
                        f"状态码 {got} != 期望 {e['status_code']}"
                    )
                    findings.append({"router": router_name, "method": e["method"],
                                     "path": e["path"], "kind": "STATUS_CODE_MISMATCH",
                                     "expected": e["status_code"], "actual": got})
        for m in sorted(expected_set - actual_set):
            violations.append(f"{router_name}: 缺失端点 {m[0]} {m[1]}")
            findings.append({"router": router_name, "method": m[0], "path": m[1],
                             "kind": "MISSING_ENDPOINT"})
        for x in sorted(actual_set - expected_set):
            violations.append(f"{router_name}: 存在额外端点 {x[0]} {x[1]}")
            findings.append({"router": router_name, "method": x[0], "path": x[1],
                             "kind": "EXTRA_ENDPOINT"})

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations, "actual": actual}


def _check_call_signatures(ws_path, contract: dict) -> dict:
    """调用签名一致性检查：service 类必须支持实例化、方法必须是实例方法。"""
    ws = Path(ws_path)
    svc_files = {
        "order_service": ws / "backend" / "services" / "order_service.py",
        "inventory_service": ws / "backend" / "services" / "inventory_service.py",
    }
    violations = []
    findings = []

    for svc_key, svc_file in svc_files.items():
        spec = contract.get(svc_key, {})
        if not svc_file.is_file():
            violations.append(f"服务文件缺失: {svc_file.name}")
            continue
        info = _ast_inspect_python_file(svc_file)
        if info is None:
            violations.append(f"服务文件无法解析: {svc_file.name}")
            continue
        cls_name = spec.get("class")
        cls_methods = info["classes"].get(cls_name, {})
        if spec.get("instance_based"):
            init_args = cls_methods.get("__init__")
            if init_args != spec.get("init_params"):
                violations.append(
                    f"{cls_name}.__init__ 参数 {init_args} != 期望 "
                    f"{spec.get('init_params')}（必须支持实例化）"
                )
                findings.append({"class": cls_name, "kind": "INIT_SIGNATURE",
                                 "actual": init_args})
            for method in spec.get("methods", []):
                args = cls_methods.get(method)
                if args is None:
                    continue  # 符号缺失由 ast_contract 检查
                if not args or args[0] != "self":
                    violations.append(
                        f"{cls_name}.{method} 不是实例方法（缺少 self 第一参数，"
                        f"疑似 @staticmethod）"
                    )
                    findings.append({"class": cls_name, "method": method,
                                     "kind": "NOT_INSTANCE_METHOD"})

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations}


def _check_enum_contract(ws_path, contract: dict) -> dict:
    """枚举契约检查：定义与预期一致 + 状态转换方法存在。"""
    ws = Path(ws_path)
    enum_contract = contract.get("enum_contract", {})
    enum_file = ws / enum_contract.get("module_path", "backend/models/enums.py")
    violations = []
    findings = []

    if not enum_file.is_file():
        violations.append(f"枚举文件缺失: {enum_contract.get('module_path')}")
        return {"passed": False, "findings": findings, "violations": violations}

    enum_info = _extract_enum_from_file(enum_file)
    if enum_info["class_name"] != enum_contract.get("class_name"):
        violations.append(
            f"枚举类名 {enum_info['class_name']} != 期望 {enum_contract.get('class_name')}"
        )
    if enum_info["values"] != enum_contract.get("values"):
        violations.append(
            f"枚举值 {enum_info['values']} != 期望 {enum_contract.get('values')}"
        )
    if not enum_info["has_next_states"]:
        violations.append(
            f"枚举缺少 {enum_contract.get('transition_method')}() 方法"
        )

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations}


def _check_protected_files(ws_path, snapshot: dict, contract: dict) -> dict:
    """非目标文件内容级保护：受保护文件哈希必须与修改前基线一致。"""
    ws = Path(ws_path)
    violations = []
    findings = []

    for rel, spec in contract.get("protected_files", {}).items():
        mode = spec.get("mode")
        before = snapshot.get(rel) if snapshot else None
        current = ws / rel
        if before is None:
            if current.is_file():
                violations.append(f"受保护文件不应被新增: {rel}")
                findings.append({"file": rel, "kind": "PROTECTED_FILE_ADDED"})
            else:
                violations.append(f"受保护文件缺失于基线快照: {rel}")
            continue
        if not current.is_file():
            violations.append(f"受保护文件被删除: {rel}")
            findings.append({"file": rel, "kind": "PROTECTED_FILE_DELETED"})
            continue
        if mode == "whole_file":
            if isinstance(before, dict):
                before_hash = before.get("sha256", "")
            else:
                before_hash = hashlib.sha256(str(before).encode("utf-8")).hexdigest()
            after_hash = hashlib.sha256(current.read_bytes()).hexdigest()
            if before_hash != after_hash:
                violations.append(f"受保护文件被修改: {rel}")
                findings.append({"file": rel, "kind": "PROTECTED_FILE_MODIFIED"})

    return {"passed": len(violations) == 0, "findings": findings,
            "violations": violations}


def _check_semantic_contract(ws_path, snapshot=None, contract=None) -> tuple[bool, dict]:
    """四层语义门禁汇总：Import / ORM / Router / 调用签名 + 枚举 + 保护文件。

    FAIL-CLOSED：契约提取失败直接返回失败，绝不空契约放行。
    """
    if contract is None:
        try:
            contract = _build_semantic_contract(ws_path)
        except ContractExtractionError as e:
            return False, {"passed": False, "error": str(e)}

    checks = {
        "imports": _check_imports(ws_path, contract),
        "orm_fields": _check_orm_fields(ws_path, contract),
        "router_contract": _check_router_contract(ws_path, contract),
        "call_signatures": _check_call_signatures(ws_path, contract),
        "enum_contract": _check_enum_contract(ws_path, contract),
    }
    if snapshot is not None:
        checks["protected_files"] = _check_protected_files(ws_path, snapshot, contract)

    passed = all(c.get("passed", False) for c in checks.values())
    return passed, checks


def _collect_semantic_failure_reason(sem_checks: dict) -> str:
    """汇总语义契约检查的失败原因（供 failure_reason 字段使用）。

    UNKNOWN/未通过项绝不静默通过：只要 passed=False 就给出可追溯原因。
    """
    if not isinstance(sem_checks, dict):
        return "语义契约检查结果缺失"
    if sem_checks.get("error"):
        return str(sem_checks["error"])
    reasons = []
    for name, check in sem_checks.items():
        if not isinstance(check, dict):
            continue
        if check.get("passed", False):
            continue
        violations = check.get("violations", [])
        if violations:
            for v in violations:
                reasons.append(f"[{name}] {v}")
        else:
            reasons.append(f"[{name}] 未通过（无 violation 明细）")
    return "; ".join(reasons) if reasons else "语义契约检查未通过"


def _quality_gate(
    ws_path,
    snapshot: dict,
    contract_checker=None,
    semantic_contract_checker=None,
    baseline_test: dict | None = None,
) -> dict:
    """G3: 自动质量门禁。

    五项检查（对应治理验收标准）：
      1. regression_test        —— 自动运行原有测试（pytest）
      2. ast_contract           —— AST 契约检查（服务层符号契约）
      3. semantic_contract      —— G10.1 四层语义契约检查（Import/ORM/Router/调用签名 + 枚举 + 保护文件）
      4. file_scope             —— 文件修改范围检查（基于 SHA256 diff）
      5. baseline_compare       —— 任务前后测试结果对比

    semantic_contract_checker 签名: (ws_path, snapshot) -> (passed, checks)，
    默认 None 时跳过语义检查（用于不涉及 ShopFlow 模型的最小脚手架故障注入）。

    Returns:
        {"passed": bool, "checks": {...}}
    """
    ws = Path(ws_path)
    checks = {}

    # 1. 回归测试
    regression = run_local_pytest(str(ws))
    checks["regression_test"] = {
        "passed": regression.get("passed", False),
        "status": "PASS" if regression.get("passed", False) else "FAIL",
        "exit_code": regression.get("exit_code"),
        "timed_out": regression.get("timed_out", False),
        "stdout": regression.get("stdout", ""),
        "stderr": regression.get("stderr", ""),
        "failure_reason": None if regression.get("passed", False)
        else (regression.get("stderr", "") or regression.get("stdout", ""))[-2000:],
    }

    # 2. AST 契约检查（服务层符号契约）
    if contract_checker is not None:
        ast_passed, ast_checks = contract_checker(ws_path)
        checks["ast_contract"] = {
            "passed": ast_passed,
            "status": "PASS" if ast_passed else "FAIL",
            "checks": ast_checks,
            "failure_reason": None if ast_passed else "AST 服务层符号契约未通过",
        }
    else:
        checks["ast_contract"] = {"passed": True, "checks": {}}

    # 2b. 语义契约检查（G10.1 四层门禁，FAIL-CLOSED 由 checker 内部保证）
    if semantic_contract_checker is not None:
        sem_passed, sem_checks = semantic_contract_checker(ws_path, snapshot)
        checks["semantic_contract"] = {
            "passed": sem_passed,
            "status": "PASS" if sem_passed else "FAIL",
            "evidence": sem_checks,
            "failure_reason": None if sem_passed
            else _collect_semantic_failure_reason(sem_checks),
        }
    else:
        checks["semantic_contract"] = {"skipped": True, "passed": True}

    # 3. 文件修改范围检查（SHA256 diff）
    diff = _diff_workspace(ws_path, snapshot)
    checks["file_scope"] = {
        "added": diff["added"],
        "modified": diff["modified"],
        "deleted": diff["deleted"],
        "unchanged": diff["unchanged"],
    }

    # 4. 前后测试对比
    if baseline_test is not None:
        checks["baseline_compare"] = {
            "before_passed": baseline_test.get("passed", False),
            "after_passed": regression.get("passed", False),
            "regressed": baseline_test.get("passed", False)
            and not regression.get("passed", False),
        }
    else:
        checks["baseline_compare"] = {"skipped": True}

    passed = (
        checks["regression_test"]["passed"]
        and checks["ast_contract"]["passed"]
        and checks["semantic_contract"].get("passed", True)
    )
    if baseline_test is not None:
        passed = passed and not checks["baseline_compare"]["regressed"]

    return {"passed": passed, "checks": checks}


def _json_safe(obj):
    """递归地把对象转换为 JSON 可序列化结构（把非字符串 dict 键转成字符串）。"""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _quarantine_failure(ws_path, snapshot: dict, task_id: str, gate_result: dict) -> dict:
    """G4: 失败自动隔离 —— 保留失败现场与 diff，回滚基线。

    步骤：
      1. PRESERVE_DIFF：把 diff 与失败现场写入隔离目录
      2. BASELINE_SAFE：回滚工作区到快照状态

    Returns:
        {"quarantine_dir": str, "rollback": dict}
    """
    ws = Path(ws_path)
    diff = _diff_workspace(ws_path, snapshot)

    # 隔离目录放在工作区外部（ws.parent），避免被回滚逻辑删除、也避免污染工作区
    quarantine_root = ws.parent / ".alphapilot_quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    qdir = quarantine_root / task_id
    qdir.mkdir(parents=True, exist_ok=True)

    # 保留失败现场：把被修改/新增文件内容拷贝进隔离目录
    failure_files = {}
    for rel in diff["added"] + diff["modified"]:
        src = ws / rel
        if src.is_file():
            try:
                raw = src.read_bytes()
                if b"\x00" in raw:
                    failure_files[rel] = {
                        "is_binary": True,
                        "content_b64": base64.b64encode(raw).decode("ascii"),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                else:
                    failure_files[rel] = raw.decode("utf-8", errors="replace")
            except Exception:
                pass

    # C' 增强：pytest 的 stdout/stderr 必须进入隔离现场，
    # 否则无法还原具体断言失败。两者落盘为独立日志文件，避免 JSON 膨胀。
    regression_check = gate_result.get("checks", {}).get("regression_test", {})
    if not isinstance(regression_check, dict):
        regression_check = {}
    pytest_stdout = regression_check.get("stdout") or ""
    pytest_stderr = regression_check.get("stderr") or ""
    stdout_path = qdir / "pytest_stdout.log"
    stderr_path = qdir / "pytest_stderr.log"
    try:
        stdout_path.write_text(pytest_stdout, encoding="utf-8")
        stderr_path.write_text(pytest_stderr, encoding="utf-8")
    except Exception as e:
        print(f"   ⚠️ [QUARANTINE] pytest 日志落盘失败: {e}")

    # 从 evidence 中剥离大段 stdout/stderr，改用落盘文件引用 + 预览，
    # 完整内容见 pytest_stdout.log / pytest_stderr.log
    checks_for_evidence = dict(gate_result.get("checks", {}))
    reg = dict(checks_for_evidence.get("regression_test", {}))
    if reg.get("stdout"):
        reg["stdout_preview"] = reg["stdout"][:2000]
    if reg.get("stderr"):
        reg["stderr_preview"] = reg["stderr"][:2000]
    reg.pop("stdout", None)
    reg.pop("stderr", None)
    reg["pytest_stdout_file"] = stdout_path.name
    reg["pytest_stderr_file"] = stderr_path.name
    checks_for_evidence["regression_test"] = reg

    evidence = {
        "task_id": task_id,
        "gate_passed": gate_result["passed"],
        "diff": diff,
        "failure_files": failure_files,
        "checks": checks_for_evidence,
        "pytest_stdout_file": stdout_path.name,
        "pytest_stderr_file": stderr_path.name,
    }
    evidence_path = qdir / "failure_evidence.json"

    # 证据落盘是「尽力而为」：绝不允许证据序列化失败阻断回滚。
    # 回滚（BASELINE_SAFE）是治理的硬性安全动作，必须无条件执行。
    try:
        evidence_path.write_text(
            json.dumps(_json_safe(evidence), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"   ⚠️ [QUARANTINE] 证据序列化失败（不影响回滚）: {e}")

    # 回滚基线（BASELINE_SAFE）
    rollback = _rollback_workspace(ws, snapshot)

    return {
        "quarantine_dir": str(qdir),
        "evidence_path": str(evidence_path),
        "rollback": rollback,
    }


def _run_governed_task(
    prompt: str,
    workspace_path: str,
    task_type: str = "qwen_generate",
    conversation_id: str | None = None,
    contract_checker=None,
    semantic_contract_checker=None,
) -> dict:
    """统一任务状态机（治理唯一准入原则）。

    PREPARE → SNAPSHOT → VERIFY_BASELINE → WORKER_EXECUTE → QUALITY_GATE
              QUALITY_GATE ──PASS──> ACCEPT
              QUALITY_GATE ──FAIL──> QUARANTINE → PRESERVE_DIFF → BASELINE_SAFE

    只有 QUALITY_GATE 全部通过才 ACCEPT；失败则回滚基线并保留 diff。
    测试失败不会通过自动重试掩盖，也不会覆盖原始基线。

    Returns:
        {"state", "history", "task_id", "gate_result", "quarantine", ...}
    """
    machine = {"state": TaskState.PREPARE, "history": [TaskState.PREPARE]}

    # SNAPSHOT
    _advance_state(machine, TaskState.SNAPSHOT)
    snapshot = _snapshot_workspace(workspace_path)

    # VERIFY_BASELINE
    _advance_state(machine, TaskState.VERIFY_BASELINE)
    baseline_test = run_local_pytest(workspace_path)
    if not baseline_test.get("passed", False):
        # 基线本身已坏 → 禁止在坏基线上执行，直接回到安全态
        _advance_state(machine, TaskState.BASELINE_SAFE)
        return {
            "state": machine["state"],
            "history": machine["history"],
            "task_id": None,
            "snapshot": snapshot,
            "baseline_test": baseline_test,
            "gate_result": None,
            "quarantine": None,
            "error": "VERIFY_BASELINE 失败：基线测试未通过，拒绝执行任务。",
        }

    # WORKER_EXECUTE
    _advance_state(machine, TaskState.WORKER_EXECUTE)
    submit_resp = submit_task_via_api(
        prompt=prompt,
        workspace_path=workspace_path,
        task_type=task_type,
        conversation_id=conversation_id,
    )
    task_id = submit_resp.get("task_id")
    result = poll_task_result(task_id) if task_id else None

    # QUALITY_GATE
    _advance_state(machine, TaskState.QUALITY_GATE)
    gate_result = _quality_gate(
        workspace_path,
        snapshot,
        contract_checker=contract_checker,
        semantic_contract_checker=semantic_contract_checker,
        baseline_test=baseline_test,
    )

    quarantine = None
    if gate_result["passed"]:
        _advance_state(machine, TaskState.ACCEPT)
    else:
        _advance_state(machine, TaskState.QUARANTINE)
        _advance_state(machine, TaskState.PRESERVE_DIFF)
        quarantine = _quarantine_failure(
            workspace_path, snapshot, task_id or "unknown-task", gate_result
        )
        _advance_state(machine, TaskState.BASELINE_SAFE)

    return {
        "state": machine["state"],
        "history": machine["history"],
        "task_id": task_id,
        "worker_result": result,
        "snapshot": snapshot,
        "baseline_test": baseline_test,
        "gate_result": gate_result,
        "quarantine": quarantine,
    }


def run_local_pytest(workspace_path: str) -> dict:
    """在本地工作区运行 pytest 验证代码质量"""
    test_dir = Path(workspace_path) / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)

    pytest_cmd = [sys.executable, "-m", "pytest", str(workspace_path), "-q", "--tb=short"]
    start = time.monotonic()

    try:
        result = subprocess.run(
            pytest_cmd,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
            check=False,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_seconds": PYTEST_TIMEOUT,
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "pytest is not installed in the current Python environment.",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
        }


def clean_workspace(workspace_path: str):
    """清空工作区，仅保留 src 目录结构"""
    root = Path(workspace_path)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return

    exclude = {"__pycache__", ".pytest_cache", "node_modules", ".git", ".vscode", ".idea"}
    for item in root.iterdir():
        if item.name in exclude:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def inject_bug_remove_typing_import(workspace_path: str) -> bool:
    """给 orders.py 注入 Bug：移除 List 导入"""
    routes_file = Path(workspace_path) / "backend" / "routers" / "orders.py"
    if not routes_file.exists():
        print("   ⚠️ [Inject] orders.py 不存在，跳过 Bug 注入")
        return False
    original = routes_file.read_text(encoding="utf-8")
    modified = original.replace(
        "from typing import List",
        "from typing import   # ← BUG: List removed"
    )
    if modified == original:
        print("   ⚠️ [Inject] 未找到 'from typing import List'，Bug 注入失败")
        return False
    routes_file.write_text(modified, encoding="utf-8")
    print("   🐛 [Inject] Bug 已注入: backend/routers/orders.py (List 导入已移除)")
    return True


def read_all_sources(workspace_path: str) -> str:
    """读取工作区所有 Python 文件内容"""
    parts = []
    root = Path(workspace_path)
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file) or ".pytest_cache" in str(py_file) or ".venv" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            if len(content) > 2000:
                content = content[:2000] + "\n# ... (内容截断)"
            parts.append(f"### {py_file.relative_to(root)}\n```python\n{content}\n```")
        except Exception:
            pass
    return "\n\n".join(parts)


def strip_python_comments(text: str) -> str:
    """移除 Python 注释和文档字符串，仅保留实际代码"""
    import re
    # 移除三引号文档字符串
    text = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
    text = re.sub(r"'''.*?'''", '', text, flags=re.DOTALL)
    # 移除单行注释
    text = re.sub(r'#.*$', '', text, flags=re.MULTILINE)
    return text


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def check_services():
    """验证 Node.js API 和 Redis 均可达"""
    errors = []

    if not _check_node_api():
        errors.append(
            f"Node.js API 不可达 ({NODE_API_URL})。"
            f"请启动: cd node-api && node index.js"
        )
    else:
        print(f"\n✅ Node.js API 可达: {NODE_API_URL}")

    if not _check_redis():
        errors.append(
            f"Redis 不可达 ({REDIS_HOST}:{REDIS_PORT})。"
            f"请启动: docker run -p 6379:6379 redis 或 redis-server"
        )
    else:
        print(f"✅ Redis 可达: {REDIS_HOST}:{REDIS_PORT}")

    if errors:
        pytest.skip("\n".join(errors))


def clear_project_memory(project_name_pattern: str = "shopflow") -> int:
    """清除指定项目的所有历史任务，确保测试从零开始（无记忆污染）"""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host='localhost', port=5433,
            dbname='alphapilot_copilot_memory',
            user='alphapilot', password='alphapilot_memory_2026',
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute('SELECT id, name FROM "Project" WHERE LOWER(name) LIKE %s',
                    (f'%{project_name_pattern}%',))
        projects = cur.fetchall()

        total = 0
        for pid, pname in projects:
            cur.execute('DELETE FROM "Task" WHERE project_id = %s', (pid,))
            n = cur.rowcount
            total += n
            if n > 0:
                print(f"  🧹 [MEMORY CLEAN] {pname}: 已清除 {n} 个历史任务")
        conn.commit()
        conn.close()
        return total
    except Exception as e:
        print(f"  ⚠️ [MEMORY CLEAN] 跳过清除（{e}）")
        return 0


@pytest.fixture(autouse=True)
def record_test_start(request):
    """记录每个测试的开始时间"""
    node_id = request.node.nodeid
    print(f"\n{'='*70}")
    print(f"  🚀 开始: {node_id}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    yield


@pytest.fixture
def workspace():
    """确保工作区目录存在"""
    ws = Path(DEFAULT_WORKSPACE)
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


# ═══════════════════════════════════════════════════════════════
# 测试用例 — ShopFlow 真实链路 6 轮贯穿
# ═══════════════════════════════════════════════════════════════

_shopflow_verdicts: list[dict] = []


class TestShopFlowProductionPath:

    @classmethod
    def setup_class(cls):
        """测试前：清除项目历史记忆，避免污染 LLM 工作台"""
        cleared = clear_project_memory("shopflow")
        print(f"\n{'='*70}")
        print(f"  🧪 ShopFlow 生产路径测试 — Attempt #4")
        print(f"  🧹 记忆清除: {cleared} 个历史任务")
        print(f"{'='*70}")

    @pytest.mark.timeout(960)
    def test_round5_architecture(self, check_services, workspace):
        """
        Round 5: 架构设计
        链路: POST /task/submit → Redis → Worker → LLM → FileOps → 结果
        验收: 架构设计文档存在 + Markdown 内容完整 + 无 Python 代码生成
        """
        global _shopflow_verdicts

        clean_workspace(workspace)
        print(f"\n  🧹 工作区已清理: {workspace}")

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        try:
            submit_resp = submit_task_via_api(
                prompt=PROMPT_ROUND_5,
                workspace_path=workspace,
                conversation_id=SHOPFLOW_CONVERSATION_ID,
            )
            task_id = submit_resp.get("task_id")
            chain_ok = task_id is not None
            detail["submit_response"] = submit_resp

            result = poll_task_result(task_id)
            execution_ok = result is not None
            detail["result"] = result

            if result:
                status = result.get("status", "unknown")
                execution_ok = status in ("done", "awaiting_authorization")
                detail["result_status"] = status

                governance_ok = check_authorization_stored(task_id)
                detail["r6_authorization"] = governance_ok

                design_file = Path(workspace) / "architecture_design.md"
                docs_file = Path(workspace) / "docs" / "architecture_design.md"
                if not design_file.exists() and docs_file.exists():
                    design_file = docs_file
                quality_ok = design_file.exists()
                if quality_ok:
                    content = design_file.read_text(encoding="utf-8")
                    quality_ok = len(content) > 200
                    detail["design_size"] = len(content)
                detail["design_file_exists"] = design_file.exists()

                py_files_gen = list(Path(workspace).rglob("*.py"))
                detail["py_files_generated"] = len(py_files_gen)

                if py_files_gen:
                    print(f"  ⚠️ 架构设计阶段生成了 {len(py_files_gen)} 个 .py 文件: "
                          f"{[f.name for f in py_files_gen]}")

            verdict = record_verdict(
                5, "architecture", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(5, "architecture", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败：任务未成功提交到 Node.js API"
        assert execution_ok, "执行失败：Worker 未完成任务"
        assert quality_ok, "质量失败：架构设计文档不存在或内容过短"

    @pytest.mark.timeout(960)
    def test_round6_core_implementation(self, check_services, workspace):
        """
        Round 6: 核心实现
        链路: POST /task/submit → Redis → Worker → LLM → FileOps → pytest
        验收: 核心文件存在 + pytest 全部通过 + 四维验收
        """
        global _shopflow_verdicts

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        try:
            submit_resp = submit_task_via_api(
                prompt=PROMPT_ROUND_6,
                workspace_path=workspace,
                conversation_id=SHOPFLOW_CONVERSATION_ID,
            )
            task_id = submit_resp.get("task_id")
            chain_ok = task_id is not None

            result = poll_task_result(task_id)
            execution_ok = result is not None

            if result:
                status = result.get("status", "unknown")
                execution_ok = status in ("done", "awaiting_authorization")
                detail["result_status"] = status
                governance_ok = check_authorization_stored(task_id)
                detail["r6_authorization"] = governance_ok

                final_file_ops = (
                    result.get("context", {}).get("final_file_ops", [])
                    or result.get("final_file_ops", [])
                )
                paths = [op.get("path") or "" for op in final_file_ops]
                detail["generated_paths"] = paths

                ws_path = Path(workspace)
                essential = [
                    "backend/models/order.py",
                    "backend/schemas/order.py",
                    "backend/routers/orders.py",
                    "backend/database.py",
                    "backend/main.py",
                    "tests/test_orders.py",
                ]
                missing = [f for f in essential if not (ws_path / f).exists()]
                detail["missing_files"] = missing

                test_result = run_local_pytest(workspace)
                quality_ok = test_result.get("passed", False)
                detail["test_passed"] = quality_ok

                if not quality_ok:
                    err = (test_result.get("stdout", "") + test_result.get("stderr", ""))[:1000]
                    detail["test_error_preview"] = err

            verdict = record_verdict(
                6, "core_implementation", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(6, "core_implementation", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败"
        assert execution_ok, "执行失败"
        assert quality_ok, (
            f"质量失败：pytest 未通过\n"
            f"缺失文件: {detail.get('missing_files', [])}\n"
            f"错误: {detail.get('test_error_preview', '')[:500]}"
        )

    @pytest.mark.timeout(960)
    def test_round7_bug_fix(self, check_services, workspace):
        """
        Round 7: Bug 精准修复
        流程: 验证 R6 产出文件 → 收集已有错误 + 注入 Bug
              → POST /task/submit (含完整错误信息) → Worker → 修复 → 验证

        验收: 所有 Bug 被修复 + pytest 通过 + 修改范围最小化
        """
        global _shopflow_verdicts

        ws_path = Path(workspace)
        essential = [
            "backend/models/order.py",
            "backend/schemas/order.py",
            "backend/routers/orders.py",
            "backend/database.py",
            "backend/main.py",
            "tests/test_orders.py",
        ]
        missing = [f for f in essential if not (ws_path / f).exists()]
        assert not missing, f"前置条件不满足: R6 未产出必要文件 {missing}"
        print(f"  ✅ 前置条件: {len(essential)} 个必要文件均已产出")

        baseline_errors = ""
        pre_test = run_local_pytest(workspace)
        if not pre_test.get("passed", False):
            baseline_errors = (pre_test.get("stdout", "") + "\n" + pre_test.get("stderr", ""))[:2000]
            print(f"  ⚠️  R6 残留 {baseline_errors.count('FAILED')} 个测试失败，将一并修复")
            print(f"  📋 残留错误摘要:\n{baseline_errors[:300]}")
        else:
            print("  ✅ 前置条件: pytest 已通过")

        injected = inject_bug_remove_typing_import(workspace)
        error_text = ""
        if injected:
            bug_test = run_local_pytest(workspace)
            assert not bug_test.get("passed", False), "Bug 注入后 pytest 仍通过 — 注入无效"
            print("  🐛 Bug 已触发: pytest 失败 ✅")
            error_text = (bug_test.get("stdout", "") + "\n" + bug_test.get("stderr", ""))[:3000]
            print(f"  🐛 注入后 traceback 摘要:\n{error_text[:500]}")
        else:
            print("  ℹ️  Bug 注入跳过（代码未使用目标模式），使用 R6 自有错误即可")

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        has_errors = bool(baseline_errors or error_text)

        if not has_errors:
            chain_ok = True
            execution_ok = True
            quality_ok = True
            governance_ok = True
            detail["note"] = "R6 代码已通过 pytest，且无 Bug 注入，跳过修复"
            print("  ✅ R6 代码已通过 pytest，且无 Bug 注入，跳过 R7 修复")

        try:
            if has_errors:
                all_errors = ""
                if baseline_errors:
                    all_errors += f"=== 已有问题（R6 遗留，需一并修复）===\n{baseline_errors}\n\n"
                if error_text:
                    all_errors += f"=== 注入 Bug 后的错误 ===\n{error_text}"

                bug_fix_prompt = (
                    f"{PROMPT_ROUND_7}\n\n"
                    f"{all_errors}\n\n"
                    f"⭐⭐⭐ 关键要求：修复上述所有错误（包括已有问题和注入 Bug），"
                    f"只做最小修改，不要改动测试断言、HTTP 状态码、API 行为。"
                )

                submit_resp = submit_task_via_api(
                    prompt=bug_fix_prompt,
                    workspace_path=workspace,
                    conversation_id=SHOPFLOW_CONVERSATION_ID,
                )
                task_id = submit_resp.get("task_id")
                chain_ok = task_id is not None

                result = poll_task_result(task_id)
                execution_ok = result is not None

                if result:
                    status = result.get("status", "unknown")
                    execution_ok = status in ("done", "awaiting_authorization")
                    governance_ok = check_authorization_stored(task_id)

                    final_paths = []
                    for op in (result.get("context", {}).get("final_file_ops", [])
                               or result.get("final_file_ops", [])):
                        p = op.get("path") or ""
                        if p:
                            final_paths.append(p)
                    detail["modified_paths"] = final_paths

                    test_result = run_local_pytest(workspace)
                    quality_ok = test_result.get("passed", False)
                    detail["test_passed"] = quality_ok

                    if quality_ok and injected:
                        content = (ws_path / "backend" / "routers" / "orders.py").read_text(
                            encoding="utf-8"
                        )
                        quality_ok = "from typing import List" in content
                        detail["import_restored"] = quality_ok

            verdict = record_verdict(
                7, "bug_fix", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(7, "bug_fix", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败"
        assert execution_ok, "执行失败"
        assert quality_ok, (
            f"质量失败：Bug 修复后 pytest 未通过或 List 导入未恢复\n"
            f"修改文件: {detail.get('modified_paths', [])}"
        )

    @pytest.mark.timeout(960)
    def test_round8_incremental_feature(self, check_services, workspace):
        """
        Round 8: 增量功能追加（库存系统）
        验收: inventory 三文件存在 + pytest 全部通过 + test_orders 未被修改
        """
        global _shopflow_verdicts

        ws_path = Path(workspace)
        pre_test = run_local_pytest(workspace)
        assert pre_test.get("passed", False), (
            f"前置条件不满足: Round 7 后 pytest 未通过"
        )
        print("  ✅ 前置条件: pytest 通过，准备增量开发")

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        old_orders_test = (ws_path / "tests" / "test_orders.py").read_text(
            encoding="utf-8"
        ) if (ws_path / "tests" / "test_orders.py").exists() else ""

        try:
            submit_resp = submit_task_via_api(
                prompt=PROMPT_ROUND_8,
                workspace_path=workspace,
                conversation_id=SHOPFLOW_CONVERSATION_ID,
            )
            task_id = submit_resp.get("task_id")
            chain_ok = task_id is not None

            result = poll_task_result(task_id)
            execution_ok = result is not None

            if result:
                status = result.get("status", "unknown")
                execution_ok = status in ("done", "awaiting_authorization")
                governance_ok = check_authorization_stored(task_id)

                inv_model = (ws_path / "backend/models/inventory.py").exists()
                inv_router = (ws_path / "backend/routers/inventory.py").exists()
                inv_test = (ws_path / "tests/test_inventory.py").exists()
                detail["inventory_files"] = {
                    "model": inv_model, "router": inv_router, "test": inv_test
                }

                test_result = run_local_pytest(workspace)
                quality_ok = test_result.get("passed", False)
                detail["test_passed"] = quality_ok

                if old_orders_test and (ws_path / "tests" / "test_orders.py").exists():
                    new_orders = (ws_path / "tests" / "test_orders.py").read_text(
                        encoding="utf-8"
                    )
                    detail["test_orders_preserved"] = "test_create_order" in new_orders

            verdict = record_verdict(
                8, "incremental_feature", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(8, "incremental_feature", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败"
        assert execution_ok, "执行失败"
        assert quality_ok, (
            f"质量失败：库存系统文件缺失或 pytest 未通过\n"
            f"文件: {detail.get('inventory_files', {})}"
        )

    @pytest.mark.timeout(960)
    def test_round9_cascading_change(self, check_services, workspace):
        """
        Round 9: 跨文件级联修改
        验收: 旧枚举值全部清除 + 新枚举值到位 + pytest 通过 + 2+ 文件被修改
        """
        global _shopflow_verdicts

        ws_path = Path(workspace)
        pre_test = run_local_pytest(workspace)
        assert pre_test.get("passed", False), "前置条件: pytest 未通过"

        old_values = {"confirmed", "shipped", "delivered"}
        before_sources = read_all_sources(workspace)
        before_refs = {v: before_sources.count(v) for v in old_values}
        print(f"  📊 改前引用: {before_refs}")

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        try:
            submit_resp = submit_task_via_api(
                prompt=PROMPT_ROUND_9,
                workspace_path=workspace,
                conversation_id=SHOPFLOW_CONVERSATION_ID,
            )
            task_id = submit_resp.get("task_id")
            chain_ok = task_id is not None

            result = poll_task_result(task_id)
            execution_ok = result is not None

            if result:
                status = result.get("status", "unknown")
                execution_ok = status in ("done", "awaiting_authorization")
                governance_ok = check_authorization_stored(task_id)

                after_sources = read_all_sources(workspace)
                code_only = strip_python_comments(after_sources)
                leftover = {v: code_only.count(v) for v in old_values
                             if v in code_only}
                detail["old_values_remaining"] = leftover

                new_values = {"processing", "in_transit", "completed"}
                found_new = [v for v in new_values if v in code_only]
                detail["new_values_found"] = found_new

                final_paths = []
                for op in (result.get("context", {}).get("final_file_ops", [])
                           or result.get("final_file_ops", [])):
                    p = op.get("path") or ""
                    if p:
                        final_paths.append(p)
                detail["modified_paths"] = final_paths

                test_result = run_local_pytest(workspace)
                quality_ok = (
                    test_result.get("passed", False)
                    and len(leftover) == 0
                    and len(found_new) >= 3
                    and len(final_paths) >= 2
                )
                detail["test_passed"] = test_result.get("passed", False)

            verdict = record_verdict(
                9, "cascading_change", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(9, "cascading_change", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败"
        assert execution_ok, "执行失败"
        assert quality_ok, (
            f"质量失败：级联修改不完整\n"
            f"残留旧值: {detail.get('old_values_remaining', {})}\n"
            f"新值: {detail.get('new_values_found', [])}\n"
            f"修改文件: {detail.get('modified_paths', [])}"
        )

    @pytest.mark.timeout(960)
    def test_round10_refactor_service_layer(self, check_services, workspace):
        """
        Round 10: 重构提取服务层
        验收: service 文件存在 + OrderService 方法完整 + router 无直接 db 操作
              + pytest 通过
        """
        global _shopflow_verdicts

        ws_path = Path(workspace)
        pre_test = run_local_pytest(workspace)
        assert pre_test.get("passed", False), "前置条件: pytest 未通过"
        print("  ✅ 前置条件: pytest 通过，准备重构")

        # G10.1: 从真实源码（基线）冻结语义契约，并据此派生 PROMPT（FAIL-CLOSED）
        sem_contract = _build_semantic_contract(str(ws_path))
        model_block = _format_model_contract_block(sem_contract)
        prompt_round_10 = _PROMPT_ROUND_10_TEMPLATE.replace(
            "{model_contract_block}", model_block
        )
        pre_snapshot = _snapshot_workspace(workspace)

        task_id = None
        chain_ok = False
        execution_ok = False
        quality_ok = False
        governance_ok = False
        detail = {}

        try:
            submit_resp = submit_task_via_api(
                prompt=prompt_round_10,
                workspace_path=workspace,
                conversation_id=SHOPFLOW_CONVERSATION_ID,
            )
            task_id = submit_resp.get("task_id")
            chain_ok = task_id is not None

            result = poll_task_result(task_id)
            execution_ok = result is not None

            if result:
                status = result.get("status", "unknown")
                execution_ok = status in ("done", "awaiting_authorization")
                governance_ok = check_authorization_stored(task_id)

                orders_svc = ws_path / "backend/services/order_service.py"
                inv_svc = ws_path / "backend/services/inventory_service.py"
                detail["services"] = {
                    "order_service": orders_svc.exists(),
                    "inventory_service": inv_svc.exists(),
                }

                svc_checks = {}
                if orders_svc.exists():
                    svc_info = _ast_inspect_python_file(orders_svc)
                    if svc_info is None:
                        svc_checks["OrderService"] = False
                        svc_checks[_oc["constant"]] = False
                        for method in _oc["methods"]:
                            svc_checks[f"method:{method}"] = False
                        for fn in _oc["module_functions"]:
                            svc_checks[f"module_fn:{fn}"] = False
                    else:
                        # 类必须定义在模块顶层
                        svc_checks["OrderService"] = _oc["class"] in svc_info["classes"]
                        # 常量必须是模块级赋值（不是类属性、不是局部变量）
                        svc_checks[_oc["constant"]] = _oc["constant"] in svc_info["module_assigns"]
                        # 类方法必须定义在 OrderService 类内
                        cls_methods = svc_info["classes"].get(_oc["class"], {})
                        for method in _oc["methods"]:
                            svc_checks[f"method:{method}"] = method in cls_methods
                        # 模块级函数必须定义在模块顶层（而非任何类内）
                        for fn in _oc["module_functions"]:
                            svc_checks[f"module_fn:{fn}"] = fn in svc_info["module_functions"]
                        # 函数签名精确校验
                        svc_checks["sig:get_order"] = (
                            svc_info["module_functions"].get("get_order") == ["db", "order_id"]
                        )
                        svc_checks["sig:validate_transition"] = (
                            svc_info["module_functions"].get("validate_transition")
                            == ["current_status", "new_status"]
                        )

                if inv_svc.exists():
                    inv_info = _ast_inspect_python_file(inv_svc)
                    if inv_info is None:
                        svc_checks["InventoryService"] = False
                        for method in _ic["methods"]:
                            svc_checks[f"method:{method}"] = False
                    else:
                        svc_checks["InventoryService"] = _ic["class"] in inv_info["classes"]
                        inv_methods = inv_info["classes"].get(_ic["class"], {})
                        for method in _ic["methods"]:
                            svc_checks[f"method:{method}"] = method in inv_methods

                inv_router = ws_path / "backend/routers" / "inventory.py"
                router_clean = True
                if inv_router.exists():
                    router_content = inv_router.read_text(encoding="utf-8")
                    for forbidden in SERVICE_LAYER_CONTRACT["router_forbidden"]:
                        if forbidden in router_content:
                            router_clean = False
                            svc_checks[f"forbidden_in_router:{forbidden}"] = True
                            break
                detail["service_checks"] = svc_checks
                detail["router_clean"] = router_clean

                # G10.1: 以基线冻结契约执行四层语义门禁（Import/ORM/路由/签名 + 枚举 + 保护文件）
                sem_passed, sem_checks = _check_semantic_contract(
                    workspace, snapshot=pre_snapshot, contract=sem_contract
                )
                detail["semantic_checks"] = sem_checks
                detail["semantic_passed"] = sem_passed

                test_result = run_local_pytest(workspace)
                quality_ok = (
                    test_result.get("passed", False)
                    and all(svc_checks.values())
                    and router_clean
                    and sem_passed
                )
                detail["test_passed"] = test_result.get("passed", False)

                # G4: 质量门禁失败自动回滚 —— 失败现场隔离留证，工作区基线恢复执行前快照
                if not quality_ok:
                    gate_result = {
                        "passed": False,
                        "checks": {
                            "regression_test": test_result,
                            "service_checks": svc_checks,
                            "router_clean": router_clean,
                            "semantic_contract": {
                                "passed": sem_passed,
                                "evidence": sem_checks,
                                "failure_reason": _collect_semantic_failure_reason(sem_checks),
                            },
                        },
                    }
                    quarantine = _quarantine_failure(
                        workspace, pre_snapshot, task_id or "round10-unknown", gate_result
                    )
                    detail["quarantine"] = quarantine
                    detail["rollback"] = quarantine["rollback"]

            else:
                # 轮询超时兜底：Worker 未在窗口内返回结果时仍需回滚并隔离现场，防止污染基线
                quality_ok = False
                gate_result = {
                    "passed": False,
                    "checks": {
                        "regression_test": {"passed": False, "stdout": "", "stderr": ""},
                        "timeout": True,
                        "reason": "poll_task_result 超时返回 None，Worker 未在轮询窗口内完成",
                    },
                }
                quarantine = _quarantine_failure(
                    workspace, pre_snapshot, task_id or "round10-timeout", gate_result
                )
                detail["quarantine"] = quarantine
                detail["rollback"] = quarantine["rollback"]

            verdict = record_verdict(
                10, "refactor", chain_ok, execution_ok, quality_ok, governance_ok, detail
            )
            _shopflow_verdicts.append(verdict)

        except Exception as e:
            verdict = record_verdict(10, "refactor", False, False, False, False,
                                      {"error": str(e)})
            _shopflow_verdicts.append(verdict)
            raise

        assert chain_ok, "链路失败"
        assert execution_ok, "执行失败"
        assert quality_ok, (
            f"质量失败：服务层重构不完整\n"
            f"服务检查: {detail.get('service_checks', {})}\n"
            f"Router clean: {detail.get('router_clean', False)}\n"
            f"语义契约: {_collect_semantic_failure_reason(detail.get('semantic_checks', {}))}"
        )

    def test_summary_report(self):
        """汇总报告：输出全部 6 轮的四维验收结果"""
        print(f"\n{'='*70}")
        print(f"  🏪 ShopFlow 真实链路端到端观察测试 — 汇总报告")
        print(f"  Conversation: {SHOPFLOW_CONVERSATION_ID}")
        print(f"  Workspace: {DEFAULT_WORKSPACE}")
        print(f"  Node API: {NODE_API_URL}")
        print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
        print(f"{'='*70}")

        if not _shopflow_verdicts:
            print("  ⚠️ 无验收记录（前置测试可能全部跳过）")
            return

        print(f"\n{'Round':<10} {'Label':<25} {'Chain':<8} {'Exec':<8} {'Quality':<8} {'Gov':<8} {'Overall':<8}")
        print(f"{'-'*10} {'-'*25} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

        for v in _shopflow_verdicts:
            def ok(flag):
                return "✅" if flag else "❌"
            print(f"{v['round']:<10} {v['label']:<25} "
                  f"{ok(v['chain_success']):<8} {ok(v['execution_success']):<8} "
                  f"{ok(v['quality_success']):<8} {ok(v['governance_success']):<8} "
                  f"{ok(v['overall']):<8}")

        total = len(_shopflow_verdicts)
        passed = sum(1 for v in _shopflow_verdicts if v["overall"])
        print(f"\n  📊 总览: {passed}/{total} 轮完全通过四维验收")
        print(f"{'='*70}")

        assert passed == total, (
            f"{total - passed} 轮未通过四维验收。"
            f"详情见上方逐项报告。"
        )