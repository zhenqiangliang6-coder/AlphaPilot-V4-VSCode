"""v3.7 validate_generated_files 结构完整性验证层测试

验证 AlphaPilot 在 merge_file_ops 后自动检测：
  G9.1 — FastAPI Router 未注册
  G9.2 — 跨文件可变状态冲突
  G9.3 — Python 语法错误
  G9.4 — 导入引用不存在的文件
  G9.5 — 前端依赖缺失
"""

import pytest
from file_ops import (
    validate_generated_files,
    _check_fastapi_router_registration,
    _check_cross_file_state_conflicts,
    _validate_python_syntax,
    _check_import_integrity,
    _check_frontend_dependency_gaps,
    create_file_op,
    merge_file_ops,
)


# ── helpers ─────────────────────────────────────────────

def _op(path, content, op_type="create"):
    return create_file_op(op_type, path, content, reason="test", intent="test")


# ══════════════════════════════════════════════════════════
# G9.1: FastAPI Router 注册完整性
# ══════════════════════════════════════════════════════════

ROUTER_WITH_APP = """
from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("/")
async def root():
    return {"ok": True}

app.include_router(router)
"""

ROUTER_WITHOUT_APP = """
from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("/")
async def root():
    return {"ok": True}
"""

ROUTER_WITH_INCLUDE_NO_VAR = """
from fastapi import FastAPI, APIRouter

app = FastAPI()
tasks_router = APIRouter(prefix="/tasks")
app.include_router(tasks_router)
"""


class TestFastAPIRouterRegistration:
    def test_registered_router_passes(self):
        ops = [_op("backend/main.py", ROUTER_WITH_APP)]
        result = _check_fastapi_router_registration(ops)
        assert result == []

    def test_unregistered_router_detected(self):
        ops = [_op("backend/main.py", ROUTER_WITHOUT_APP)]
        result = _check_fastapi_router_registration(ops)
        assert len(result) == 1
        assert result[0]["type"] == "unregistered_router"
        assert "include_router(router)" in result[0]["fix_hint"]

    def test_different_var_name_with_include_passes(self):
        ops = [_op("backend/main.py", ROUTER_WITH_INCLUDE_NO_VAR)]
        result = _check_fastapi_router_registration(ops)
        assert result == []

    def test_non_python_skipped(self):
        ops = [_op("frontend/App.tsx", ROUTER_WITHOUT_APP)]
        result = _check_fastapi_router_registration(ops)
        assert result == []

    def test_no_router_definition_passes(self):
        ops = [_op("backend/models.py", "from pydantic import BaseModel\n\nclass Task(BaseModel):\n    title: str\n")]
        result = _check_fastapi_router_registration(ops)
        assert result == []


# ══════════════════════════════════════════════════════════
# G9.2: 跨文件可变状态冲突
# ══════════════════════════════════════════════════════════

MODELS_WITH_STORE = """
from pydantic import BaseModel

task_store = {}

class Task:
    pass
"""

DEPENDENCIES_WITH_STORE = """
from typing import Generator

task_store = {}

def get_db():
    return task_store
"""

DEPENDENCIES_IMPORTING_STORE = """
from .models import task_store

def get_db():
    return task_store
"""


class TestCrossFileStateConflicts:
    def test_duplicate_store_detected(self):
        ops = [
            _op("backend/models.py", MODELS_WITH_STORE),
            _op("backend/dependencies.py", DEPENDENCIES_WITH_STORE),
        ]
        result = _check_cross_file_state_conflicts(ops)
        assert len(result) == 1
        assert result[0]["type"] == "duplicate_mutable_state"
        assert result[0]["variable"] == "task_store"
        assert "backend/dependencies.py" in result[0]["paths"]
        assert "backend/models.py" in result[0]["paths"]

    def test_importing_is_not_a_conflict(self):
        ops = [
            _op("backend/models.py", MODELS_WITH_STORE),
            _op("backend/dependencies.py", DEPENDENCIES_IMPORTING_STORE),
        ]
        result = _check_cross_file_state_conflicts(ops)
        assert result == []

    def test_singletons_not_reported(self):
        ops = [
            _op("backend/main.py", "app = FastAPI()\nrouter = APIRouter()\n"),
            _op("backend/sub.py", "app = FastAPI()\n"),
        ]
        result = _check_cross_file_state_conflicts(ops)
        # app is in HEADLESS_SINGLETON_NAMES
        assert all(r["variable"] != "app" for r in result)

    def test_no_store_no_conflict(self):
        ops = [
            _op("backend/models.py", "class Task: pass\n"),
            _op("backend/dependencies.py", "def get_db(): pass\n"),
        ]
        result = _check_cross_file_state_conflicts(ops)
        assert result == []

    def test_multiple_conflicting_vars(self):
        ops = [
            _op("a.py", "cache = {}\ndb = []\n"),
            _op("b.py", "cache = {}\ndb = {}\n"),
        ]
        result = _check_cross_file_state_conflicts(ops)
        assert len(result) == 2
        vars_found = {r["variable"] for r in result}
        assert vars_found == {"cache", "db"}


# ══════════════════════════════════════════════════════════
# G9.3: Python 语法验证
# ══════════════════════════════════════════════════════════

VALID_PY = "def foo():\n    return 42\n"
INVALID_PY = "def foo():\nreturn 42\n"
VALID_TS = "const x: number = 1;\n"


class TestPythonSyntax:
    def test_valid_python_passes(self):
        ops = [_op("app.py", VALID_PY)]
        assert _validate_python_syntax(ops) == []

    def test_invalid_python_detected(self):
        ops = [_op("app.py", INVALID_PY)]
        result = _validate_python_syntax(ops)
        assert len(result) == 1
        assert result[0]["type"] == "python_syntax_error"
        assert result[0]["path"] == "app.py"

    def test_typescript_skipped(self):
        ops = [_op("App.tsx", VALID_TS)]
        assert _validate_python_syntax(ops) == []

    def test_empty_content_skipped(self):
        ops = [_op("backend/__init__.py", "")]
        assert _validate_python_syntax(ops) == []


# ══════════════════════════════════════════════════════════
# G9.4: 导入完整性
# ══════════════════════════════════════════════════════════

MAIN_IMPORTING_DEPS = """
from .dependencies import get_db_session
from .models import TaskResponse
"""

MAIN_IMPORTING_MISSING = """
from .dependencies import get_db_session
from .nonexistent import Foo
"""


class TestImportIntegrity:
    def test_valid_imports_pass(self):
        ops = [
            _op("backend/main.py", MAIN_IMPORTING_DEPS),
            _op("backend/dependencies.py", "def get_db_session(): pass\n"),
            _op("backend/models.py", "class TaskResponse: pass\n"),
        ]
        result = _check_import_integrity(ops)
        assert result == []

    def test_orphan_import_detected(self):
        ops = [
            _op("backend/main.py", MAIN_IMPORTING_MISSING),
            _op("backend/dependencies.py", "def get_db_session(): pass\n"),
        ]
        result = _check_import_integrity(ops)
        assert len(result) == 1
        assert result[0]["type"] == "orphan_import"
        assert "nonexistent" in result[0]["detail"]

    def test_non_python_skipped(self):
        ops = [_op("App.tsx", "import React from 'react';\n")]
        assert _check_import_integrity(ops) == []


# ══════════════════════════════════════════════════════════
# G9.5: 前端依赖缺失
# ══════════════════════════════════════════════════════════

PKG_WITH_CRA_MISSING = """{
    "name": "frontend",
    "scripts": {
        "start": "react-scripts start",
        "build": "react-scripts build"
    },
    "dependencies": {
        "react": "^18.0.0"
    }
}"""

PKG_WITH_CRA_INSTALLED = """{
    "name": "frontend",
    "scripts": {
        "start": "react-scripts start"
    },
    "dependencies": {
        "react": "^18.0.0",
        "react-scripts": "5.0.1"
    }
}"""

PKG_NO_SCRIPTS = """{
    "name": "simple-pkg",
    "dependencies": {}
}"""


class TestFrontendDependencyGaps:
    def test_missing_react_scripts_detected(self):
        ops = [_op("frontend/package.json", PKG_WITH_CRA_MISSING)]
        result = _check_frontend_dependency_gaps(ops)
        assert len(result) == 1
        assert result[0]["type"] == "missing_frontend_dep"
        assert result[0]["dependency"] == "react-scripts"

    def test_installed_react_scripts_passes(self):
        ops = [_op("frontend/package.json", PKG_WITH_CRA_INSTALLED)]
        assert _check_frontend_dependency_gaps(ops) == []

    def test_no_scripts_passes(self):
        ops = [_op("package.json", PKG_NO_SCRIPTS)]
        assert _check_frontend_dependency_gaps(ops) == []

    def test_non_package_json_skipped(self):
        ops = [_op("backend/main.py", VALID_PY)]
        assert _check_frontend_dependency_gaps(ops) == []


# ══════════════════════════════════════════════════════════
# 集成测试: validate_generated_files 顶层入口
# ══════════════════════════════════════════════════════════

class TestValidateGeneratedFilesIntegration:
    def test_clean_project_passes(self):
        ops = [
            _op("backend/main.py", ROUTER_WITH_APP),
            _op("backend/models.py", "class Task: pass\n"),
            _op("frontend/package.json", PKG_WITH_CRA_INSTALLED),
        ]
        result = validate_generated_files(ops)
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_mixed_issues_all_detected(self):
        ops = [
            _op("backend/main.py", ROUTER_WITHOUT_APP),  # unregistered router
            _op("backend/models.py", MODELS_WITH_STORE),   # duplicate state
            _op("backend/dependencies.py", DEPENDENCIES_WITH_STORE),  # duplicate state
            _op("frontend/package.json", PKG_WITH_CRA_MISSING),  # missing dep
        ]
        result = validate_generated_files(ops)
        assert len(result["errors"]) >= 1  # unregistered_router
        assert len(result["warnings"]) >= 2  # duplicate + missing dep
        assert result["checks"]["errored"] >= 1
        assert result["checks"]["warned"] >= 2

    def test_merge_file_ops_triggers_validation(self):
        context = {}
        ops = [
            _op("backend/main.py", ROUTER_WITHOUT_APP),
            _op("backend/models.py", "class Task: pass\n"),
        ]
        merge_file_ops(context, ops, source_step="test")
        assert "validation" in context
        validation = context["validation"]
        assert len(validation["errors"]) >= 1
        assert any(e["type"] == "unregistered_router" for e in validation["errors"])

    def test_empty_file_ops_handles_gracefully(self):
        result = validate_generated_files([])
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["checks"]["passed"] == 0

    def test_result_structure(self):
        ops = [_op("app.py", VALID_PY)]
        result = validate_generated_files(ops)
        assert "errors" in result
        assert "warnings" in result
        assert "checks" in result
        assert "passed" in result["checks"]
        assert "warned" in result["checks"]
        assert "errored" in result["checks"]