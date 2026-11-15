# -*- coding: utf-8 -*-
"""交付闸门（G10.15）：事务式候选工作区验证 + 失败分诊 + 自适应自愈 + FAIL-CLOSED。

为什么需要它
------------
旧 ShadowVerify 有三个结构性缺陷（shopflow_full_run1/1b/1c 实证）：

1. **沙箱缺基础工作区**：只把本次 file_ops 写进空临时目录，增量轮次
   （R8 新增库存模块）必然因缺少 backend/ 既有模块而报
   `ModuleNotFoundError`，是假失败；而真实工作区又确实被写入了
   `from backend.models.base import Base` 这类**幻觉导入**，是真失败。
2. **同构重试**：固定 2 轮，每轮同模型/同 prompt/只换最新报错，
   没有「已尝试修复历史」和失败签名对比，收敛就靠多摇骰子。
3. **自检失败仍放行**：`EvidenceGate` 不看 pytest 结果，缺陷交付照样落盘，
   R8 的 15 个失败直接把 R9/R10 前置全部带崩。

工业级改造（本模块）
--------------------
* **事务式验证**：快照真实工作区 → 在临时副本里应用本次 file_ops →
  跑真实 pytest；通过才允许落盘（P2 蓝绿式交付）。
* **失败分诊**：项目内部模块/符号不存在 → 确定性符号解析修复
  （自动重定向到真正定义该符号的模块，或删除幻觉导入），不消耗 LLM 轮次。
* **自适应预算**：每轮算 failure_signature（失败用例集合 + 错误类型 + 数量）；
  只有 `converging` 才续轮，上限 5；`stalled` / `worsening` 立即止损（P3/P4）。
* **异策略升级**：每轮 prompt 带上轮签名变化、已尝试改动、失败增量，
  并随轮次提高温度、切换根因假设（P3）。
* **FAIL-CLOSED**：最终仍失败且工作区存在良好基线（已有 tests/）时，
  丢弃写操作 = 保留磁盘现状 + 标记 partial，绝不把缺陷扩散到下一轮（P0）。

治理边界
--------
* 绝不写用户工作区：所有验证都在 tempfile.TemporaryDirectory() 里。
* 绝不改变授权边界：写盘仍由 Node API 侧授权。
* FAIL-OPEN 保护：无工作区 / 无既有 tests 基线（R6 从零建项目）/
  快照异常 → 闸门不启用，交回旧沙箱逻辑，不误伤建项目轮次。
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeout
from pathlib import Path

_MAX_REPAIR_ROUNDS = 5
# G10.25：单次 LLM 调用的 wall-clock 硬上限 & 闸门整体预算。
# 二者共同保证「上游半开连接」不可能把长驻 Worker 无限挂住。
_REPAIR_LLM_HARD_TIMEOUT = int(
    os.getenv("ALPHAPILOT_REPAIR_LLM_TIMEOUT", "120"))
_GATE_TOTAL_BUDGET_SEC = int(
    os.getenv("ALPHAPILOT_GATE_TOTAL_BUDGET", "900"))
_PYTEST_TIMEOUT = 90
_ERROR_LIMIT = 4000
_PROMPT_LIMIT = 24000
_SNAPSHOT_SUFFIXES = (".py", ".ini", ".cfg", ".toml", ".txt")
_SKIP_PARTS = {".venv", "venv", "__pycache__", ".git", ".pytest_cache",
               ".alphapilot", "node_modules", ".idea", "dist", "build"}
_MAX_FILES = 200
_MAX_FILE_BYTES = 200_000

_FROM_RE = re.compile(r"^\s*from\s+([\w\.]+)\s+import\s+(.+?)\s*$")
_IMPORT_RE = re.compile(r"^\s*import\s+([\w\.]+)")
_ERROR_TYPES_RE = re.compile(
    r"\b(ModuleNotFoundError|ImportError|SyntaxError|AssertionError|KeyError|"
    r"TypeError|AttributeError|NameError|ValueError|RuntimeError|"
    r"OperationalError|IntegrityError|ValidationError)\b"
)
_FAILED_RE = re.compile(r"(?:FAILED|ERROR)\s+([\w/\\.:\-]+::[\w\[\]\-]+)")

# G10.24：收集期崩溃（failed_count = -1）时的根因级指纹。
# 旧签名此时只有「错误类型集合」，语法坏行从 A 文件挪到 B 文件、
# 未定义符号从 X 变成 Y 都会算出同一个 sig，第二轮就被误判 stalled
# 止损（shopflow_v5_1 的 R6/R8 实证）。归一掉临时目录与行号，只保留
# 「出错文件相对路径 + 错误类型 + 错误消息/符号」。
_CRASH_PY_RE = re.compile(r"([\w\\/.\-]+\.py)(?::\d+|\",\s*line\s+\d+)")
_CRASH_ERR_RE = re.compile(
    r"(?:^\s*E\s+)?(SyntaxError|IndentationError|NameError|ModuleNotFoundError|"
    r"ImportError|AttributeError|TypeError|RuntimeError|OperationalError|"
    r"IntegrityError):\s*(.+)$")


def _crash_fingerprint(text: str) -> str:
    """从 pytest 收集期 traceback 提取稳定的根因指纹；无信息时返回空串。"""
    roots = ("backend/", "tests/", "app/", "src/")
    paths, errs = [], []
    for line in (text or "").splitlines():
        for m in _CRASH_PY_RE.finditer(line):
            p = m.group(1).replace("\\", "/")
            low = p.lower()
            hits = [low.find(r) for r in roots if r in low]
            rel = p[min(hits):] if hits else p.rsplit("/", 1)[-1]
            if rel not in paths:
                paths.append(rel)
        m = _CRASH_ERR_RE.match(line)
        if m:
            msg = re.sub(
                r"['\"]?(?:[A-Za-z]:)?[^\s'\"]*alphapilot-gate-[^\s'\"]*['\"]?",
                "<tmp>", m.group(2).strip())
            item = f"{m.group(1)}:{msg[:100]}"
            if item not in errs:
                errs.append(item)
    return "|".join(["F:" + p for p in paths[:8]]
                    + ["E:" + e for e in errs[:8]])


# ── 快照与候选工作区 ──────────────────────────────────────────────

def snapshot_workspace(ws_root: str) -> dict:
    """只读快照工作区文本配置与源码，返回 {相对路径: 内容}。"""
    root = Path(ws_root)
    if not root.is_dir():
        return {}
    out = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _SKIP_PARTS for part in rel_parts):
            continue
        if p.suffix not in _SNAPSHOT_SUFFIXES:
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
            out[p.relative_to(root).as_posix()] = p.read_text(
                encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(out) >= _MAX_FILES:
            break
    return out


def build_candidate(files: dict, file_ops: list) -> dict:
    """把本次写操作应用到快照副本（不碰磁盘），路径越界一律跳过。"""
    out = dict(files)
    for op in file_ops or []:
        if op.get("op") not in ("create", "update", "modify", "test", "doc"):
            continue
        if op.get("_internal"):
            continue
        raw = str(op.get("path") or "").replace("\\", "/").strip()
        if not raw or raw.startswith("/") or ":" in raw.split("/")[0]:
            continue
        parts = [s for s in raw.split("/") if s]
        if not parts or ".." in parts:
            continue
        content = op.get("content")
        if content is None:
            continue
        out["/".join(parts)] = str(content)
    return out


# ── 失败签名与进展检测 ────────────────────────────────────────────

def failure_signature(output: str) -> dict:
    """从 pytest 输出提取稳定签名（失败用例集合 + 错误类型 + 数量）。"""
    text = output or ""
    failed = sorted(set(_FAILED_RE.findall(text)))
    errs = sorted(set(_ERROR_TYPES_RE.findall(text)))
    counts = re.findall(r"(\d+) failed", text)
    failed_count = int(counts[-1]) if counts else (len(failed) or -1)
    crash = _crash_fingerprint(text) if failed_count < 0 else ""
    # 无崩溃指纹时完全沿用旧公式，保证既有签名契约不回归
    raw = "|".join(failed) + "#" + "|".join(errs)
    if crash:
        raw += "#" + crash
    sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return {"failed_count": failed_count, "failed_tests": failed,
            "error_types": errs, "crash": crash, "sig": sig}


def progress(prev: dict | None, cur: dict) -> str:
    """判断自愈是否在收敛 —— 决定要不要继续烧额度。"""
    if not prev:
        return "first"
    if cur["sig"] == prev["sig"]:
        return "stalled"
    # -1 = 导入崩溃/无法收集测试；变成可量化的失败数说明根因已解决，
    # 是明确进展，绝不能判成停滞（run1d 实证：ImportError → 4 failed）。
    if prev["failed_count"] < 0 <= cur["failed_count"]:
        return "converging"
    # G10.22：两轮都还在「无法收集」阶段时，failed_count 恒为 -1，
    # 数量维度完全失效。shopflow_v3_1 的 R6 实证：
    # [ImportError, ModuleNotFoundError] → [ImportError, NameError]
    # 是「不存在的模块已解决、暴露出下一个根因」的明确收敛，旧逻辑却判
    # stalled 直接止损，一次修复机会都没给第二轮。
    # 规则：模块级错误消失，或错误类型集合发生变化，都算进展；
    # 5 轮预算上限仍然兜底，避免无限重试。
    if prev["failed_count"] < 0 and cur["failed_count"] < 0:
        _module_errors = ("ModuleNotFoundError", "ImportError")
        if (any(t in prev["error_types"] for t in _module_errors)
                and not any(t in cur["error_types"] for t in _module_errors)):
            return "converging"
        if set(cur["error_types"]) != set(prev["error_types"]):
            return "converging"
        # G10.24：错误类型集合没变，但根因位置/消息变了（语法坏行从
        # A 文件挪到 B 文件、未定义符号从 X 换成 Y），说明上一轮确实
        # 消掉了一个崩溃点并暴露下一个，属于收敛而非同构重摇。
        if (cur.get("crash") and prev.get("crash")
                and cur["crash"] != prev["crash"]):
            return "converging"
    if ("ImportError" in prev["error_types"]
            or "ModuleNotFoundError" in prev["error_types"]) \
            and not any(t in cur["error_types"]
                        for t in ("ImportError", "ModuleNotFoundError")):
        return "converging"
    if prev["failed_count"] >= 0 and cur["failed_count"] > prev["failed_count"]:
        return "worsening"
    if (cur["failed_count"] >= 0 and prev["failed_count"] >= 0
            and cur["failed_count"] < prev["failed_count"]):
        return "converging"
    if len(cur["error_types"]) < len(prev["error_types"]):
        return "converging"
    return "stalled"


# ── 确定性失败分诊：幻觉导入修复 ──────────────────────────────────

def _module_symbols(files: dict, defined_only: bool = False) -> dict:
    """ast 收集候选工作区每个模块的顶层可见符号。

    defined_only=True 时只认本模块**真正定义**的符号（类/函数/赋值），
    不把 `from X import Y` 的 re-export 算作提供者 —— 否则坏模块
    `from backend.models.base import Base` 会把自己伪装成 Base 的提供者，
    造成重定向歧义。
    """
    syms = {}
    for path, src in files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Import):
                if defined_only:
                    continue
                for a in node.names:
                    names.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if defined_only:
                    continue
                for a in node.names:
                    names.add(a.asname or a.name)
        mod = path[:-3].replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[:-len(".__init__")]
        syms[mod] = names
    return syms


def _module_exists(mod: str, files: dict) -> bool:
    rel = mod.replace(".", "/")
    return f"{rel}.py" in files or f"{rel}/__init__.py" in files


def _pick_provider(bad_mod: str, name: str, defined: dict) -> str | None:
    """从符号定义者里挑最可信的模块；歧义时按模块语义打分。

    ShopFlow 实证：`Base` 同时由 backend/database.py 与 backend/main.py
    定义（都写了 declarative_base()），「只认唯一」会把 import 直接删掉，
    导致 NameError。database/base/session 类模块比 main/app 入口更可信。
    """
    providers = [m for m, ns in defined.items() if name in ns and m != bad_mod]
    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]

    def score(m: str) -> int:
        low = m.lower()
        s = 0
        if any(k in low for k in ("database", "base", "session")):
            s -= 3
        if any(k in low for k in ("models", "schemas", "entities")):
            s -= 1
        if low.split(".")[-1] in ("main", "app", "__init__", "conftest"):
            s += 3
        return s

    ranked = sorted(providers, key=lambda m: (score(m), m))
    return ranked[0] if score(ranked[0]) < 0 else None


def resolve_internal_imports(files: dict) -> tuple[dict, list]:
    """修复项目内部幻觉导入（确定性，零 LLM 依赖）。

    * 模块不存在（如 backend.models.base）→ 把每个导入名重定向到
      候选工作区里**唯一**定义了该符号的模块（如 backend.database.Base）；
      找不到定义则删除该 import 行。
    * 模块存在但符号不存在（如 OrderItem）→ 同上处理单个名字。
    * 外部/标准库模块一律不动（第三方依赖不在 Worker venv 属正常）。
    """
    syms = _module_symbols(files)                       # 模块可见名（含 re-export）
    defined = _module_symbols(files, defined_only=True)  # 重定向只认真实定义者
    first_dirs = {k.split("/")[0] for k in files}
    fixes = []
    out = dict(files)
    for path, src in list(out.items()):
        if not path.endswith(".py"):
            continue
        lines = src.splitlines()
        new_lines = []
        changed = False
        for line in lines:
            m = _FROM_RE.match(line)
            if m and m.group(1).split(".")[0] in first_dirs:
                mod, names_str = m.group(1), m.group(2)
                mod_syms = syms.get(mod, set()) if _module_exists(mod, files) else set()
                keep, redirected, dropped = [], [], []
                for raw in names_str.split(","):
                    piece = raw.strip()
                    if not piece:
                        continue
                    name = piece.split(" as ")[0].strip()
                    # 从包导入子模块（from backend.routers import orders）
                    # 是合法的，不能按"符号不存在"误删。
                    if _module_exists(f"{mod}.{name}", files):
                        keep.append(piece)
                        continue
                    if name == "*" or (name in mod_syms and _module_exists(mod, files)):
                        keep.append(piece)
                        continue
                    provider = _pick_provider(mod, name, defined)
                    if provider:
                        redirected.append(f"from {provider} import {piece}")
                    else:
                        dropped.append(name)
                if redirected or dropped:
                    changed = True
                    fixes.append(
                        f"{path}: {mod} → 重定向 {redirected or '无'} / 丢弃 {dropped}")
                    if keep:
                        new_lines.append(f"from {mod} import " + ", ".join(keep))
                    new_lines.extend(redirected)
                    continue
            im = _IMPORT_RE.match(line)
            if im and im.group(1).split(".")[0] in first_dirs:
                if not _module_exists(im.group(1), files):
                    changed = True
                    fixes.append(f"{path}: 删除不存在的模块 import {im.group(1)}")
                    continue
            new_lines.append(line)
        if changed:
            out[path] = "\n".join(new_lines) + ("\n" if src.endswith("\n") else "")
    return out, fixes


_NAME_ERROR_RE = re.compile(r"NameError: name '([A-Za-z_]\w*)' is not defined")


def _repair_undefined_router_imports(files: dict, error_text: str) -> tuple[dict, list]:
    """确定性修复 FastAPI 路由注册里「引用了未导入的 router 名」（G10.22）。

    shopflow_v3_1 的 R6 实证：`backend/main.py` 写
    `app.include_router(orders_router, ...)`，但 `backend/routers/orders.py`
    定义的是 `router`、`backend/routers/__init__.py` 只在 `__all__` 里声明
    `orders_router` 却没导入 → `NameError`，pytest 连收集都做不到。
    这类命名断裂每次都靠 LLM 重猜，成本高且不稳定。

    规则（严格、零歧义才动手）：
      1. 报错是 `NameError: name '<X>' is not defined` 且 X 含 router；
      2. 候选工作区里恰好一个文件用 `include_router(X, ...)`；
      3. 候选工作区里恰好一个其它模块定义了顶层 `APIRouter()` 实例；
    满足则补一条 `from <module> import <var> as <X>`（同名则不带 alias）。
    任何一步不唯一就完全不动，交回 LLM 修复轮。
    """
    m = _NAME_ERROR_RE.search(error_text or "")
    if not m:
        return files, []
    missing = m.group(1)
    if "router" not in missing.lower():
        return files, []
    targets = [p for p, s in files.items()
               if p.endswith(".py") and re.search(
                   r"include_router\(\s*" + re.escape(missing) + r"\b", s)]
    if len(targets) != 1:
        return files, []
    target = targets[0]

    providers = []
    for p, src in files.items():
        if not p.endswith(".py") or p == target or p.endswith("/__init__.py"):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            fn = node.value.func
            fname = (fn.id if isinstance(fn, ast.Name)
                     else fn.attr if isinstance(fn, ast.Attribute) else "")
            if fname != "APIRouter":
                continue
            for t in node.targets:
                if isinstance(t, ast.Name):
                    providers.append((p, t.id))
    if len(providers) != 1:
        return files, []
    provider_path, defined = providers[0]
    module = provider_path[:-3].replace("/", ".").rstrip(".")
    line = (f"from {module} import {defined}" if defined == missing
            else f"from {module} import {defined} as {missing}")
    src = files[target]
    if line in src or re.search(rf"\b{re.escape(missing)}\b\s*=", src):
        return files, []
    new_src = line + "\n" + src
    try:
        ast.parse(new_src)
    except SyntaxError:
        return files, []
    out = dict(files)
    out[target] = new_src
    return out, [f"{target}: 补 {line}（修复未定义的 {missing}）"]


# ── G10.24：断裂多行 import 的确定性修复 ─────────────────────────
_COMPLETE_IMPORT_LINE_RE = re.compile(
    r"^\s*from\s+[\w.]+\s+import\s+[\w., \t]+$")
_ORPHAN_CONT_RE = re.compile(
    r"^\s+[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*\s*,?\s*$")
_CLOSE_PAREN_RE = re.compile(r"^\s*[\)\]\}][,]?\s*$")


def _repair_broken_syntax(files: dict) -> tuple[dict, list]:
    """确定性修复 LLM 生成时断裂的多行 import（零 LLM、FAIL-CLOSED）。

    真实形态（shopflow_v5_1 的 R10 产物 `backend/services/order_service.py`）：

        from backend.schemas.order import OrderCreate
            OrderNotFoundException,
            InvalidStatusTransitionException,
            InvalidStatusValueException
        )

    首行没有开括号，后续是缩进续行 + 孤立右括号 → SyntaxError，
    pytest 连收集都做不到。旧闸门把这种纯语法断裂交给 LLM 重猜，
    上游抖动时 5 轮都修不回来，且失败签名恒为 `['ImportError']`，
    第 2 轮就被误判 stalled 止损。

    规则：把续行标识符合并回首行形成合法单行 import，删除续行与孤立
    右括号，整体 ast.parse 自检通过才应用。合并进来的幻觉符号由紧随
    其后的 resolve_internal_imports() 按模块真实符号清理，不臆造。
    """
    out, fixes = {}, []
    for path, src in files.items():
        if not path.endswith(".py"):
            continue
        try:
            ast.parse(src)
            continue
        except SyntaxError:
            pass
        lines = src.splitlines()
        trailing = "\n" if src.endswith("\n") else ""
        rebuilt, changed = [], False
        i = 0
        while i < len(lines):
            line = lines[i]
            if (not _COMPLETE_IMPORT_LINE_RE.match(line)
                    or line.rstrip().endswith(("(", ",", "\\"))):
                rebuilt.append(line)
                i += 1
                continue
            j, block = i + 1, []
            while (j < len(lines) and lines[j].strip()
                   and _ORPHAN_CONT_RE.match(lines[j])):
                block.append(lines[j])
                j += 1
            if block and j < len(lines) and _CLOSE_PAREN_RE.match(lines[j]):
                names = []
                for b in block:
                    for tok in re.findall(r"[A-Za-z_]\w*", b):
                        if tok != "as" and tok not in names:
                            names.append(tok)
                merged = line.rstrip().rstrip(",")
                if names:
                    merged += ", " + ", ".join(names)
                try:
                    ast.parse(merged)
                except SyntaxError:
                    rebuilt.append(line)
                    i += 1
                    continue
                rebuilt.append(merged)
                i = j + 1
                changed = True
                fixes.append(f"{path}: 合并断裂的多行 import（{len(block)} 行续行）")
                continue
            rebuilt.append(line)
            i += 1
        if not changed:
            continue
        cand = "\n".join(rebuilt) + trailing
        try:
            ast.parse(cand)
        except SyntaxError:
            continue
        out[path] = cand
    if not out:
        return files, []
    merged_files = dict(files)
    merged_files.update(out)
    return merged_files, fixes


# ── 题面显式状态码约束的确定性修复（G10.29）──────────────────────
# R10 题面明确写「POST / 返回 200（不是 201）」，LLM 重构服务层时仍生成
# `status_code=status.HTTP_201_CREATED`：pytest 能过，但语义契约门判
# 「inventory: POST / 状态码 201 != 期望 200」而整轮失败。这类偏差是
# 题面已经写死的数值约束，交给自愈 LLM 重猜既不收敛也不必要：
# 在候选工作区落盘前做一次定点确定性纠正，零 LLM、零重试预算。
# 只在题面同时给出「期望值 + 明确禁止值」时触发，不做泛化猜测。

_EXPLICIT_STATUS_RE = re.compile(
    r"返回\s*(\d{3})\s*[（(]\s*不是\s*(\d{3})\s*[)）]")


def _repair_explicit_status_code(files: dict, user_request: str) -> tuple[dict, list]:
    """把题面明令禁止的 HTTP 状态码在路由文件中纠正为期望值。"""
    pairs = _EXPLICIT_STATUS_RE.findall(user_request or "")
    if not pairs:
        return files, []
    desired, forbidden = pairs[0]
    out = dict(files)
    fixes = []
    for path, content in list(out.items()):
        if not (path.startswith("backend/routers/") and path.endswith(".py")):
            continue
        # 仅替换装饰器 status_code= 的字面量或 status.HTTP_xxx 常量，
        # 不触碰业务返回体、错误码与测试断言里的同值数字。
        replaced = re.sub(
            rf"status_code\s*=\s*(?:{forbidden}|status\.HTTP_{forbidden}_\w+)",
            f"status_code={desired}", str(content))
        if replaced != content:
            out[path] = replaced
            fixes.append(f"{path}: status_code {forbidden} → {desired}")
    return out, fixes


# ── 题面显式枚举级联替换的确定性修复（G10.30）──────────────────────
# v9 第 1 遍 R9 的真实失败链：题面把三组映射写死（"confirmed" →
# "processing" 等）并要求「所有引用一次性全部更新、不得遗留旧词」，
# LLM 却在 write/refine/docstring 多步里只改了部分文件：候选工作区
# pytest 10 failed(AssertionError)，两轮签名不变判 stalled，分层收敛
# 回滚 20 个既有文件修改 → 真实工作区 enums.py 里三个旧值一个没少。
# 这是「题面已给出完整映射」的机械替换，不该交给自愈 LLM 重猜：
# 在候选工作区跑 pytest 前做一次纯文本三态替换，零 LLM、零重试预算。
# 触发条件刻意收紧：≥2 组带引号映射 + 题面同时含「枚举」与级联范围词，
# 其余轮次（R5 架构 / R10 服务层重构等）一律不触发。

_ENUM_CASCADE_PAIR_RE = re.compile(
    r'["“]([a-z][a-z0-9_]*)["”]\s*(?:→|->|=>)\s*["“]([a-z][a-z0-9_]*)["”]')
_CASCADE_SCOPE_RE = re.compile(r"枚举|状态值")
_CASCADE_RANGE_RE = re.compile(r"所有|全部|不要遗留|一次性|级联")


def _enum_cascade_pairs(user_request: str) -> list:
    """仅当题面明确给出枚举级联语义时，返回 (旧值, 新值) 映射列表。"""
    req = user_request or ""
    if not (_CASCADE_SCOPE_RE.search(req) and _CASCADE_RANGE_RE.search(req)):
        return []
    pairs = _ENUM_CASCADE_PAIR_RE.findall(req)
    # 去重且至少 2 组：单组映射可能是普通说明文字，不足以判定为级联替换
    seen, out = set(), []
    for old, new in pairs:
        if old == new or (old, new) in seen:
            continue
        seen.add((old, new))
        out.append((old, new))
    return out if len(out) >= 2 else []


def _repair_enum_cascade(files: dict, user_request: str) -> tuple[dict, list]:
    """把题面写死的枚举值级联替换到候选工作区的全部 .py 文件。"""
    pairs = _enum_cascade_pairs(user_request)
    if not pairs:
        return files, []
    out = dict(files)
    fixes = []
    for path, content in list(out.items()):
        if not path.endswith(".py"):
            continue
        parts = Path(path).parts
        if any(seg in _SKIP_PARTS or seg == "site-packages" for seg in parts):
            continue
        # 题面明令「不要改动 backend/main.py」，且该文件不持有状态值
        if path == "backend/main.py":
            continue
        src = str(content)
        new = src
        for old, repl in pairs:
            for a, b in ((old.upper(), repl.upper()),
                         (old.capitalize(), repl.capitalize()),
                         (old, repl)):
                new = new.replace(a, b)
        if new == src:
            continue
        # 语法守卫：替换后必须仍是合法 Python，否则宁可保留原文
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        out[path] = new
        fixes.append(f"{path}: 枚举级联替换 {len(pairs)} 组")
    return out, fixes


def _retry_with_deterministic_fix(candidate: dict, output: str,
                                  fixes: list) -> tuple[dict, bool, str]:
    """pytest 失败后先做一轮零 LLM 的确定性分诊，成功就不烧修复轮次。"""
    cand, det = _repair_undefined_router_imports(candidate, output)
    det = list(det)
    cand, syntax_fixes = _repair_broken_syntax(cand)
    det.extend(syntax_fixes)
    if det:
        # 语法修复后首次能 AST 解析这些文件，需再跑一次幻觉导入清理
        cand, import_fixes = resolve_internal_imports(cand)
        det.extend(import_fixes)
    if not det:
        return candidate, False, output
    fixes.extend(det)
    print(f"[DeliveryGate] 确定性修复: {det[0]}"
          + (f" 等 {len(det)} 处" if len(det) > 1 else ""))
    ok, out = _run_pytest(cand)
    return cand, ok, out


# ── 事务式 pytest ─────────────────────────────────────────────────

def _run_pytest(files: dict) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="alphapilot-gate-") as tmp:
        root = Path(tmp)
        for rel, src in files.items():
            target = root / rel
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(src, encoding="utf-8")
            except Exception:
                continue
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": str(root)}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--disable-warnings"],
                cwd=str(root), capture_output=True, text=True,
                timeout=_PYTEST_TIMEOUT, env=env)
        except subprocess.TimeoutExpired:
            return False, f"候选工作区 pytest 超时（{_PYTEST_TIMEOUT}s）"
        except Exception as e:
            return False, f"候选工作区 pytest 启动失败: {type(e).__name__}: {e}"
        if proc.returncode == 5:
            return True, "候选工作区无测试用例，跳过"
        output = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-_ERROR_LIMIT:]
        return proc.returncode == 0, output


def _relevant_sources(files: dict, error_text: str, limit: int = _PROMPT_LIMIT) -> str:
    """优先放报错涉及的文件与 tests/，控制 prompt 总长。"""
    mentioned = set(re.findall(r"([\w/\\.]+\.py)", error_text or ""))
    items = list(files.items())

    def score(item):
        path = item[0]
        return (0 if any(path.endswith(m.replace("\\", "/").split("/")[-1])
                         for m in mentioned) else 1,
                0 if path.startswith("tests/") else 1,
                0 if any(k in path for k in ("schema", "model", "router")) else 1)

    items.sort(key=score)
    blocks, total = [], 0
    for path, src in items:
        if not path.endswith(".py"):
            continue
        block = f"# FILE: {path}\n{src}\n"
        if total + len(block) > limit:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks)


def _repair_prompt(files: dict, error_text: str, user_request: str,
                   history: list, round_no: int) -> str:
    strategy = (
        "第 1 轮：优先做最小修复。若报错来自本次新生成的测试文件，"
        "应让测试适配既有 API 契约（字段、状态码、路径），不得反过来删改既有业务文件。"
        if round_no == 1 else
        f"第 {round_no} 轮：上一轮修复未收敛，必须换一个根因假设。"
        "重点检查：自生成测试是否与既有 schema/路由契约一致、"
        "是否有指向不存在模块或不存在符号的 import、字段类型是否匹配。"
        "禁止重复上一轮方案，禁止改动既有业务文件的公开契约。"
    )
    return (
        "你是代码交付前的最后一道事务式自检修复步骤。以下文件已放入隔离的"
        "候选工作区（包含既有项目全部源码），运行 pytest 得到【真实报错】。\n\n"
        f"【本轮策略】{strategy}\n\n"
        "硬性要求：\n"
        "1. 只修复报错指出的真实问题，禁止重构、禁止新增功能；\n"
        "2. 只输出【需要修改】的文件，用 `# FILE: 相对路径` 开头，"
        "后接该文件完整内容；未修改的文件不要输出；\n"
        "3. 不要输出任何说明文字、Markdown 标题或代码围栏，只输出文件块；\n"
        "4. 每个文件必须是完整、语法合法的源码；\n"
        "5. 严格遵守用户原始请求里的字段、类名、状态码与路径契约。\n\n"
        f"=== 用户原始请求 ===\n{(user_request or '')[:1500]}\n\n"
        f"=== 本轮真实报错 ===\n{(error_text or '')[:_ERROR_LIMIT]}\n\n"
        f"=== 已尝试修复历史（失败签名 / 收敛判断）===\n{history}\n\n"
        "=== 候选工作区源码 ===\n" + _relevant_sources(files, error_text)
    )


_WRITABLE_OPS = ("create", "update", "modify", "test", "doc")


def _apply_back(context: dict, candidate: dict, base: dict) -> int:
    """把闸门内验证通过的改动回写到 final_file_ops（唯一真相源）。

    G10.19：`final_file_ops` 开头常有「清理上次生成文件」的 `delete` op。
    旧实现按路径找 op 时不看类型，会把闸门修复后的源码挂到 delete op 上；
    Node 侧 `case 'delete'` 直接抛错拒绝执行（删除须走 VSCode 工作区工具），
    于是**候选工作区已验证通过的修复静默丢失**，磁盘仍是旧版。
    shopflow_3pass_1 的 R8 实证：闸门第 1 轮已把库存联动修到 pytest 通过，
    但 orders.py 的 mtime 没变，质量门仍 3 failed。
    规则：delete/meta/depends 一律不作为回写目标，缺失路径补一条可写 op。
    """
    ops = context.setdefault("final_file_ops", [])
    by_path = {}
    for op in ops:
        if op.get("_internal"):
            continue
        if op.get("op") not in _WRITABLE_OPS:
            continue
        p = str(op.get("path") or "").replace("\\", "/").lstrip("./")
        if p:
            by_path[p] = op
    written = 0
    for path, content in candidate.items():
        if base.get(path) == content:
            continue
        op = by_path.get(path)
        if op is not None:
            op["content"] = content
        else:
            ops.append({"op": "modify" if path in base else "create",
                        "path": path, "content": content,
                        "file_type": "file",
                        "reason": "交付闸门确定性修复"})
        written += 1
    return written


# ── G10.20: LLM 修复调用的网络瞬断退避 ────────────────────────────
# shopflow_final_1 实证：闸门已收敛（-1 failed ImportError → 5 failed
# AssertionError / converging），第 3 轮修复时 dashscope ConnectTimeout，
# 整条降级链「所有模型不可用」，旧实现直接 break → 分层收敛回滚 9 个既有
# 文件修改，R8 质量判红。这是基础设施抖动，不是代码缺陷，不该判死。
_REPAIR_LLM_ATTEMPTS = 3
_REPAIR_LLM_BACKOFF = (3, 8)
_TRANSIENT_MARKERS = (
    "Timeout", "timed out", "ConnectTimeout", "ReadTimeout",
    "ConnectionError", "RemoteDisconnected", "SSLEOFError",
    "所有模型不可用", "429", "502", "503", "504",
)


def _is_transient_llm_error(exc: Exception) -> bool:
    return any(m in str(exc) for m in _TRANSIENT_MARKERS)


def _call_llm_hard_timeout(call_llm, prompt: str, temperature: float,
                           timeout: float) -> str:
    """单次 LLM 调用的 wall-clock 硬上限（G10.25）。

    `requests` 的 read timeout 在 `stream=True` 时只约束**相邻 chunk 之间**
    的间隔，不约束总时长，更不约束「首个 chunk 之前」的等待。上游或本机
    代理半开连接时（Tunnel 502 后不吐数据也不关闭），首个 chunk 永远不到，
    调用既不返回也不抛异常 —— G10.20 的退避重试完全不触发，长驻 Worker
    主线程被冻住，整条队列阻塞、任务跑满轮询预算留下僵尸。
    shopflow_v6_1 实证：闸门日志停在 `调用模型: qwen3.5-plus` 后再无输出。

    Windows 没有 signal.alarm，用单线程 executor + `result(timeout=)`；
    超时后必须 `shutdown(wait=False)`，否则 `with` 会反过来等挂起的线程。
    抛出带 `Timeout` 标记的异常，交给 G10.20 既有「跳过本轮继续自愈」路径。
    """
    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(call_llm, prompt, temperature)
    try:
        return fut.result(timeout=timeout)
    except _FutureTimeout:
        fut.cancel()
        raise TimeoutError(
            f"Timeout: LLM 修复调用超过 {timeout}s 硬上限（上游半开连接）")
    finally:
        # 正常/异常路径都不能阻塞等待线程收尾
        pool.shutdown(wait=False, cancel_futures=True)


def _call_repair_llm(prompt: str, temperature: float, call_llm,
                     timeout: float | None = None) -> str:
    """带退避 + 单次硬超时的修复调用；最后一次仍失败才抛出。"""
    # 保留浮点精度：int(0.x) 会被截成 0 再被下限抬成 1s，短预算场景失效
    limit = max(0.01, float(timeout or _REPAIR_LLM_HARD_TIMEOUT))
    last = None
    for attempt in range(_REPAIR_LLM_ATTEMPTS):
        try:
            return _call_llm_hard_timeout(call_llm, prompt, temperature, limit)
        except Exception as e:
            last = e
            if not _is_transient_llm_error(e) or attempt == _REPAIR_LLM_ATTEMPTS - 1:
                raise
            delay = _REPAIR_LLM_BACKOFF[min(attempt, len(_REPAIR_LLM_BACKOFF) - 1)]
            print(f"[DeliveryGate] LLM 调用网络波动 ({type(e).__name__})，"
                  f"{delay}s 后重试 ({attempt + 1}/{_REPAIR_LLM_ATTEMPTS})")
            time.sleep(delay)
    raise last


def _finalize_verified_pass(context: dict, result: dict, candidate: dict,
                            base: dict, reason: str) -> bool:
    """回写候选 → 用「Node 真正会执行的 final_file_ops」复验 → 通过才准入。

    G10.19：**候选工作区通过 ≠ 交付清单通过**。shopflow_3pass_1 的 R8 里
    `_apply_back` 把修复源码挂到 `delete` op 上，候选 pytest 已全绿，
    Node 侧却拒绝 delete、磁盘仍是旧版，质量门 3 failed。
    这里按落盘侧同样的规则重建候选（忽略 delete/meta/depends）再跑一次
    pytest，把「验证过的东西」和「真正交付的东西」锁成同一个对象。
    """
    result["written"] = _apply_back(context, candidate, base)
    delivered = build_candidate(base, context.get("final_file_ops") or [])
    ok, output = _run_pytest(delivered)
    if ok:
        result.update(passed=True, reason=reason, block_delivery=False)
        return True
    result.update(passed=False, block_delivery=False,
                  reason="回写后复验失败：交付清单与已验证候选不一致",
                  delivery_mismatch=output[-_ERROR_LIMIT:],
                  final_error=output[-_ERROR_LIMIT:])
    print("[DeliveryGate] ⚠️ 回写后复验失败：交付清单与已验证候选不一致")
    return False


def gate(context: dict, intent: str) -> dict:
    """事务式交付闸门主入口。返回结构化证据，由 step_runner 决定是否落盘。"""
    meta = context.get("meta", {}) or {}
    ws = (meta.get("workspace_path") or "").rstrip("/\\")
    ops = context.get("final_file_ops") or []
    result = {
        "ran": False, "passed": False, "rounds": 0, "fixes": [],
        "history": [], "block_delivery": False, "reason": "", "written": 0,
    }
    if not ws or intent not in ("write_code", "fix_code", "refactor",
                                "incremental_feature", "bug_fix"):
        return result
    base = snapshot_workspace(ws)
    op_paths = {
        str(op.get("path") or "").replace("\\", "/").lstrip("./")
        for op in ops if op.get("content") and not op.get("_internal")
    }
    has_baseline = any(p.startswith("tests/") and p.endswith(".py") for p in base)
    py_baseline = any(p.endswith(".py") for p in base)
    candidate_has_tests = any(
        p.startswith("tests/") and p.endswith(".py") for p in op_paths)
    # G10.17：从零建项目（工作区无 .py 基线）但本次 file_ops 自带 tests/ 时，
    # 候选工作区本身就是可验证的事务式基线 —— 旧逻辑一律跳过，导致 R6
    # 只能走 2 轮同构沙箱（shopflow_full_pass1 实证：qwen-plus 生成的
    # OrderStatus.next_states() 崩溃 + 测试夹具遮蔽，2 轮修不好，3 failed）。
    # 这里放行闸门：同样的候选 pytest，但有 5 轮自适应预算 + 确定性符号解析。
    # base 为空时 FAIL-CLOSED 不误伤：分层收敛交付会保留全部新增文件。
    # 既无 .py 基线、本次也不产出测试 → 仍 FAIL-OPEN，交回旧沙箱。
    from_zero_project = not py_baseline
    if not has_baseline and not (from_zero_project and candidate_has_tests):
        return result

    result["ran"] = True
    # G10.25：闸门整体 wall-clock 预算，覆盖所有修复轮、pytest 与确定性分诊。
    # 无论上游怎么挂，闸门最多占这么久，任务总能写回结果而不留僵尸。
    deadline = time.monotonic() + _GATE_TOTAL_BUDGET_SEC
    candidate = build_candidate(base, ops)
    # G10.29：题面显式数值约束（如 POST / 必须 200 而非 201）先进候选工作区，
    # 再跑真实 pytest。这样语义契约门看到的候选与最终落盘产物一致。
    candidate, contract_fixes = _repair_explicit_status_code(
        candidate, meta.get("user_request", ""))
    # G10.30：题面写死的枚举值级联替换，同样必须在真实 pytest 之前进入
    # 候选工作区，否则「候选绿 / 落盘红」或直接 stalled 回滚。
    candidate, cascade_fixes = _repair_enum_cascade(
        candidate, meta.get("user_request", ""))
    candidate, fixes = resolve_internal_imports(candidate)
    result["fixes"] = (list(contract_fixes) + list(cascade_fixes)
                       + list(fixes))
    ok, output = _run_pytest(candidate)
    if not ok:
        candidate, ok, output = _retry_with_deterministic_fix(
            candidate, output, result["fixes"])
    if ok:
        if _finalize_verified_pass(context, result, candidate, base,
                                   "确定性符号解析后通过"):
            print(f"[DeliveryGate] 候选工作区 pytest 通过（修复 {len(fixes)} 处导入）")
        return result

    from .agents.qwen.qwen_api import call_llm
    from .file_ops import parse_fileops_v3

    prev_sig = None
    history = []
    for round_no in range(1, _MAX_REPAIR_ROUNDS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result["reason"] = f"闸门总预算 {_GATE_TOTAL_BUDGET_SEC}s 耗尽"
            print(f"[DeliveryGate] ⚠️ {result['reason']}，停止自愈")
            break
        sig = failure_signature(output)
        prog = progress(prev_sig, sig)
        result["rounds"] = round_no
        entry = {"round": round_no, "sig": sig["sig"],
                 "failed_count": sig["failed_count"], "progress": prog}
        history.append(entry)
        result["history"] = history
        print(f"[DeliveryGate] 第 {round_no} 轮: {sig['failed_count']} failed, "
              f"{sig['error_types'][:3]}, {prog}")
        if prog in ("stalled", "worsening"):
            result["reason"] = f"第 {round_no} 轮 {prog}，自适应预算止损"
            break
        try:
            reply = _call_repair_llm(
                _repair_prompt(candidate, output, meta.get("user_request", ""),
                               history, round_no),
                min(0.1 + 0.1 * (round_no - 1), 0.4), call_llm,
                timeout=min(_REPAIR_LLM_HARD_TIMEOUT, max(1, int(remaining))),
            )
            patched = {
                str(op.get("path") or "").replace("\\", "/").lstrip("./"): op.get("content")
                for op in parse_fileops_v3(reply) if op.get("content")
            }
        except Exception as e:
            result["reason"] = f"LLM 修复异常: {type(e).__name__}: {e}"
            # 网络抖动不该直接止损：跳过本轮，把预算留给后续轮次
            if _is_transient_llm_error(e) and round_no < _MAX_REPAIR_ROUNDS:
                print(f"[DeliveryGate] ⚠️ {result['reason']}；跳过本轮继续自愈")
                prev_sig = sig
                continue
            break
        changed = []
        for path, content in patched.items():
            if path not in candidate or candidate[path] == content:
                continue
            if path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError:
                    continue
            candidate[path] = content
            changed.append(path)
        if not changed:
            result["reason"] = "LLM 未产出有效改动"
            break
        entry["changed"] = changed
        # G10.30：LLM 补丁可能把已级联替换过的文件重新写回旧枚举值
        candidate, cascade = _repair_enum_cascade(
            candidate, meta.get("user_request", ""))
        result["fixes"].extend(cascade)
        candidate, more = resolve_internal_imports(candidate)
        result["fixes"].extend(more)
        ok, output = _run_pytest(candidate)
        if not ok:
            candidate, ok, output = _retry_with_deterministic_fix(
                candidate, output, result["fixes"])
        if ok:
            if _finalize_verified_pass(context, result, candidate, base,
                                       f"第 {round_no} 轮异策略修复后通过"):
                print(f"[DeliveryGate] 第 {round_no} 轮修复后候选工作区 pytest 通过")
            return result
        prev_sig = sig

    # ===== 分层收敛交付（P0 工业级：不做全有或全无）=====
    # 全量丢弃会让增量轮次连「本次新增的交付物」都不落盘（run1d 实证：
    # R8 丢掉 16 个写操作，库存三文件消失，质量门必挂）。
    # 正确做法：回写闸门内已验证的确定性/LLM 修复内容，保留新增文件，
    # 丢弃对既有文件的修改 —— 良好基线不回归，缺陷不扩散到下一轮。
    result["written"] = _apply_back(context, candidate, base)
    kept, dropped_existing = [], []
    for op in context.get("final_file_ops", []) or []:
        p = str(op.get("path") or "").replace("\\", "/").lstrip("./")
        if op.get("_internal") or p not in base:
            kept.append(op)
        else:
            dropped_existing.append(p)
    context["final_file_ops"] = kept
    result.update(
        passed=False, block_delivery=False, partial_delivery=True,
        kept_new_files=[str(o.get("path")) for o in kept if not o.get("_internal")],
        dropped_existing=dropped_existing,
        final_error=output[-_ERROR_LIMIT:],
        reason=result["reason"] or f"{result['rounds']} 轮后仍未通过",
    )
    print(f"[DeliveryGate] 分层收敛: 保留 {len(result['kept_new_files'])} 个新增文件，"
          f"回滚 {len(dropped_existing)} 个既有文件修改（{result['reason']}）")
    return result
