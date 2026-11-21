# python_worker/tests/test_g1044_contracts.py
"""G10.44 占位 .db 资产守卫的契约测试。

真实故障（shopflow_v25_1，2026-11-15 22:29）：
`4 failed, 3 passed in 1214.37s`，R5/R6/R7 四维全绿，R8 质量维 ❌
（inventory 三文件全 True，却 `pytest 未通过`），R9/R10 前置连带红。
R9/R10 前置 stdout 一致：

    ImportError while loading conftest ... -> backend/main.py:9
    Base.metadata.create_all(bind=engine) ->
    sqlalchemy.exc.DatabaseError: (sqlite3.DatabaseError)
    file is not a database

根因：node_api_run30.log:636 `[Memory] 记录文件操作: create
backend/shopflow.db` —— LLM 生成了 `create backend/shopflow.db` op，
内容写成 66 字节占位文本 "# Binary SQLite database file. Generated at
runtime by SQLAlchemy."，覆盖了 R5 基线复位写入的有效 SQLite 二进制
（_shopflow_baseline.json 里 is_binary=True / content_b64 28672 字节 /
`SQLite format 3\\0` 头）。合规基线 backend/main.py **本就有**模块级
`Base.metadata.create_all(bind=engine)`，conftest 导入 main 即撞上损坏
DB ⇒ 全链崩。

snapshot_workspace 的 _SNAPSHOT_SUFFIXES 只含 .py/.ini/.cfg/.toml/.txt，
**不含 .db** ⇒ 闸门 base 里没有 shopflow.db，基于「候选/基线比对」的
G10.41/42 看不到、拦不住。G10.44 在放行前按 op 就地拒绝（FAIL-CLOSED），
拒绝后两端自洽：候选工作区临时目录里没有该 .db ⇒ SQLite 新建有效 DB；
落盘工作区不再被覆盖 ⇒ 保留 R5 复位写入的有效 DB。

契约：只拒绝「非空、非 SQLite 二进制头、无 NUL 的可读占位文本」写入
*.db；有效二进制头 / 空内容（0 字节 SQLite 自行初始化）/ 含 NUL 的二进制
乱码 / 非 .db / delete / _internal / 路径越界 / 绝对路径 / Windows 盘符
一律不误伤；Windows 路径归一化；就地改 final_file_ops（成长法第 35 条）；
幂等；gate() 接入且 fixes 可审计；真实 pytest 对照证明修复有效。
"""

import inspect
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import python_worker.delivery_gate as dg  # noqa: E402
from python_worker.delivery_gate import build_candidate  # noqa: E402

# v25 工作区 backend/shopflow.db 的真实内容（逐字，66 字节）
PLACEHOLDER_DB = "# Binary SQLite database file. Generated at runtime by SQLAlchemy."
VALID_DB_HEAD = "SQLite format 3\x00" + "\x00" * 20
BINARY_GARBAGE = "x\x00y\x00z"


# ── 1. 占位内容判定 ──────────────────────────────────────────────────

def test_placeholder_content_detection():
    assert dg._g1044_is_placeholder_db(PLACEHOLDER_DB) is True
    assert dg._g1044_is_placeholder_db("garbage text\n") is True
    # 有效情况一律不碰
    assert dg._g1044_is_placeholder_db("") is False          # 0 字节 → SQLite 自建
    assert dg._g1044_is_placeholder_db(VALID_DB_HEAD) is False
    assert dg._g1044_is_placeholder_db(BINARY_GARBAGE) is False  # 含 NUL
    assert dg._g1044_is_placeholder_db(None) is False
    assert dg._g1044_is_placeholder_db(123) is False


# ── 2. 拒绝 v25 真实占位 op，就地改 final_file_ops ────────────────────

def test_rejects_v25_placeholder_db_op_in_place():
    ops = [
        {"op": "create", "path": "backend/shopflow.db",
         "content": PLACEHOLDER_DB},
        {"op": "create", "path": "backend/main.py", "content": "x = 1\n"},
    ]
    rejected = dg.restore_corrupt_db_ops(ops)
    assert rejected == ["backend/shopflow.db"]
    # 就地改：落盘清单里不再有占位 .db op
    assert [o.get("path") for o in ops] == ["backend/main.py"]
    # 候选工作区也不含 .db（临时目录里 SQLite 会新建有效 DB）
    candidate = build_candidate({}, ops)
    assert "backend/shopflow.db" not in candidate
    assert candidate["backend/main.py"] == "x = 1\n"


def test_rejects_windows_path_placeholder_db():
    ops = [{"op": "modify", "path": "backend\\shopflow.db",
            "content": PLACEHOLDER_DB}]
    assert dg.restore_corrupt_db_ops(ops) == ["backend/shopflow.db"]
    assert ops == []


def test_rejects_other_db_suffixes():
    ops = [
        {"op": "create", "path": "backend/a.sqlite", "content": "placeholder"},
        {"op": "create", "path": "backend/b.sqlite3", "content": "placeholder"},
        {"op": "create", "path": "backend/c.db", "content": "placeholder"},
    ]
    assert dg.restore_corrupt_db_ops(ops) == [
        "backend/a.sqlite", "backend/b.sqlite3", "backend/c.db"]
    assert ops == []


# ── 3. 不误伤边界 ────────────────────────────────────────────────────

def test_valid_db_contents_untouched():
    ops = [
        {"op": "create", "path": "backend/valid.db",
         "content": VALID_DB_HEAD},
        {"op": "create", "path": "backend/empty.db", "content": ""},
        {"op": "create", "path": "backend/binary.db",
         "content": BINARY_GARBAGE},
    ]
    assert dg.restore_corrupt_db_ops(ops) == []
    assert len(ops) == 3


def test_non_db_and_non_writable_ops_untouched():
    ops = [
        {"op": "create", "path": "backend/notes.txt",
         "content": PLACEHOLDER_DB},
        {"op": "create", "path": "backend/main.py",
         "content": PLACEHOLDER_DB},
        {"op": "delete", "path": "backend/old.db"},
        {"op": "create", "path": "backend/internal.db",
         "content": PLACEHOLDER_DB, "_internal": True},
        {"op": "meta", "path": "backend/meta.db",
         "content": PLACEHOLDER_DB},
    ]
    assert dg.restore_corrupt_db_ops(ops) == []
    assert len(ops) == 5


def test_path_boundaries_untouched():
    ops = [
        {"op": "create", "path": "../evil.db", "content": PLACEHOLDER_DB},
        {"op": "create", "path": "/absolute/evil.db",
         "content": PLACEHOLDER_DB},
        {"op": "create", "path": "C:/evil.db", "content": PLACEHOLDER_DB},
        {"op": "create", "path": "backend/../escape.db",
         "content": PLACEHOLDER_DB},
        {"op": "create", "path": "", "content": PLACEHOLDER_DB},
    ]
    assert dg.restore_corrupt_db_ops(ops) == []
    assert len(ops) == 5


def test_empty_and_none_file_ops():
    assert dg.restore_corrupt_db_ops([]) == []
    assert dg.restore_corrupt_db_ops(None) == []


def test_idempotent():
    ops = [
        {"op": "create", "path": "backend/shopflow.db",
         "content": PLACEHOLDER_DB},
        {"op": "create", "path": "backend/main.py", "content": "x = 1\n"},
    ]
    assert dg.restore_corrupt_db_ops(ops) == ["backend/shopflow.db"]
    assert dg.restore_corrupt_db_ops(ops) == []
    assert [o.get("path") for o in ops] == ["backend/main.py"]


# ── 4. 落盘清单与已验证候选一致（成长法第 35 条）─────────────────────

def test_delivery_manifest_never_reintroduces_placeholder_db():
    base = {"backend/main.py": "old = 1\n"}   # snapshot 不含 .db
    ops = [
        {"op": "create", "path": "backend/shopflow.db",
         "content": PLACEHOLDER_DB},
        {"op": "modify", "path": "backend/main.py", "content": "new = 2\n"},
    ]
    ctx = {"final_file_ops": ops}
    dg.restore_corrupt_db_ops(ctx["final_file_ops"])
    candidate = build_candidate(base, ctx["final_file_ops"])
    assert "backend/shopflow.db" not in candidate
    dg._apply_back(ctx, candidate, base)
    delivered = build_candidate(base, ctx["final_file_ops"])
    assert "backend/shopflow.db" not in delivered
    assert delivered["backend/main.py"] == "new = 2\n"


def test_gate_wires_g1044_into_fixes():
    src = inspect.getsource(dg.gate)
    assert "restore_corrupt_db_ops" in src
    assert "db_fixes" in src
    assert "拒绝占位/损坏 .db 写入（G10.44）" in src


# ── 5. 真实 pytest 对照：占位 DB 崩 / G10.44 状态绿 ──────────────────
# 自包含最小项目精确复刻 v25 机制：backend/main.py 模块级
# Base.metadata.create_all(bind=engine) + 文件 DB backend/shopflow.db。

MINI_DATABASE = '''from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "shopflow.db"
engine = create_engine(f"sqlite:///{DB_PATH}",
                       connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

# 必须注册至少一张表，create_all 才会真正执行 DDL（PRAGMA table_info），
# 从而撞上损坏的 .db 文件；空 metadata 的 create_all 不碰文件、不会崩。
MINI_MODELS = '''from sqlalchemy import Column, Integer, String
from backend.database import Base


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    name = Column(String)
'''

MINI_MAIN = '''from fastapi import FastAPI
from backend.database import engine, Base
import backend.models  # noqa: F401  (注册模型，使 create_all 真正执行 DDL)

app = FastAPI()

# 精确复刻合规基线 / v25：模块级 create_all，导入即碰文件 DB
Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"ok": True}
'''

MINI_CONFTEST = '''import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope="function")
def client():
    with TestClient(app) as c:
        yield c
'''

MINI_TEST = '''def test_root(client):
    assert client.get("/").status_code == 200
'''


def _write_mini(root: Path, db_state: str):
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "database.py").write_text(MINI_DATABASE, encoding="utf-8")
    (root / "backend" / "models.py").write_text(MINI_MODELS, encoding="utf-8")
    (root / "backend" / "main.py").write_text(MINI_MAIN, encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(MINI_CONFTEST, encoding="utf-8")
    (root / "tests" / "test_app.py").write_text(MINI_TEST, encoding="utf-8")
    dbp = root / "backend" / "shopflow.db"
    if db_state == "placeholder":
        dbp.write_text(PLACEHOLDER_DB, encoding="utf-8")
    elif db_state == "empty":
        dbp.write_bytes(b"")          # 0 字节 → SQLite 自行初始化
    elif db_state == "absent":
        pass                          # 文件不存在 → SQLite 新建
    else:
        raise ValueError(db_state)


def _run_pytest(root: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--disable-warnings"],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
    )
    return r.returncode, r.stdout, r.stderr


def test_real_pytest_placeholder_db_crashes(tmp_path):
    """v25 实际落盘状态：占位文本 .db ⇒ create_all 崩。"""
    root = tmp_path / "placeholder"
    root.mkdir()
    _write_mini(root, "placeholder")
    rc, out, err = _run_pytest(root)
    assert rc != 0, (rc, out, err)
    assert "file is not a database" in (err + out)


def test_real_pytest_g1044_state_passes(tmp_path):
    """G10.44 拒绝占位 op 后：候选工作区无 .db / 落盘保留空 DB ⇒ 全绿。"""
    for state in ("absent", "empty"):
        root = tmp_path / state
        root.mkdir()
        _write_mini(root, state)
        rc, out, err = _run_pytest(root)
        assert rc == 0, (state, rc, out, err)
        assert "1 passed" in out, (state, out)


def test_real_pytest_g1044_end_to_end(tmp_path):
    """端到端：ops 含占位 .db → 守卫拒绝 → build_candidate 落盘 → pytest 绿。"""
    root = tmp_path / "e2e"
    root.mkdir()
    base = {
        "backend/__init__.py": "",
        "backend/database.py": MINI_DATABASE,
        "backend/models.py": MINI_MODELS,
        "backend/main.py": MINI_MAIN,
        "tests/__init__.py": "",
        "tests/conftest.py": MINI_CONFTEST,
        "tests/test_app.py": MINI_TEST,
    }
    ops = [
        {"op": "create", "path": "backend/shopflow.db",
         "content": PLACEHOLDER_DB},
    ]
    rejected = dg.restore_corrupt_db_ops(ops)
    assert rejected == ["backend/shopflow.db"]
    delivered = build_candidate(base, ops)
    assert "backend/shopflow.db" not in delivered
    for p, s in delivered.items():
        fp = root / p
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(s, encoding="utf-8")
    rc, out, err = _run_pytest(root)
    assert rc == 0, (rc, out, err)
    assert "1 passed" in out
