# -*- coding: utf-8 -*-
"""G10.23 回归契约：路由端点 AST 提取的语义等价与状态码解析。

取证（2026-11-15 ShopFlow R10 / shopflow_v4_1 真实链路）：

    [router_contract] orders: 缺失端点 GET /
    [router_contract] orders: 存在额外端点 GET <空>

源码写的是 `@router.post("")`，FastAPI 挂载 prefix 后与 `@router.post("/")`
映射到同一 URL，属语义等价写法；旧提取器按字面比较，把同一个端点同时
判成「缺失」和「额外」，是从 R6 起就一直存在的假阴性，与 R9 无关。

同时 `status_code=status.HTTP_200_OK` 是 ast.Attribute，旧提取器只认
ast.Constant → 解析成 None，而 `_check_router_contract` 对 None 直接跳过
比对，orders.py 全部端点的状态码检查形同虚设（11-14 已记为已知限制）。

修复（python_worker/tests/test_observe_task_system.py）：
  * 只把**空字符串**路径归一为 "/"，其它路径原样保留；
  * 解析 `HTTP_2xx_*` 常量名（`status.HTTP_200_OK` / 裸名）为真实整数，
    无法确定的写法仍返回 None，绝不臆造数字。

这是**净加严**：以前状态码恒为 None 被跳过，现在真正参与比对。下面
「额外端点仍被拒」「错误状态码现在会被抓到」两条用例即是证据。
"""
import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_worker.tests import test_observe_task_system as obs  # noqa: E402

_CONTRACT = {
    "router_contract": {
        "orders": [
            {"method": "POST", "path": "/", "status_code": 200},
            {"method": "GET", "path": "/", "status_code": 200},
        ]
    }
}


def _endpoints(src: str) -> dict:
    return obs._extract_router_endpoints(ast.parse(src))


def _workspace(tmp_path: Path, src: str) -> Path:
    routers = tmp_path / "backend" / "routers"
    routers.mkdir(parents=True)
    (routers / "orders.py").write_text(src, encoding="utf-8")
    return tmp_path


def test_empty_path_is_normalized_to_root():
    """`@router.post("")` 与契约里的 `POST /` 应视为同一端点。"""
    eps = _endpoints('''
from fastapi import APIRouter
router = APIRouter()
@router.post("", status_code=200)
def create(): pass
''')
    assert ("POST", "/") in eps
    assert ("POST", "") not in eps


def test_http_status_constants_resolve_to_real_integers():
    """status.HTTP_200_OK / 裸名 HTTP_204_NO_CONTENT / 字面量都要能比对。"""
    eps = _endpoints('''
from fastapi import APIRouter, status
router = APIRouter()
@router.post("", status_code=status.HTTP_200_OK)
def create(): pass
@router.delete("/{order_id}", status_code=HTTP_204_NO_CONTENT)
def delete(): pass
@router.put("/{order_id}", status_code=201)
def update(): pass
''')
    assert eps[("POST", "/")]["status_code"] == 200
    assert eps[("DELETE", "/{order_id}")]["status_code"] == 204
    assert eps[("PUT", "/{order_id}")]["status_code"] == 201


def test_unknown_status_expression_stays_none():
    """无法确定的表达式返回 None，不臆造数字（FAIL-OPEN 于解析、不放行检查）。"""
    eps = _endpoints('''
from fastapi import APIRouter
router = APIRouter()
@router.patch("/{order_id}", status_code=compute_code())
def patch(): pass
''')
    assert eps[("PATCH", "/{order_id}")]["status_code"] is None


def test_non_string_path_constant_is_not_accepted():
    """路径必须是字符串常量；非字符串不得凭空变成端点（加严）。"""
    eps = _endpoints('''
from fastapi import APIRouter
router = APIRouter()
@router.get(123)
def weird(): pass
''')
    assert eps == {}


def test_extra_endpoint_is_still_rejected(tmp_path):
    """归一化没有放宽集合检查：多出来的端点依然判失败。"""
    ws = _workspace(tmp_path, '''
from fastapi import APIRouter, status
router = APIRouter()
@router.post("", status_code=status.HTTP_200_OK)
def create(): pass
@router.get("", status_code=status.HTTP_200_OK)
def list_orders(): pass
@router.post("/evil", status_code=200)
def evil(): pass
''')
    out = obs._check_router_contract(str(ws), _CONTRACT)
    assert not out["passed"]
    assert any(f["kind"] == "EXTRA_ENDPOINT" for f in out["findings"])
    assert not any(f["kind"] == "MISSING_ENDPOINT" for f in out["findings"])


def test_wrong_status_code_is_now_caught(tmp_path):
    """净加严证据：status.HTTP_201_CREATED 以前解析成 None 被跳过，现在必须报错。"""
    ws = _workspace(tmp_path, '''
from fastapi import APIRouter, status
router = APIRouter()
@router.post("", status_code=status.HTTP_201_CREATED)
def create(): pass
@router.get("", status_code=status.HTTP_200_OK)
def list_orders(): pass
''')
    out = obs._check_router_contract(str(ws), _CONTRACT)
    assert not out["passed"]
    assert any(f["kind"] == "STATUS_CODE_MISMATCH" for f in out["findings"])
