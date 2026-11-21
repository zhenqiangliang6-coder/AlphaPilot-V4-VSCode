# -*- coding: utf-8 -*-
# step_runner.py
# ---------------------------------------------------------
# Step Runner — 步骤执行循环 + 收尾
#
# Responsibility:
#   - 逐步执行 execution_chain 中的步骤
#   - test→fix→retest 闭环（最多 3 轮）
#   - vision_analysis 跳过（已在 Post-Vision 阶段执行）
#   - 文件操作策略执行
#   - 自清理：追踪生成文件
#   - Python 包完整性：自动补充 __init__.py（P0 确定性后处理）
#
# Extracted from qwen_worker_v2.py execute_task()
# ---------------------------------------------------------

import ast
import difflib
import json
import re
import time
from pathlib import Path

from ...worker_config import redis, check_stop_flag, stream_chunk
from ...intent_router import requires_authorization_before_step
from ...file_ops import track_generated_files, create_file_op
from ...task_state_contract import (
    STEP_STATE_PENDING,
    STEP_STATE_RUNNING,
    STEP_STATE_COMPLETED,
    STEP_STATE_FAILED,
    STEP_STATE_AWAITING_AUTHORIZATION,
    STEP_STATE_SKIPPED,
)

from .step_executor import execute_step
from .step_executor.test_step import discover_project_test_commands

MAX_FIX_RETRIES = 3

# ────────────────────────────────────────────────────────────────
# 交付完整性守卫（Deliverable Completeness Guard）
# 多文件生成时 LLM 偶发漏项（例如只写实现、漏掉题目点名的测试文件）。
# 这里在任务收尾前对照用户显式点名的路径做一次自检，缺什么补什么。
# 与具体题型无关：只认「用户点名的相对路径」这一通用契约。
# ────────────────────────────────────────────────────────────────
_REQUESTED_PATH_RE = re.compile(
    r"(?<![\w./])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\."
    r"(?:py|md|json|ya?ml|toml|txt|tsx?|jsx?|java|go|rs|sql|html|css))(?![\w/])",
    re.IGNORECASE,
)
_GUARD_INTENTS = {
    "write_code", "refactor", "execute_operation", "workspace_maintenance",
    "architecture",  # 架构师模式下用户点名的文档同样必须落盘，不能只在聊天里输出
}
# 「禁止创建扁平的 backend/models.py」这类否定句里的路径不是交付目标
_NEGATIVE_LINE_RE = re.compile(r"禁止|不要|不得|严禁|不可|避免|不应|never|don't", re.IGNORECASE)
# 分句边界：否定词的管辖范围到本句结束为止，不跨句、不整行一刀切
_CLAUSE_SPLIT_RE = re.compile(r"[;；。]")


def _extract_requested_paths(user_request: str) -> list:
    """提取用户显式点名的目标文件（排除否定语境 / API 路径 / import 名 / 绝对路径）。

    否定语境按「路径之前」判定，而不是整行一刀切：
    - 「禁止创建 `backend/models.py`」→ 路径前出现否定词，跳过。
    - 「修改 backend/routers/orders.py —— 路由不得包含 db 查询」→ 否定词在路径之后，
      路径本身仍是交付目标，必须保留（整行过滤会误杀这一整行）。
    """
    seen, out = set(), []
    for line in (user_request or "").splitlines():
        clause_starts = [0] + [m.end() for m in _CLAUSE_SPLIT_RE.finditer(line)]
        neg_positions = [m.start() for m in _NEGATIVE_LINE_RE.finditer(line)]
        for m in _REQUESTED_PATH_RE.finditer(line):
            p = m.group(1).strip().lstrip("./")
            if not p or p in seen or p.startswith("/"):
                continue
            # 否定词只在「同一分句、且位于路径之前」时管辖该路径
            clause_start = max((c for c in clause_starts if c <= m.start()), default=0)
            if any(clause_start <= pos < m.start() for pos in neg_positions):
                continue
            seen.add(p)
            out.append(p)
    return out


# ────────────────────────────────────────────────────────────────
# v3.7 最小修改约束
# 修复类任务若题面明确要求「只改出错文件 / 最小行数变更」，模型仍可能
# 全量重生成整套项目（run12 改 27 个文件、run13 改 19 个，还新建无关的
# backend/core/database.py），把原本一行 import 的修复变成半重写，
# 引入 201 vs 200、405 vs 204 等新失败。
# 这里把题面契约编译成确定性过滤：只认 traceback 里 `File "xxx.py"`
# 指向的源文件，其余 FileOps 一律不落盘。
# ────────────────────────────────────────────────────────────────
_MINIMAL_FIX_INTENTS = {
    "fix_code", "bug_fix", "debug", "explain_and_fix", "test_failure_repair",
}
_MINIMAL_FIX_MARKERS = (
    "最小修改", "最小行数变更", "只允许修改", "只改", "不要改动测试断言",
    "minimal change", "minimal modification", "only modify",
)
_TRACEBACK_FILE_RE = re.compile(r'File\s+"([^"]+\.py)"', re.IGNORECASE)
# 常见源码根，用于把 Windows 绝对路径切成工作区相对路径
_SOURCE_ROOTS = ("backend/", "src/", "app/", "lib/", "server/", "api/", "tests/")


def _relative_source_path(raw: str, workspace_path: str = "") -> str:
    """把 traceback 里的绝对/混合路径归一成工作区相对路径。"""
    p = (raw or "").replace("\\", "/").strip()
    if workspace_path:
        ws = workspace_path.replace("\\", "/").rstrip("/")
        if p.lower().startswith(ws.lower() + "/"):
            p = p[len(ws) + 1:]
    p = p.lstrip("/")
    for i, seg in enumerate(p.split("/")):
        prefix = seg + "/"
        if prefix in _SOURCE_ROOTS:
            return "/".join(p.split("/")[i:])
    # 兜底：最多保留末尾 3 段，避免把 C:/Users/... 整串当成路径
    parts = p.split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else p


def _extract_traceback_targets(user_request: str, workspace_path: str = "") -> list:
    """提取 traceback 指向的源文件（排除 tests/ 下的测试文件）。"""
    seen, out = set(), []
    for m in _TRACEBACK_FILE_RE.finditer(user_request or ""):
        rel = _relative_source_path(m.group(1), workspace_path)
        if not rel or rel.startswith("tests/") or "/tests/" in rel:
            continue  # 修复题面通常明令禁止重写测试文件
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _enforce_minimal_fix_scope(context: dict, intent: str) -> dict:
    """题面要求「最小修改」时，只保留 traceback 点名的源文件 FileOps。

    FAIL-OPEN 设计（防止误伤其它轮次）：
      * 意图不是修复类 → 不生效；
      * 题面没有明确的最小修改措辞 → 不生效；
      * traceback 没提取到任何源文件 → 不生效；
      * 过滤后一个有效操作都不剩 → 回滚到原始列表。
    被过滤的路径记入 meta 作为证据，便于复盘。
    """
    meta = context.get("meta", {}) or {}
    req = meta.get("user_request") or ""
    result = {"applied": False, "kept": [], "dropped": []}
    if intent not in _MINIMAL_FIX_INTENTS:
        return result
    if not any(marker in req for marker in _MINIMAL_FIX_MARKERS):
        return result
    targets = _extract_traceback_targets(req, meta.get("workspace_path", ""))
    if not targets:
        return result

    target_set = set(targets)
    ops = context.get("final_file_ops", []) or []
    kept, dropped = [], []
    for op in ops:
        path = str(op.get("path") or "").replace("\\", "/").lstrip("./")
        # 内部元数据、包完整性补充的 __init__.py、生成清单都不算「模型改的业务文件」
        is_support = (op.get("_internal") or path.endswith("/__init__.py")
                      or path == "__init__.py"
                      or path.startswith(".alphapilot"))
        if is_support or path in target_set:
            kept.append(op)
        else:
            dropped.append(path or "<无路径>")

    if not kept:
        return result  # 绝不把交付清空

    context["final_file_ops"] = kept
    result.update(applied=True, kept=[str(o.get("path")) for o in kept],
                  dropped=dropped)
    return result


# ── v3.8: 最小修改的内容级守卫 ──────────────────────────────────
# run17 实证：scope 守卫管住了「改哪些文件」，但保留文件的**内容**仍可能被
# 全量重写 —— R7 修复把 orders.py 重写，恢复了 `from typing import List`
# 的同时凭空引入 `from backend.models.order import Order, OrderItem`，
# 而 order.py 根本没有 OrderItem，幻觉导入让 pytest 崩掉。
# 确定性规则：最小修复语境下，磁盘现状 + 重写内容 diff 很小 → 直接放行；
# diff 很大（违约重写）→ 只信任「纯新增 import 行」（缺失导入恰好是
# ImportError / NameError 类 Bug 的最小修复形态），合并回磁盘现状，
# 替换/删除行一律丢弃 —— 幻觉导入、越界改动全部隔离。
_MINIMAL_FIX_MAX_DIFF_LINES = 6
_IMPORT_LINE_RE = re.compile(r"^\s*(?:from\s+[\w\.]+\s+import\s+|import\s+[\w\.]+)")


def _is_import_line(line: str) -> bool:
    return bool(_IMPORT_LINE_RE.match(line or ""))


def _count_diff_lines(old_lines: list, new_lines: list) -> int:
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            changed += (i2 - i1) + (j2 - j1)
    return changed


def _extract_pure_import_additions(old_lines: list, new_lines: list) -> list:
    """提取重写内容中旧文件没有的 import 行（行级集合语义，不受 diff 分块影响）。"""
    old_set = set(old_lines)
    seen, adds = set(), []
    for line in new_lines:
        if not line.strip() or not _is_import_line(line) or line in old_set:
            continue
        if line not in seen:
            seen.add(line)
            adds.append(line)
    return adds


_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([\w\.]+)\s+import\s+(.+)$")
_PLAIN_IMPORT_RE = re.compile(r"^\s*import\s+([\w\.]+)")


def _workspace_module_file(ws_root: str, module: str):
    """项目内部模块 → 工作区源文件路径；外部模块返回 None。"""
    if not module:
        return None
    rel = module.replace(".", "/")
    for cand in (f"{rel}.py", f"{rel}/__init__.py"):
        f = Path(ws_root) / cand
        if f.is_file():
            return f
    return None


def _module_top_level_names(path: Path) -> set:
    """ast 收集模块顶层可见名（类/函数/赋值/re-export/__all__）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return set()
    names: set = set()
    exported = None
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
                    if t.id == "__all__":
                        try:
                            exported = {e.value for e in node.value.elts
                                         if isinstance(e, ast.Constant)}
                        except Exception:
                            pass
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    names.add((a.asname or a.name).split(".")[0])
            else:
                for a in node.names:
                    names.add(a.asname or a.name)
    if exported:
        names |= exported
    return names


def _looks_internal(ws_root: str, module: str) -> bool:
    """模块是否是项目内部模块：首段在工作区里能对上目录/文件。

    `typing` / `os` 这类顶层外部模块首段对不上任何工作区条目 → 外部。
    """
    first = module.split(".")[0]
    probe = Path(ws_root) / first
    return probe.is_dir() or probe.is_file()


def _validate_import_additions(ws_root: str, lines: list) -> tuple[list, list]:
    """验证候选 import 行，幻觉导入（工作区模块里不存在的名字）一律丢弃。

    * 引用项目内部模块（工作区能定位到文件）→ ast 验证每个导入名；
      任一名字不存在 → 丢弃整行 —— run17 的 `Order, OrderItem` 幻觉即此类。
    * 引用不存在的内部模块（文件都定位不到）→ 丢弃整行（必然 ImportError）。
    * 外部/标准库模块 → 无法在工作区验证，保守放行（第三方依赖不在
      Worker venv 里很正常，过度拦截会误伤合法修复）。
    """
    kept, dropped = [], []
    for line in lines:
        m = _FROM_IMPORT_RE.match(line)
        if m:
            module = m.group(1)
            src = _workspace_module_file(ws_root, module)
            if src is None:
                if _looks_internal(ws_root, module):
                    dropped.append(line)
                else:
                    kept.append(line)
                continue
            top = _module_top_level_names(src)
            wanted = [n.strip().split(" as ")[0].strip()
                      for n in m.group(2).split(",") if n.strip()]
            if wanted and all(any(w == t or w.startswith(t + ".")
                                  for t in top) or w in top for w in wanted):
                kept.append(line)
            else:
                dropped.append(line)
            continue
        m2 = _PLAIN_IMPORT_RE.match(line)
        if m2:
            module = m2.group(1)
            if _workspace_module_file(ws_root, module) is not None:
                kept.append(line)
            elif _looks_internal(ws_root, module):
                dropped.append(line)
            else:
                kept.append(line)
        else:
            kept.append(line)
    return kept, dropped


def _top_import_insert_index(lines: list) -> int:
    """返回顶部 import 区的插入位置（跳过 shebang/编码声明/注释/模块 docstring）。"""
    idx = 0
    n = len(lines)
    while idx < n and (lines[idx].lstrip().startswith("#") or not lines[idx].strip()):
        idx += 1
    if idx < n and lines[idx].lstrip().startswith(('"""', "'''")):
        stripped = lines[idx].lstrip()
        quote = stripped[:3]
        if quote in stripped[3:]:
            idx += 1  # 单行 docstring（开闭引号同行）
        else:
            idx += 1
            while idx < n and quote not in lines[idx]:
                idx += 1
            idx += 1
    return idx


# 完整合法的 import 语句（带别名/行尾注释）；不匹配的 import 前缀行 = 语法坏行
_COMPLETE_IMPORT_RE = re.compile(
    r"^\s*from\s+[\w\.]+\s+import\s+"
    r"[\w\.]+(\s+as\s+\w+)?(\s*,\s*[\w\.]+(\s+as\s+\w+)?)*(\s*#.*)?$"
    r"|^\s*import\s+"
    r"[\w\.]+(\s+as\s+\w+)?(\s*,\s*[\w\.]+(\s+as\s+\w+)?)*(\s*#.*)?$"
)


def _broken_import_lines(lines: list) -> list:
    """提取语法坏行：import 前缀但不构成完整 import 语句（必然 SyntaxError）。

    run18 实证：注入的 Bug 把导入改成 `from typing import   # ← BUG: List removed`，
    这种行单独存在就是 SyntaxError，最小修复的另一半就是删掉它。
    合法完整导入（含别名/行尾注释）永远不在此列，不会被误删。
    """
    out = []
    for line in lines:
        s = line.strip()
        if not s or not _is_import_line(line):
            continue
        if not _COMPLETE_IMPORT_RE.match(line):
            out.append(line)
    return out


def _enforce_minimal_fix_content(context: dict, scope: dict) -> dict:
    """最小修改语境下的内容级守卫：挡住「保留文件」的违约全量重写。

    FAIL-OPEN：
      * 磁盘上没有旧内容（新文件）→ 跳过；
      * diff 在阈值内（真·最小修复）→ 原样放行；
      * diff 超阈值但提取不到任何纯新增 import → 放行 LLM 内容
        （比交付空强，证据记入 meta）。
    """
    result = {"checked": 0, "blocked_rewrites": [], "import_additions": [],
              "passed_through": []}
    meta = context.get("meta", {}) or {}
    ws = (meta.get("workspace_path") or "").rstrip("/\\")
    req = meta.get("user_request") or ""
    if not ws or not scope.get("applied"):
        return result
    target_set = {str(p).replace("\\", "/").lstrip("./") for p in scope.get("kept", [])}

    for op in context.get("final_file_ops", []) or []:
        path = str(op.get("path") or "").replace("\\", "/").lstrip("./")
        content = op.get("content") or ""
        if path not in target_set or not content or op.get("_internal"):
            continue
        disk = Path(ws) / path
        try:
            if not disk.is_file():
                continue
            old = disk.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        result["checked"] += 1
        old_lines = old.splitlines()
        new_lines = content.splitlines()
        if _count_diff_lines(old_lines, new_lines) <= _MINIMAL_FIX_MAX_DIFF_LINES:
            result["passed_through"].append(path)
            continue  # 真·最小修复，放行
        candidates = _extract_pure_import_additions(old_lines, new_lines)
        if not candidates:
            result["passed_through"].append(path)
            continue  # 提取不到任何 import 证据，FAIL-OPEN 放行 LLM 内容
        validated, hallucinated = _validate_import_additions(ws, candidates)
        if hallucinated:
            result.setdefault("hallucinated_imports", []).extend(
                f"{path}: {l.strip()}" for l in hallucinated)
        existing = {l.strip() for l in old_lines}
        fresh = [l for l in validated if l.strip() not in existing]
        broken = _broken_import_lines(old_lines)
        if not fresh and not broken:
            # 候选全是幻觉且无坏行 → 重写没有任何可信增益，整体回滚到磁盘现状
            op["content"] = old
            result["blocked_rewrites"].append(path)
            continue
        # 磁盘现状 - 语法坏行 + 验证过的新增 import = 确定性最小修复
        base_lines = [l for l in old_lines if l not in set(broken)]
        if broken:
            result.setdefault("import_deletions", []).extend(
                f"{path}: {l.strip()}" for l in broken)
        insert_at = _top_import_insert_index(base_lines)
        merged = base_lines[:insert_at] + fresh + base_lines[insert_at:]
        merged_text = "\n".join(merged) + ("\n" if old.endswith("\n") else "")
        try:
            ast.parse(merged_text)  # 语法自检：坏行漏删/合并出错立即暴露
        except SyntaxError as _se:
            result.setdefault("syntax_check_failed", []).append(f"{path}: {_se}")
        op["content"] = merged_text
        result["blocked_rewrites"].append(path)
        result["import_additions"].extend(f"{path}: {l.strip()}" for l in fresh)
    return result


# ── v3.9: 增量功能的既有文件契约保护（G10.14）─────────────────────
# shopflow_full_run1b 实证：R8 题面明写「不要破坏现有功能」，模型却把
# backend/schemas/order.py、backend/routers/orders.py、backend/models/order.py
# 等既有文件全量重写，删掉 OrderResponse.id、改掉 HTTP 方法，pytest 15 failed
# （422 / 405 / KeyError: 'id'）。Worker 的 ShadowVerify 两轮自检都发现失败，
# 却仍让缺陷交付落盘，导致 R9/R10 前置连锁崩。
# 确定性规则：这类题面下，既有文件的写操作必须保持「公开契约」不缩水
# （类/字段/函数签名/路由装饰器只许增不许删），且新内容语法合法；
# 违约则保留磁盘现状。新增文件不受影响（增量功能本来就该只加不改）。
_INCREMENTAL_GUARD_MARKERS = (
    "不要破坏现有功能", "不要改动现有", "原样通过", "保持现有 API",
    "不要修改 tests/", "不要改动 tests/", "不要改动测试",
)
_INCREMENTAL_INTENTS = {"write_code", "incremental_feature", "feature_addition"}

# ── v3.9.1: 题面正向点名要修改的既有文件（G10.16）─────────────────
# shopflow_full_run1e 实证：R8 题面明写「backend/main.py 必须用
# include_router(inventory_router, prefix="/inventory") 注册库存路由」，
# 但增量契约保护把 main.py 当普通既有文件回滚，导致 /inventory 全 404
# （9 failed）。规则：逐行确定性解析，只有「同一行内既有 .py 路径、又有
# 正向修改动词、且不含任何否定/受保护措辞」才进白名单；R9「不要改动
# backend/main.py」、R10「backend/main.py 属于受保护文件…其余内容禁止修改」
# 严格排除。白名单只豁免「契约缩水检查」，语法检查照做，最终仍由
# delivery_gate 的事务式 pytest 决定交付。
_EXPLICIT_PATH_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.py\b")
_EXPLICIT_EDIT_VERBS = (
    "修改", "追加", "注册", "添加", "新增", "更新", "改写",
    "接入", "补齐", "扩展", "挂载",
)
_EXPLICIT_NEGATIONS = (
    "不要", "不得", "禁止", "不许", "不可", "不能", "无需", "不用",
    "受保护", "原样", "保持不变", "勿", "不得改",
)

# G10.32：题面还会用「端点」正向点名要改的既有文件，而不写 .py 路径。
# v11 第 1 遍 R8 实证：题面第 4 条「修改 POST /orders 逻辑」要求改
# backend/routers/orders.py 实现库存扣减，但白名单只认 .py 路径，
# 增量契约保护把 orders.py 的写操作整个丢弃（保留磁盘现状），于是
# LLM 自己生成的 test_inventory.py 里「下单扣减库存」断言必然失败，
# 候选工作区 6 failed(AttributeError) → 全量回滚 → R8 零落盘。
# 收紧条件：同一行必须有「正向修改动词 + HTTP 方法 + 端点路径」，
# 且不含强否定词；只映射到 backend/routers/<首段>.py，不碰 tests/、
# schemas/ 或 main.py。「原样」不参与屏蔽 —— 它通常修饰同一行里另一个
# 受保护文件（如 tests/test_orders.py），不该连带否决端点放行。
_ENDPOINT_EDIT_RE = re.compile(
    r"(?:修改|调整|扩展|更新|改写|补齐|接入)\s*"
    r"(?:POST|GET|PUT|PATCH|DELETE)\s+"
    r"(/[A-Za-z0-9_{}./-]+)")
_ENDPOINT_STRONG_NEG = ("不要", "不得", "禁止", "不许", "不可", "勿")


def _explicitly_named_edit_targets(req: str) -> set:
    """提取题面正向点名要修改的既有文件；否定语境一律不认。

    FAIL-CLOSED 语义：宁可少放行（继续做契约保护），也不误放行受保护文件。
    """
    out: set = set()
    for line in (req or "").splitlines():
        if any(neg in line for neg in _EXPLICIT_NEGATIONS):
            continue
        if not any(verb in line for verb in _EXPLICIT_EDIT_VERBS):
            continue
        for m in _EXPLICIT_PATH_RE.finditer(line):
            out.add(m.group(0).replace("\\", "/").lstrip("./"))
    for line in (req or "").splitlines():
        if any(neg in line for neg in _ENDPOINT_STRONG_NEG):
            continue
        for m in _ENDPOINT_EDIT_RE.finditer(line):
            seg = m.group(1).strip("/").split("/")[0]
            if seg and re.fullmatch(r"[A-Za-z0-9_]+", seg):
                out.add(f"backend/routers/{seg}.py")
    return out


def _public_contract(src: str) -> set:
    """抽取模块公开契约：类、类字段、函数签名、路由装饰器。"""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out.add(("class", node.name))
            for sub in node.body:
                targets = []
                if isinstance(sub, ast.AnnAssign):
                    targets = [sub.target]
                elif isinstance(sub, ast.Assign):
                    targets = list(sub.targets)
                for t in targets:
                    if isinstance(t, ast.Name):
                        out.add(("field", node.name, t.id))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(("func", node.name, tuple(a.arg for a in node.args.args)))
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    path = (dec.args[0].value if dec.args
                            and isinstance(dec.args[0], ast.Constant) else "")
                    out.add(("route", dec.func.attr, str(path)))
    return out


def _enforce_incremental_contract(context: dict, intent: str) -> dict:
    """「不要破坏现有功能」题面下，挡住既有文件的契约破坏型重写。

    FAIL-OPEN：非增量意图 / 无保护措辞 / 无工作区路径 / 目标文件不存在 /
    新旧内容相同 / 解析异常 → 一律放行，不影响 R6/R9/R10。

    例外（G10.16）：题面正向点名要修改的既有文件（如 R8 的 backend/main.py）
    只做语法自检，跳过公开契约缩水检查；否定语境点名的受保护文件不豁免。
    """
    result = {"applied": False, "blocked": [], "reasons": {}, "checked": 0,
              "explicit_targets": [], "whitelisted": []}
    meta = context.get("meta", {}) or {}
    req = meta.get("user_request") or ""
    ws = (meta.get("workspace_path") or "").rstrip("/\\")
    if intent not in _INCREMENTAL_INTENTS or not ws:
        return result
    if not any(m in req for m in _INCREMENTAL_GUARD_MARKERS):
        return result

    explicit = _explicitly_named_edit_targets(req)
    result["explicit_targets"] = sorted(explicit)
    ops = context.get("final_file_ops", []) or []
    kept = []
    for op in ops:
        path = str(op.get("path") or "").replace("\\", "/").lstrip("./")
        content = op.get("content")
        if (not path.endswith(".py") or not content or op.get("_internal")
                or path.endswith("/__init__.py") or path == "__init__.py"):
            kept.append(op)
            continue
        disk = Path(ws) / path
        try:
            if not disk.is_file():
                kept.append(op)  # 新增文件：不设限
                continue
            old = disk.read_text(encoding="utf-8", errors="replace")
        except Exception:
            kept.append(op)
            continue
        if content == old:
            kept.append(op)
            continue
        result["checked"] += 1
        is_explicit = path in explicit
        if is_explicit:
            result["whitelisted"].append(path)
        try:
            ast.parse(content)
        except SyntaxError as se:
            result["blocked"].append(path)
            result["reasons"][path] = f"新内容语法错误: {se.msg}"
            continue  # 丢弃该写操作 = 保留磁盘现状
        if not is_explicit:
            missing = _public_contract(old) - _public_contract(content)
            if missing:
                result["blocked"].append(path)
                result["reasons"][path] = f"公开契约缩水: {sorted(missing)[:5]}"
                continue
        kept.append(op)  # 加法式增量 / 题面点名文件（语法合法），放行

    if result["blocked"]:
        # kept 为空也生效：不落盘 == 保留磁盘现状，正是保护目标
        context["final_file_ops"] = kept
        result["applied"] = True
    return result


def _reconcile_misplaced_paths(ops: list, expected: list) -> tuple[list, list]:
    """把「丢了目录前缀」的重复文件归位或丢弃（确定性，零 LLM 依赖）。

    多轮分批生成时，模型偶尔会同时产出 `backend/models/order.py` 和
    `models/order.py`。用户点名的路径是权威：已有正确版本就丢掉错位项，
    否则把错位项重定向到正确路径，避免污染工作区根目录。
    """
    def _norm(p):
        return (p or "").replace("\\", "/").lstrip("./")

    expected_set = set(expected)
    produced = {_norm(op.get("path")) for op in ops}
    suffix_map: dict[str, list[str]] = {}
    for e in expected_set:
        parts = e.split("/")
        for n in range(1, len(parts)):
            suffix_map.setdefault("/".join(parts[n:]), []).append(e)

    dropped, renamed = [], []
    for op in ops:
        p = _norm(op.get("path"))
        if not p or p in expected_set:
            continue
        candidates = [e for e in suffix_map.get(p, []) if e != p]
        if not candidates:
            continue
        target = candidates[0]
        if target in produced:
            op["_drop"] = True          # 已有正确版本，丢弃重复错位项
            dropped.append(p)
        else:
            op["path"] = target        # 只有错位版本，救回内容并归位
            produced.add(target)
            renamed.append((p, target))
    return dropped, renamed


def _ensure_requested_deliverables(context: dict, intent: str) -> dict:
    """补齐用户点名但本轮未交付的文件，返回可审计的报告。"""
    meta = context.get("meta", {}) or {}
    ws_root = meta.get("workspace_path") or ""
    user_request = meta.get("user_request") or ""

    if intent not in _GUARD_INTENTS or not ws_root or not user_request:
        return {"skipped": True}

    from ...file_ops import parse_fileops_v3, normalize_fileop_paths
    from .qwen_api import call_llm

    def _norm(p):
        return (p or "").replace("\\", "/").lstrip("./")

    ops = context.get("final_file_ops") or []
    expected = _extract_requested_paths(user_request)
    if intent == "architecture":
        # 架构师模式是只读角色：守卫只允许补齐文档，绝不借补齐之名生成代码。
        # 角色策略已经把 .py FileOps 过滤掉，这里把名单收紧到同一边界。
        expected = [p for p in expected
                    if p.lower().endswith((".md", ".mmd", ".puml"))]
    dropped, renamed = _reconcile_misplaced_paths(ops, expected)
    reconciled = {"dropped": dropped, "renamed": renamed}
    if dropped:
        context["final_file_ops"] = [op for op in ops if not op.pop("_drop", False)]
        ops = context["final_file_ops"]

    # G10.37：cleanup_previous_generated 会在 final_file_ops 开头插入
    # delete op。此刻磁盘上还留着上一遍的同名文件，只看 exists() 会
    # 误判「题面点名的文件已交付」；Node 随后删掉它却不会重建，
    # 工作区变成零测试文件（pytest exit 5），质量门必挂（v16 实证）。
    # 凡是被本轮 delete 命中的路径，一律视为磁盘上不存在，强制补齐。
    deleted = {
        _norm(op.get("path")) for op in ops
        if str(op.get("op") or "").lower() == "delete"
    }
    produced = {
        _norm(op.get("path")) for op in ops
        if str(op.get("op") or "").lower() != "delete"
    }
    missing = [
        p for p in expected
        if p not in produced and (p in deleted or not (Path(ws_root) / p).exists())
    ]
    if not missing:
        return {"checked": len(expected), "missing": [], "recovered": [],
                "reconciled": reconciled}

    # 带上本轮已生成的源码作为上下文，保证补出的文件与实现兼容
    src_blocks = []
    for op in ops:
        p, content = _norm(op.get("path")), op.get("content") or ""
        if p.endswith(".py") and content and not op.get("_internal"):
            src_blocks.append(f"# FILE: {p}\n{content[:6000]}")
    existing_src = "\n\n".join(src_blocks) or "(无)"

    prompt = (
        "你是代码交付补全器。用户要求生成一组文件，但下面列出的文件漏了。\n\n"
        f"【用户原始需求】\n{user_request}\n\n"
        f"【本轮已经生成的文件源码】\n{existing_src}\n\n"
        "【必须补齐的缺失文件】\n" + "\n".join(f"- {p}" for p in missing) + "\n\n"
        "硬性要求：\n"
        "1. 只生成上面列出的缺失文件，严禁重复生成已生成文件。\n"
        "2. 每个文件用一行 `# FILE: 相对路径` 开头，紧接着写完整文件内容；"
        "多个文件依次排列，不要输出 Markdown 代码围栏。\n"
        "3. 内容必须与已生成的实现严格兼容、可直接运行；"
        "若是测试文件，必须覆盖用户原始需求里列出的场景。\n"
        "4. 不要输出任何解释、总结或额外文字。\n"
    )

    report = {"checked": len(expected), "missing": missing,
              "recovered": [], "reconciled": reconciled}
    try:
        raw = call_llm(prompt, temperature=0.2)
        extras = normalize_fileop_paths(parse_fileops_v3(raw) or [], ws_root)
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        context["meta"]["deliverable_guard"] = report
        return report

    wanted, seen = set(missing), set()
    for op in extras:
        p, content = _norm(op.get("path")), op.get("content") or ""
        if p not in wanted or p in seen:
            continue
        # __init__.py 合法地为空，其余空内容视为模型没真正产出
        if not content.strip() and not p.endswith("__init__.py"):
            continue
        if p.endswith(".py"):
            try:
                compile(content, p, "exec")
            except SyntaxError:
                continue
        seen.add(p)
        op["from_step"] = "deliverable_guard"
        context["final_file_ops"].append(op)
        report["recovered"].append(p)

    context["meta"]["deliverable_guard"] = report
    return report


def run_execution_loop(
    steps: list,
    execution_plan: dict,
    task_id: str,
    events: list,
    context: dict,
    intent: str,
    mode: str,
):
    """逐步执行 steps 中的步骤，含 test→fix→retest 闭环。

    Returns:
        test_fixed_in_loop: True 如果修复循环已通过测试
    """
    test_fixed_in_loop = False

    for step_index, step in enumerate(steps):
        try:
            if requires_authorization_before_step(execution_plan, step.get("type", "")):
                # P1: 确定性测试命令发现 — 在授权前自动注入，不依赖 LLM plan 输出
                _inject_discovered_test_command(context)
                _defer_test_for_authorization(step, context)
                _skip_remaining_steps(
                    steps,
                    step_index + 1,
                    "等待用户授权并完成项目测试后再继续。",
                )
                break

            if check_stop_flag(task_id):
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": "任务已被用户取消"}
                raise Exception("任务已被用户取消")

            # v3.3: 如果 test 已在修复循环中通过，跳过后续 fix
            if test_fixed_in_loop and step.get("type") == "fix":
                step["status"] = STEP_STATE_SKIPPED
                step["reason"] = "测试已在修复循环中通过，跳过重复 fix 步骤"
                step["output"] = {"text": "测试已在修复循环中通过，跳过后继 fix。"}
                test_fixed_in_loop = False
                continue

            # v4.4: vision_analysis 已在 Post-Vision 阶段执行，跳过
            if context.get("_vision_result") and step.get("type") == "vision_analysis":
                step["status"] = STEP_STATE_SKIPPED
                step["reason"] = "视觉分析已在 Post-Vision 阶段预先执行"
                step["output"] = context.get("_vision_result_last_output") or {
                    "text": "视觉分析已在上一阶段完成"
                }
                continue

            step["status"] = STEP_STATE_RUNNING

            # v4.3: 将视觉分析结果注入下游步骤 prompt
            if context.get("_vision_result") and step.get("type") != "vision_analysis":
                step.setdefault("input", {})["prompt"] = (
                    f"[图片分析结果]\n{context['_vision_result']}\n\n"
                    f"---\n\n[用户原始请求]\n{step.get('input', {}).get('prompt', '')}\n\n"
                    f"以上分析结果作为参考，请基于用户请求直接回答。"
                )

            # v3.5: 智能验证治理 — Shadow Mode 影响分析
            # 在 test 步骤执行前分析 final_file_ops 变更，
            # 输出 impact_profile 到 context.meta 供审计。
            # 不改变任何现有测试执行行为。
            if step.get("type") == "test":
                try:
                    from .step_executor.verification_governor import VerificationGovernor
                    _vg = VerificationGovernor(context)
                    context["meta"]["verification_governance"] = _vg.analyze_impact()
                except Exception as _vg_err:
                    context["meta"]["verification_governance"] = {
                        "mode": "shadow",
                        "error": str(_vg_err),
                        "analysis_failed": True,
                    }

            execute_step(task_id, step, events, context)
            step["status"] = STEP_STATE_COMPLETED

            # v3.3: test→fix→retest 闭环
            if step.get("type") == "test":
                test_output = step.get("output", {})
                if test_output.get("exec_success") is True:
                    continue

                if test_output.get("exec_success") is False and _has_executable_test_failure(test_output):
                    _fixed = _run_fix_retest_loop(
                        task_id, events, context, step,
                    )
                    if _fixed:
                        test_fixed_in_loop = True
                    else:
                        _mark_validation_failed(
                            context,
                            step,
                            "测试未通过，修复重测未能验证成功；已停止后续步骤。",
                        )
                        _skip_remaining_steps(
                            steps,
                            step_index + 1,
                            "前置测试未通过。",
                        )
                        break
                else:
                    _mark_validation_failed(
                        context,
                        step,
                        "没有获得明确的测试执行成功证据；不会将此步骤报告为通过。",
                    )
                    _skip_remaining_steps(
                        steps,
                        step_index + 1,
                        "测试结果缺失或测试命令未能执行。",
                    )
                    break

        except Exception as step_error:
            msg = str(step_error)
            if "取消" in msg or "cancel" in msg.lower():
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": "任务已被用户取消"}
            else:
                step["status"] = STEP_STATE_FAILED
                step["output"] = {"text": f"步骤执行失败：{step_error}"}
            raise step_error

    return test_fixed_in_loop


def _inject_discovered_test_command(context: dict) -> None:
    """P1: 若 plan LLM 未发现测试命令，通过确定性文件扫描自动补充。"""
    meta = context.setdefault("meta", {})
    
    if meta.get("proposed_test_command"):
        return

    ws = meta.get("workspace_path") or meta.get("workspace_dir") or ""
    if not ws:
        return

    discovered = discover_project_test_commands(ws)
    if discovered:
        meta["proposed_test_command"] = discovered[0]["command"]
        meta["test_discovery"] = {
            "found": True,
            "command": discovered[0]["command"],
            "language": discovered[0]["language"],
            "source": discovered[0]["source"],
            "all_commands": [d["command"] for d in discovered],
        }
        print(f"[STEP_RUNNER] 确定性发现测试命令: {discovered[0]['command']} ({discovered[0]['source']})")


def _defer_test_for_authorization(step: dict, context: dict) -> None:
    meta = context.setdefault("meta", {})
    command = meta.get("proposed_test_command")
    step["status"] = STEP_STATE_AWAITING_AUTHORIZATION
    step["output"] = {
        "text": "项目测试需用户明确授权；当前未运行测试。",
        "proposed_command": command,
        "exec_success": None,
    }
    meta["execution_state"] = "awaiting_authorization"
    deferred_steps = meta.setdefault("deferred_steps", [])
    if "test" not in deferred_steps:
        deferred_steps.append("test")

    requests = meta.setdefault("authorization_requests", [])
    if not any(request.get("type") == "test" for request in requests):
        requests.append({
            "type": "test",
            "command": command,
            "status": "awaiting_host_policy",
        })


def _skip_remaining_steps(steps: list, start_index: int, reason: str) -> None:
    for pending_step in steps[start_index:]:
        if pending_step.get("status") == STEP_STATE_PENDING:
            pending_step["status"] = STEP_STATE_SKIPPED
            pending_step["reason"] = reason
            pending_step["output"] = {"text": reason}


def _has_executable_test_failure(test_output: dict) -> bool:
    result = test_output.get("test_result")
    if not isinstance(result, dict):
        return False
    exit_code = result.get("exit_code")
    return (
        isinstance(exit_code, int)
        and exit_code != 0
        and not result.get("timed_out", False)
    )


def _mark_validation_failed(context: dict, step: dict, message: str) -> None:
    step["status"] = STEP_STATE_FAILED
    output = step.setdefault("output", {})
    output["text"] = f"{output.get('text', '').rstrip()}\n{message}".strip()
    context.setdefault("meta", {})["execution_state"] = "validation_failed"


def _run_fix_retest_loop(task_id: str, events: list, context: dict, test_step: dict) -> bool:
    """test→fix→retest 闭环，最多 3 轮。"""
    for retry in range(1, MAX_FIX_RETRIES + 1):
        if task_id:
            stream_chunk(
                task_id,
                f"\n🔄 测试失败，第 {retry}/{MAX_FIX_RETRIES} 次尝试修复并重测...\n",
            )

        if check_stop_flag(task_id):
            test_step["status"] = STEP_STATE_FAILED
            test_step["output"] = {"text": "任务已被用户取消（测试修复循环中）"}
            raise Exception("任务已被用户取消")

        fix_step = {"type": "fix", "status": STEP_STATE_PENDING, "output": {}}
        try:
            execute_step(task_id, fix_step, events, context)
        except Exception as fe:
            if task_id:
                stream_chunk(task_id, f"修复步骤异常: {fe}")
            _mark_validation_failed(
                context,
                test_step,
                f"修复步骤执行失败：{fe}",
            )
            break

        retest_step = {"type": "test", "status": STEP_STATE_PENDING, "output": {}}
        try:
            execute_step(task_id, retest_step, events, context)
        except Exception as re:
            if task_id:
                stream_chunk(task_id, f"重测步骤异常: {re}")
            _mark_validation_failed(
                context,
                test_step,
                f"重测步骤执行失败：{re}",
            )
            break

        if retest_step.get("output", {}).get("exec_success") is True:
            test_step["output"] = retest_step["output"]
            test_step["status"] = STEP_STATE_COMPLETED
            if task_id:
                stream_chunk(task_id, f"✅ 第 {retry} 次修复后测试通过！\n")
            return True
        elif retry >= MAX_FIX_RETRIES:
            test_step["output"] = retest_step["output"]
            _mark_validation_failed(
                context,
                test_step,
                f"{MAX_FIX_RETRIES} 次修复后测试仍未通过。",
            )
            if task_id:
                stream_chunk(task_id, f"❌ {MAX_FIX_RETRIES} 次修复后测试仍未通过。\n")

    if test_step.get("status") != STEP_STATE_FAILED:
        _mark_validation_failed(
            context,
            test_step,
            "测试修复循环未能产生通过证据。",
        )
    return False


def _store_authorization_in_redis(context: dict, task_id: str):
    """R6 安全契约：存储授权数据到 Redis 供 Node.js 执行端独立验证。

    Worker = 真相：只有 Worker 创建授权条目。
    Node.js 只读验证，不修改 task_state。
    """
    if not task_id:
        return
    authorization_requests = context.get("meta", {}).get("authorization_requests")
    if not authorization_requests:
        return
    auth_key = f"auth:{task_id}"
    auth_data = {
        "task_id": task_id,
        "workspace_path": context.get("meta", {}).get("workspace_path", ""),
        "authorizations": authorization_requests,
        "created_at": time.time(),
        "expires_at": time.time() + 3600,
    }
    try:
        redis.set(auth_key, json.dumps(auth_data, ensure_ascii=False), ex=3600)
    except Exception:
        pass


def _ensure_python_package_inits(file_ops: list) -> int:
    """确定性后处理：为 Python 包目录自动补充 __init__.py

    原则：
    - 零 LLM 依赖，纯文件路径解析
    - 已有 __init__.py 的目录不重复创建
    - 仅在 ws_root 非空时生效（有工作区才有意义）
    - 生成的 FileOp 标记 _internal=True，不出现在用户界面

    Returns:
        创建的 __init__.py 数量
    """
    create_ops = [
        op for op in file_ops
        if op.get("op") in ("create", "modify")
    ]
    if not create_ops:
        return 0

    existing_paths = {
        op["path"] for op in file_ops
        if op.get("path") and op.get("op") != "delete"
    }

    init_paths_needed = set()
    for op in create_ops:
        path = op.get("path", "")
        if not path.endswith(".py"):
            continue
        parts = Path(path).parent.parts
        for i in range(1, len(parts) + 1):
            pkg_path = str(Path(*parts[:i]) / "__init__.py").replace("\\", "/")
            if pkg_path != path and pkg_path not in existing_paths:
                init_paths_needed.add(pkg_path)

    count = 0
    for init_path in sorted(init_paths_needed):
        file_ops.append(create_file_op(
            action="create",
            path=init_path,
            content="",
            file_type="file",
            language="python",
            reason="Python 包初始化文件（AlphaPilot 自动补充）",
            from_step="workspace",
        ))
        existing_paths.add(init_path)
        count += 1

    return count


_PROSE_CODE_LEADING_RE = re.compile(
    r"^(?:def|class|import|from|if|elif|else|for|while|with|try|except|"
    r"finally|return|yield|raise|assert|pass|break|continue|global|"
    r"nonlocal|lambda|async|await|@)\b"
)


def _is_discardable_prose(line: str) -> bool:
    """一行是否是「明确可判定的自然语言文本」。

    宁可漏判也不能误删代码：注释、空行、任何能独立 parse 成 Python
    语句的行、以代码关键字开头的行、含 Python 结构符号的行，一律不算污染。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if _PROSE_CODE_LEADING_RE.match(stripped):
        return False
    try:
        ast.parse(stripped)
        return False
    except SyntaxError:
        pass
    # 反引号 / 排版箭头等字符在 Python 源码中非法，是 Markdown 文本的强特征。
    # 早期版本把反引号列入「代码符号」黑名单，导致
    #   `pending` → `confirmed` / `cancelled`
    # 这类污染行被当成代码保留（ShopFlow R6 第二次失败根因）。
    if any(ch in stripped for ch in "`→←↑↓⇒•—–"):
        return True
    if len(stripped.split()) < 4:
        return False
    # 只排除真正能构成 Python 语法的符号；引号/反引号不在此列，
    # 能独立 parse 的行已在上面被排除，不会误伤。
    if any(ch in stripped for ch in "{}[]()=:;\\"):
        return False
    return True


def _repair_python_content(content: str, path: str, max_lines: int = 12) -> tuple:
    """确定性自愈：删除 LLM 混入 Python 文件末尾的自然语言说明行。

    真实故障（2026-11-14 ShopFlow R6）：模型把
      "Optimized the FastAPI + SQLAlchemy e-commerce order management system ..."
    追加到 tests/conftest.py 末尾，compile() 报 SyntaxError。旧门控只打
    _needs_fix 标记就放行，而 test_step 停在 awaiting_authorization，自愈
    轮次被跳过，脏文件直接落盘，造成 R6–R10 连锁失败。

    安全约束（防止自愈本身变成新 Bug）：
      1. 只删被明确判定为自然语言的尾部连续行，遇到任何代码行立即停；
      2. 限制最大删除行数；
      3. 候选内容必须重新 compile() 通过才采纳。
    返回 (修复后内容, 剥离行数)，无法自愈返回 (None, 0)。
    """
    lines = content.splitlines(keepends=True)
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1  # 跳过文件末尾空行，不计入污染
    cut = 0
    idx = end - 1
    while idx >= 0 and cut < max_lines and _is_discardable_prose(lines[idx]):
        cut += 1
        idx -= 1
    if cut == 0:
        return None, 0
    candidate = "".join(lines[:end - cut])
    try:
        compile(candidate, path, "exec")
    except SyntaxError:
        return None, 0
    return candidate, cut


def finalize_task(
    context: dict,
    steps: list,
    events: list,
    mode: str,
    intent: str,
    payload: dict,
    task_id: str = "",
) -> dict:
    """执行任务收尾：文件策略、自清理追踪、授权请求。

    Returns:
        last_output_text (str)
    """
    from ...collaboration_modes import enforce_file_operation_policy

    enforce_file_operation_policy(context, mode, steps=steps, events=events)

    # v3.7: 最小修改约束（题面明写「只改出错文件」时，挡住全量重写）
    try:
        _scope = _enforce_minimal_fix_scope(context, intent)
        if _scope.get("applied"):
            context["meta"]["minimal_fix_scope"] = _scope
            print(f"   ✂️ 最小修改约束: 保留 {len(_scope['kept'])} 个文件，"
                  f"拦下 {len(_scope['dropped'])} 个越界改动 "
                  f"{_scope['dropped'][:6]}")
            # v3.8: 内容级守卫 —— 保留文件被全量重写时，只信任纯新增 import
            _content = _enforce_minimal_fix_content(context, _scope)
            if _content.get("blocked_rewrites"):
                context["meta"]["minimal_fix_content"] = _content
                print(f"   🛡️ 内容级守卫: 拦下 {len(_content['blocked_rewrites'])} 个违约重写，"
                      f"恢复导入 {len(_content.get('import_additions', []))} 行，"
                      f"删除语法坏行 {len(_content.get('import_deletions', []))} 行"
                      f"{_content.get('import_deletions', [])[:3]}")
    except Exception as _se:
        print(f"   ⚠️ 最小修改约束异常（不影响主流程）: {_se}")

    # v3.9: 增量功能题面「不要破坏现有功能」→ 既有文件契约保护
    try:
        _inc = _enforce_incremental_contract(context, intent)
        if _inc.get("applied") or _inc.get("whitelisted"):
            context["meta"]["incremental_contract"] = _inc
            print(f"   🛡️ 增量契约保护: 保留磁盘现状 {len(_inc['blocked'])} 个既有文件 "
                  f"{_inc['blocked'][:6]}；题面点名放行 "
                  f"{len(_inc['whitelisted'])} 个 {_inc['whitelisted'][:6]}")
    except Exception as _ie:
        print(f"   ⚠️ 增量契约保护异常（不影响主流程）: {_ie}")

    # 交付完整性守卫：用户点名的文件漏生成时，带上下文让模型只补漏项
    try:
        _guard = _ensure_requested_deliverables(context, intent)
        if _guard.get("recovered"):
            print(f"   🧩 交付完整性守卫: 补齐 {len(_guard['recovered'])} 个漏项 "
                  f"{_guard['recovered']}")
        elif _guard.get("missing"):
            print(f"   ⚠️ 交付完整性守卫: 检出漏项但未补齐 "
                  f"{_guard['missing']} ({_guard.get('error', '模型未产出有效内容')})")
    except Exception as _ge:
        print(f"   ⚠️ 交付完整性守卫异常（不影响主流程）: {_ge}")

    # v3.2 自清理：追踪本次生成的文件供下次清理
    ws_root = context.get("meta", {}).get("workspace_path", "")
    if ws_root and intent in ("write_code", "fix_code", "refactor", "workspace_maintenance"):
        track_generated_files(redis, ws_root, context["final_file_ops"])
        track_paths = [
            op["path"] for op in context["final_file_ops"]
            if op.get("path") and op.get("op") in ("create", "modify", "test", "doc")
            and not op.get("_internal", False)
        ]
        if track_paths:
            context["final_file_ops"].append(create_file_op(
                "create", ".alphapilot_generated.mark",
                content=json.dumps(sorted(track_paths), ensure_ascii=False, indent=2),
                reason="AlphaPilot 生成文件清单", from_step="workspace",
            ))

    # P0: Python 包完整性 — 自动补充 __init__.py（确定性后处理，零 LLM 依赖）
    if ws_root:
        init_count = _ensure_python_package_inits(context["final_file_ops"])
        if init_count > 0:
            print(f"   📦 Python 包完整性: 自动补充 {init_count} 个 __init__.py")

    # R6 安全契约：为所有文件操作类型生成授权请求
    # CREATE / MODIFY / DELETE / TEST / DOC 均需授权，由 Node.js 独立验证
    op_types = ("create", "modify", "delete", "test", "doc")
    for op_type in op_types:
        matching = [
            op.get("path")
            for op in context.get("final_file_ops", [])
            if op.get("op") == op_type and not op.get("_internal", False)
        ]
        if matching:
            context["meta"].setdefault("authorization_requests", []).append({
                "type": op_type,
                "paths": matching,
                "status": "awaiting_host_policy",
            })

    if context["meta"].get("authorization_requests"):
        context["meta"]["execution_state"] = "awaiting_authorization"

    # R6 安全契约：将授权请求写入 Redis 供 Node.js 执行端独立验证
    _store_authorization_in_redis(context, task_id)

    # ===== v3.4+: 语法错误最终门控 + 落盘前确定性自愈 =====
    # 在任务标记为完成前，对所有 final_file_ops 中的 Python 文件执行编译检查。
    # 编译失败时先尝试原地剥离自然语言污染并验证修复结果；只有确实无法自愈
    # 才标记 _needs_fix 交给下游。
    # 背景：旧版「只标记不修复」在 test_step 停在 awaiting_authorization 时
    # 没有自愈轮次，脏文件会直接落盘，进而污染后续所有轮次（R6→R10 连锁失败）。
    _final_compile_errors = []
    _self_healed = []
    for _fop in context.get("final_file_ops", []):
        _fpath = _fop.get("path") or ""
        _fcontent = _fop.get("content") or ""
        if not (_fpath.endswith(".py") and _fcontent) or _fop.get("_internal"):
            continue
        try:
            compile(_fcontent, _fpath, "exec")
            continue
        except SyntaxError:
            pass

        _repaired, _cut = _repair_python_content(_fcontent, _fpath)
        if _repaired is not None:
            _fop["content"] = _repaired
            _fop["_syntax_self_healed"] = True
            _self_healed.append(f"{_fpath} (剥离 {_cut} 行)")
            print(f"[INFO] finalize_task: 语法自愈 {_fpath}，剥离 {_cut} 行非代码文本")
            continue

        try:
            compile(_fcontent, _fpath, "exec")
        except SyntaxError as _fse:
            _fop["_compile_error"] = str(_fse)
            _fop["_needs_fix"] = True
            _final_compile_errors.append(f"{_fpath}: {_fse}")
    if _self_healed:
        context["meta"]["_syntax_self_healed"] = _self_healed
    if _final_compile_errors:
        print(
            f"[WARN] finalize_task: {len(_final_compile_errors)} Python "
            f"文件存在语法错误（已尝试自愈失败，标记 _needs_fix）"
        )
        context["meta"]["_final_compile_errors"] = _final_compile_errors

    # ===== v3.6: 交付前隔离沙箱自检（不写用户工作区、不碰授权边界）=====
    # 静态门控只能抓 SyntaxError，抓不到 422 / 未定义 ORM 关系等运行时错误。
    # 这里把本次生成的文件放进临时目录跑一遍 pytest，失败时把真实报错
    # 交回模型做「只改内容、不落盘」的修复，最多 2 轮。
    try:
        from ...shadow_verify import verify_and_repair
        _sv = verify_and_repair(context, intent)
        context["meta"]["shadow_verify"] = _sv
        # ===== G10.15 FAIL-CLOSED：自检失败 + 有良好基线 → 保留磁盘现状 =====
        # 旧行为：ShadowVerify 两轮失败只"保留错误证据"，EvidenceGate 照样
        # 准入，缺陷交付落盘，把 R8 的 15 个失败扩散成 R9/R10 连锁崩。
        if _sv.get("block_delivery"):
            _before = len(context.get("final_file_ops", []) or [])
            context["final_file_ops"] = [
                op for op in (context.get("final_file_ops") or [])
                if op.get("_internal")
            ]
            context["meta"]["delivery_blocked"] = {
                "reason": (_sv.get("delivery_gate") or {}).get("reason", ""),
                "rounds": _sv.get("rounds", 0),
                "dropped_ops": _before - len(context["final_file_ops"]),
                "final_error": (_sv.get("delivery_gate") or {}).get("final_error", "")[-800:],
            }
            print(f"   ⛔ 交付闸门 FAIL-CLOSED: 丢弃 {_before - len(context['final_file_ops'])} 个写操作，"
                  f"保留磁盘现状（{(_sv.get('delivery_gate') or {}).get('reason', '')}）")
    except Exception as _sve:
        context["meta"]["shadow_verify"] = {"ran": False, "error": str(_sve)}
        print(f"[WARN] finalize_task: 沙箱自检异常（不影响交付）: {_sve}")

    # ===== v3.5: 格式污染检测 =====
    # 确定性检查 Python 文件中是否混入了 LLM 步骤标记
    # （refine: / test: / write: / fix: / plan: / analyze:）
    # 这些标记如果出现在非注释/非字符串行，会导致 SyntaxError，
    # 但有些可能被 Python 当作合法声明侥幸通过编译。
    # 本检查作为编译门控的补充防线，捕获编译可过但语义污染的 case。
    _STEP_MARKERS = re.compile(
        r'^\s*(refine|test|write|fix|plan|analyze|execute|respond):',
        re.IGNORECASE
    )
    _pollution_errors = []
    for _fop in context.get("final_file_ops", []):
        _fpath = _fop.get("path") or ""
        _fcontent = _fop.get("content") or ""
        if not _fpath.endswith(".py") or not _fcontent or _fop.get("_internal"):
            continue
        for _li, _line in enumerate(_fcontent.splitlines(), 1):
            _m = _STEP_MARKERS.match(_line)
            if _m:
                _pollution_errors.append(
                    f"{_fpath}:{_li}: 格式污染 — 步骤标记 '{_m.group(1)}:' 出现在代码中"
                )
    if _pollution_errors:
        print(
            f"[WARN] finalize_task: {len(_pollution_errors)} 个格式污染"
            f"（步骤标记混入代码文件）"
        )
        context["meta"]["_format_pollution"] = _pollution_errors
        # 不阻断发布——错误标记已写入 FileOps，
        # 下游（test_step 全量 pytest / Node API 通知）可据此告警

    # P2-6: 标记 context 为终止
    context["_task_terminated"] = True

    return steps[-1].get("output", {}).get("text", "") if steps else ""