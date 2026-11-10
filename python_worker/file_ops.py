# -*- coding: utf-8 -*-
# file_ops.py — AlphaPilot OS v3.0 官方 + 智能增强版
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有 FileOps 的生成、解析、验证都必须发生在 Worker 内部
#    - Node API、VSCode 插件、前端都不能推断文件内容，只能执行 FileOps
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - FileOps 是 AlphaPilot OS 的唯一文件操作协议
#    - 所有文件写入必须通过 FileOps，不允许 Worker 直接写文件
#    - FileOps 的结构必须稳定、可预测、可验证
#
# 本模块负责：
# 1. 解析 LLM 输出的多文件协议（# FILE / # TEST / # DOC / # META / # DEPENDS）
# 2. 生成标准化 FileOps（action/path/type/content）
# 3. 验证 FileOps 的合法性
# ---------------------------------------------------------

# -*- coding: utf-8 -*-
# file_ops.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# FileOps Parser v3.0
# 支持：
# - 多文件协议 (# FILE: path)
# - 测试协议 (# TEST: path)
# - 文档协议 (# DOC: path)
# - 元数据 (# META: key=value)
# - 依赖声明 (# DEPENDS: file1,file2)
# - create / modify / delete / test / doc / meta / depends
# ---------------------------------------------------------

import re
import json


# =========================================================
# 0. JSON 包裹检测与解包 (v3.2)
#    LLM 有时会输出 {"filename": {"content": "..."}} 而非纯文件内容
#    本函数自动检测并提取内部 content，防止 JSON 协议被当成文件内容写入磁盘
# =========================================================

def _unwrap_json_content(content: str, expected_path: str = None) -> str:
    if not content or not content.strip().startswith("{"):
        return content
    try:
        data = json.loads(content)
        if isinstance(data, dict) and len(data) == 1:
            for key, value in data.items():
                if isinstance(value, dict) and "content" in value:
                    if expected_path and key != expected_path:
                        continue
                    unwrapped = str(value["content"])
                    if unwrapped.strip():
                        return unwrapped
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return content


# =========================================================
# 1. FileOp 创建器（Worker 所有步骤都依赖）
# =========================================================

def create_file_op(
    action: str,
    path: str = None,
    content: str = "",
    file_type: str = "file",
    language: str = None,
    reason: str = "",
    from_step: str = "",
    intent: str = "",
    data: dict = None
):
    """
    创建一个 FileOp（Worker → Node.js）
    """
    op = {
        "op": action,
        "path": path,
        "content": content,
        "file_type": file_type,
        "language": language,
        "reason": reason,
        "from_step": from_step,
        "intent": intent,
    }

    if data:
        op["data"] = data

    return op


# =========================================================
# 2. 多文件协议解析器
# =========================================================

# v3.6: 多语言 FILE 标记 — LLM 对非 Python 文件可能使用语言原生注释语法
# 例：Python 用 # FILE:，JS/TS 用 // FILE:，CSS 用 /* FILE:，HTML 用 <!-- FILE:
FILE_PATTERN  = re.compile(r"^(?:#|//|/\*\s*)\s*FILE:\s*(.+?)(?:\s*\*/)?$", re.MULTILINE)
TEST_PATTERN  = re.compile(r"^(?:#|//)\s*TEST:\s*(.+)$", re.MULTILINE)
DOC_PATTERN   = re.compile(r"^(?:#|//)\s*DOC:\s*(.+)$", re.MULTILINE)
META_PATTERN  = re.compile(r"^(?:#|//)\s*META:\s*(.+)$", re.MULTILINE)
DEPENDS_PATTERN = re.compile(r"^(?:#|//)\s*DEPENDS:\s*(.+)$", re.MULTILINE)
DELETE_PATTERN  = re.compile(r"^(?:#|//)\s*DELETE:\s*(.+)$", re.MULTILINE)

# v3.6: HTML/XML 风格需要单独处理（<!-- 和 --> 包围）
HTML_FILE_PATTERN = re.compile(r"<!--\s*FILE:\s*(.+?)\s*-->", re.MULTILINE)


def contains_multi_file_protocol(text: str) -> bool:
    """
    v3.6: 判断是否包含多文件协议（支持多语言标记）
    """
    return (
        "# FILE:" in text or "// FILE:" in text or "/* FILE:" in text
        or "# TEST:" in text or "// TEST:" in text
        or "# DOC:" in text or "// DOC:" in text
        or "# META:" in text or "// META:" in text
        or "# DEPENDS:" in text or "// DEPENDS:" in text
        or "# DELETE:" in text or "// DELETE:" in text
        or "<!-- FILE:" in text
    )


def parse_fileops_v3(text: str):
    """
    将 LLM 输出解析为 file_ops 列表
    
    ⭐ v3.1 修复：所有文件操作统一使用 create/modify/delete，通过 reason 和 from_step 区分用途
    """
    file_ops = []

    # 1) FILE - 主代码文件（v3.6: 同时匹配 # FILE:、// FILE:、/* FILE:）
    for match in FILE_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        content = _unwrap_json_content(content, expected_path=path)
        file_ops.append(create_file_op("create", path, content, reason="主代码文件", from_step="write"))

    # 1b) HTML/XML FILE 标记（<!-- FILE: ... -->）
    for match in HTML_FILE_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        content = _unwrap_json_content(content, expected_path=path)
        file_ops.append(create_file_op("create", path, content, reason="主代码文件", from_step="write"))

    # 2) TEST - 测试文件（使用 create 操作，标注来源）
    for match in TEST_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        content = _unwrap_json_content(content, expected_path=path)
        file_ops.append(create_file_op("create", path, content, reason="测试文件", from_step="test"))

    # 3) DOC - 文档文件（使用 create 操作，标注来源）
    for match in DOC_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        content = _unwrap_json_content(content, expected_path=path)
        file_ops.append(create_file_op("create", path, content, reason="文档文件", from_step="doc"))

    # 4) DELETE - deletion proposals; the host applies its authorization policy.
    for match in DELETE_PATTERN.finditer(text):
        path = match.group(1).strip()
        file_ops.append(
            create_file_op(
                "delete",
                path,
                reason="用户请求的删除候选项",
                from_step="write",
            )
        )

    # 5) META - 元数据（保留特殊操作类型，但标记为内部使用）
    for match in META_PATTERN.finditer(text):
        data = parse_meta(match.group(1))
        meta_op = create_file_op("meta", data=data)
        meta_op["_internal"] = True  # 标记为内部元数据，不推送给前端
        file_ops.append(meta_op)

    # 6) DEPENDS - 依赖声明（保留特殊操作类型，但标记为内部使用）
    for match in DEPENDS_PATTERN.finditer(text):
        deps = [d.strip() for d in match.group(1).split(",")]
        depends_op = create_file_op("depends", data={"files": deps})
        depends_op["_internal"] = True  # 标记为内部依赖信息
        file_ops.append(depends_op)

    return file_ops


# =========================================================
# 3. 工具函数
# =========================================================

# v3.6: 多语言 FILE: 标记的正则模式（LLM 对非 Python 文件可能使用语言原生的注释语法）
# ALL_BLOCK_MARKERS 统一所有块标记，供 extract_block 和多文件解析器识别
_ALL_BLOCK_MARKER_PATTERNS = {
    "# FILE:", "# TEST:", "# DOC:", "# DELETE:", "# META:", "# DEPENDS:",
    "// FILE:", "// TEST:", "// DOC:", "// DELETE:", "// META:", "// DEPENDS:",
    "/* FILE:", "/* TEST:", "/* DOC:", "/* DELETE:",
    "<!-- FILE:", "<!-- TEST:", "<!-- DOC:",
}


def _is_block_marker(line: str) -> bool:
    """判断一行是否为任何语言的 FILE: / TEST: / DOC: 等块标记"""
    stripped = line.strip()
    for prefix in _ALL_BLOCK_MARKER_PATTERNS:
        if stripped.startswith(prefix):
            return True
    return False


def _strip_markdown_fences(content: str) -> str:
    """
    v3.6: 递归剥离所有 Markdown 代码围栏（`` ``` ``、`` ```python `` 等）
    
    处理 LLM 生成的多文件输出中包含嵌套/连续 fence 的情况：
       ```
       ```python
       # FILE: app.py
       ...
       ```
       
       ```typescript
       // FILE: App.tsx
       ...
       ```
       ```
    
    策略：移除所有以 ``` 开头或结尾的行（即 fence 标记行）。
    """
    if not content:
        return content
    lines = content.splitlines()
    result = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(result).strip()


def extract_block(text: str, start_pos: int) -> str:
    """
    v3.6: 提取 FILE/TEST/DOC 后面的代码块（多语言 + 嵌套 fence 清洗）
    
    增强：
    - 识别 // FILE:（JS/TS）、/* FILE:（CSS）、<!-- FILE:（HTML）等非 Python 标记
    - 自动剥离所有 Markdown fence 行（不仅外层一对）
    """
    lines = text[start_pos:].splitlines()
    collected = []

    for line in lines:
        # v3.6: 遇到任何语言的块标记都停止收集
        if _is_block_marker(line):
            break
        collected.append(line)

    content = "\n".join(collected).strip()
    
    # v3.6: 递归剥离所有 markdown fence（不仅外层一对）
    content = _strip_markdown_fences(content)
    
    return content


def parse_meta(meta_str: str) -> dict:
    """
    解析 META: key=value,key=value
    """
    data = {}
    for pair in meta_str.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            data[k.strip()] = v.strip()
    return data


# =========================================================
# 4. FileOps 验证器（可选）
# =========================================================

def validate_file_ops(file_ops):
    """
    简单验证（Node.js 会做更严格的验证）
    """
    errors = []
    for op in file_ops:
        if "op" not in op:
            errors.append("缺少 op 字段")
        if op["op"] in ["create", "modify", "delete", "test", "doc"] and not op.get("path"):
            errors.append(f"操作 {op['op']} 缺少 path")
    return errors


# =========================================================
# 5. FileOps 过滤工具函数（v3.1.1 新增）
# =========================================================

# v3.5: 多语言代码文件扩展名，供 refine / fix / doc 等步骤按语言过滤
# 遵循 G10 "Capability = 唯一实现"：所有步骤通过同一套扩展名表判断代码文件
CODE_EXTENSIONS = frozenset({
    ".py", ".pyi", ".pyx",      # Python
    ".java", ".kt", ".kts",     # Java / Kotlin
    ".js", ".mjs", ".cjs",      # JavaScript
    ".ts", ".tsx",               # TypeScript
    ".jsx",                       # JSX (keep separate from .js for clarity)
    ".go",                        # Go
    ".rs",                        # Rust
    ".rb",                        # Ruby
    ".php", ".phtml",            # PHP
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",  # C / C++
    ".cs",                        # C#
    ".swift",                     # Swift
    ".scala", ".sc",             # Scala
    ".sh", ".bash", ".zsh",      # Shell
    ".sql", ".psql",             # SQL
    ".r",                         # R
    ".lua",                       # Lua
    ".dart",                      # Dart
    ".ex", ".exs",               # Elixir
    ".erl", ".hrl",              # Erlang
    ".hs",                        # Haskell
    ".clj", ".cljs", ".cljc",   # Clojure
    ".vue", ".svelte",           # Frontend frameworks
    ".yaml", ".yml",             # Config (may contain code-as-config)
})


def filter_valid_file_ops(file_ops: list, exclude_internal: bool = True) -> list:
    """
    过滤出有效的文件操作（v3.1.1 空值保护）
    
    Args:
        file_ops: 原始 FileOps 列表
        exclude_internal: 是否排除内部元数据（默认 True）
    
    Returns:
        过滤后的有效 FileOps 列表
    
    Example:
        >>> valid_ops = filter_valid_file_ops(context["final_file_ops"])
        >>> py_files = [fo for fo in valid_ops if fo["path"].endswith(".py")]
    """
    if not file_ops:
        return []
    
    # 第一层过滤：移除 path 为 None 或空字符串的操作
    result = [fo for fo in file_ops if fo.get("path") and isinstance(fo.get("path"), str)]
    
    # 第二层过滤：移除内部元数据（如果启用）
    if exclude_internal:
        result = [fo for fo in result if not fo.get("_internal", False)]
    
    return result


def get_code_files(file_ops: list) -> list:
    """
    从 FileOps 中提取所有受支持的代码文件（v3.5 多语言支持）
    使用 CODE_EXTENSIONS 常量统一判定，不限定单一语言。
    
    Args:
        file_ops: FileOps 列表
    
    Returns:
        代码文件的 FileOps 列表
    
    Example:
        >>> code_files = get_code_files(context["final_file_ops"])
        >>> for f in code_files:
        ...     print(f["path"])  # backend/main.py, frontend/App.tsx, ...
    """
    valid_ops = filter_valid_file_ops(file_ops)
    return [fo for fo in valid_ops if _is_code_file(fo.get("path", ""))]


def get_python_files(file_ops: list) -> list:
    """
    从 FileOps 中提取所有 Python 文件（便捷函数）
    
    Args:
        file_ops: FileOps 列表
    
    Returns:
        Python 文件的 FileOps 列表
    
    Example:
        >>> py_files = get_python_files(context["final_file_ops"])
    """
    valid_ops = filter_valid_file_ops(file_ops)
    return [fo for fo in valid_ops if fo["path"].endswith(".py")]


def _is_code_file(file_path: str) -> bool:
    """
    判断文件路径是否为支持的代码文件（v3.5）
    内部使用 CODE_EXTENSIONS 进行后缀匹配。
    """
    if not file_path:
        return False
    for ext in CODE_EXTENSIONS:
        if file_path.endswith(ext):
            return True
    return False


def normalize_fileop_paths(file_ops: list, workspace_root: str = None) -> list:
    """
    归一化 FileOp 路径，去掉重复的项目名前缀（工业级修复）。

    背景：LLM 在 write 阶段生成 `# FILE:` 路径时，可能把 workspace root 的
    basename（项目名）错误地写进路径，导致写盘落点到嵌套目录，例如：
      workspace_root = C:/Users/49772/Desktop/shopflow_ecommerce
      LLM 输出 path = shopflow_ecommerce/backend/models/enums.py
      → Node 侧 join 后变成 shopflow_ecommerce/shopflow_ecommerce/backend/...

    本函数在 Worker 端（真相源）做确定性修正：当 FileOp path 以 workspace
    root 的 basename 作为首段前缀时，去掉该前缀，使路径重新相对 workspace root。

    信条约束（Worker = 真相）：这是 Worker 内部对自身产出的修正，
    不新增任何跨组件通道，Node 侧仍只忠实执行 FileOps，不做推断。

    Args:
        file_ops: parse_fileops_v3 输出的 FileOps 列表
        workspace_root: workspace root 的绝对路径（meta["workspace_path"]）

    Returns:
        原地归一化后的 FileOps 列表
    """
    if not file_ops or not workspace_root:
        return file_ops
    root = workspace_root.replace("\\", "/").rstrip("/")
    basename = root.rsplit("/", 1)[-1]
    if not basename:
        return file_ops
    prefix = basename + "/"
    for op in file_ops:
        p = op.get("path")
        if not p:
            continue
        norm = p.replace("\\", "/")
        if norm.startswith(prefix):
            new_path = norm[len(prefix):]
            if new_path:
                op["path"] = new_path
    return file_ops


def merge_file_ops(context: dict, new_ops: list, source_step: str = "") -> list:
    """
    v3.5 工业级 FileOp 合并（G10 唯一入口）
    
    按 path 进行增量合并：new_ops 中存在的路径覆盖旧值，
    new_ops 中不存在的路径保留旧值（不被丢弃）。
    
    解决问题：
    - refine_step 用 = 全量替换导致非 Python 文件被丢弃
    - docstring_step 用 = 全量替换存在脆弱性
    - fix_step 本地重写了相同逻辑（违反 G10 "唯一实现"）
    
    Args:
        context: Worker 上下文字典（被原地修改）
        new_ops: 新的 FileOp 列表
        source_step: 调用来源步骤名（用于日志，可选）
    
    Returns:
        合并后的 final_file_ops 列表
    
    Example:
        >>> merge_file_ops(context, refined_file_ops, source_step="refine")
    """
    if not new_ops:
        return context.get("final_file_ops", []) if context else []
    
    # context 为空 dict 时 {} 是 falsy，需显式处理
    if context is None:
        context = {}
    existing = context.get("final_file_ops") or context.get("file_ops") or []
    
    # 构建新路径集合，用于去重
    changed_paths = {op.get("path") for op in new_ops if op.get("path")}
    
    # 保留不在 new_ops 中的旧文件（跨语言保护的关键）
    merged = [op for op in existing if op.get("path") not in changed_paths]
    merged.extend(new_ops)
    
    # 写入唯一真相源
    context["final_file_ops"] = merged
    context["file_ops"] = merged
    
    preserved = len(existing) - len([op for op in existing if op.get("path") in changed_paths])
    if source_step and preserved > 0:
        print(f"  [merge_file_ops] {source_step}: 保留 {preserved} 个未变更文件, "
              f"更新 {len(new_ops)} 个, 最终 {len(merged)} 个")

    # v3.7: 合并后自动执行结构完整性验证
    try:
        validation = validate_generated_files(merged)
        context["validation"] = validation
        if validation["errors"]:
            err_types = ", ".join(e["type"] for e in validation["errors"])
            print(f"  [validate] {source_step}: {len(validation['errors'])} 结构缺陷 "
                  f"({err_types})")
        if validation["warnings"]:
            wrn_types = ", ".join(w["type"] for w in validation["warnings"])
            print(f"  [validate] {source_step}: {len(validation['warnings'])} 警告 "
                  f"({wrn_types})")
    except Exception:
        pass
    
    return merged


# =========================================================
# 6. 生成文件结构完整性验证 (v3.7)
#    在 merge_file_ops 写入 context 后、Extension 写盘前，
#    对最终 FileOp 集合进行跨文件 AST 级别的结构完整性检查。
#
#    验证器检测以下缺陷类：
#    6.1 FastAPI Router 未注册 (unregistered_router)
#    6.2 跨文件可变状态冲突 (duplicate_mutable_state)
#    6.3 Python 语法错误 (python_syntax_error)
#    6.4 导入引用了不存在的生成文件 (orphan_import)
#    6.5 前端依赖缺失 (missing_frontend_dep)
#
#    设计原则：
#    - 只检测不修复 — 修复决策属于 LLM (fix_step)
#    - 所有异常静默降级 — 验证失败不阻断写盘
#    - 结果注入 context["validation"] 供下游消费
# =========================================================

import ast as _ast


def validate_generated_files(file_ops: list) -> dict:
    """
    v3.7 — 对最终 FileOp 集合执行跨文件结构完整性验证

    在 merge_file_ops() 写入 context 后、Extension 写盘前调用。
    返回结构化验证报告，注入 context["validation"]。

    Args:
        file_ops: merge_file_ops() 产出的最终 FileOp 列表

    Returns:
        {
            "errors":   [{"type": str, "path": str, "detail": str, ...}],
            "warnings": [{"type": str, "path": str, "detail": str, ...}],
            "checks": {"passed": int, "warned": int, "errored": int},
        }
    """
    errors = []
    warnings = []

    try:
        errors.extend(_check_fastapi_router_registration(file_ops))
    except Exception:
        pass

    try:
        warnings.extend(_check_cross_file_state_conflicts(file_ops))
    except Exception:
        pass

    try:
        errors.extend(_validate_python_syntax(file_ops))
    except Exception:
        pass

    try:
        warnings.extend(_check_import_integrity(file_ops))
    except Exception:
        pass

    try:
        warnings.extend(_check_frontend_dependency_gaps(file_ops))
    except Exception:
        pass

    try:
        errors.extend(_check_orm_model_integrity(file_ops))
    except Exception:
        pass

    try:
        errors.extend(_check_schema_model_integrity(file_ops))
    except Exception:
        pass

    try:
        warnings.extend(_check_architectural_layer_isolation(file_ops))
    except Exception:
        pass

    return {
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "passed": len(file_ops) - len(errors) - len(warnings),
            "warned": len(warnings),
            "errored": len(errors),
        },
    }


# ── 6.1 FastAPI Router 注册完整性检查 ─────────────────────

def _check_fastapi_router_registration(file_ops: list) -> list:
    """
    v3.8 跨文件分析 — 检测 Python 文件中定义了 APIRouter 但未在项目任何文件中用 include_router 注册的情况。

    检测逻辑（跨文件）：
    1. 扫描所有 .py 文件，找到定义了 "router = APIRouter(" 的文件
    2. 扫描所有 .py 文件中是否包含 "include_router(router)" 或 "app.include_router"
    3. 只有在整个项目 FileOp 集合中都找不到 include_router 时才报告
    """
    findings = []

    # 收集所有定义了 APIRouter 的文件
    router_files = []
    all_contents = []

    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        content = op.get("content") or ""
        all_contents.append(content)
        if "APIRouter(" in content:
            router_files.append((path, content))

    if not router_files:
        return findings

    # 检查整个项目范围内是否存在 include_router
    any_include = any("include_router" in c for c in all_contents)

    for path, content in router_files:
        if re.search(r'(?:^|\n)\s*router\s*=\s*APIRouter\(', content):
            if not any_include:
                findings.append({
                    "type": "unregistered_router",
                    "path": path,
                    "detail": "APIRouter 'router' defined but not registered with app.include_router(router) anywhere in the project",
                    "fix_hint": "add 'app.include_router(router)' in your main.py or equivalent entry point",
                })

    return findings


# ── 6.2 跨文件可变状态冲突检测 ─────────────────────────────

# Mutable assignment patterns: identifiers assigned dict/list/set/class instances at module level
_MUTABLE_ASSIGN_PATTERN = re.compile(
    r'^(?!#)(?:[a-zA-Z_]\w*)\s*=\s*(?:\{\}|\[\]|set\(\)|[A-Z]\w+\([^)]*\))\s*$',
    re.MULTILINE
)

# Whitelist: these names are commonly bound at module level as singletons
# and are NOT considered conflicts (e.g., app = FastAPI() is expected)
_HEADLESS_SINGLETON_NAMES = frozenset({
    "app", "router", "client", "metadata", "__all__", "__version__",
    "logger", "engine", "SessionLocal", "Base",
})


def _check_cross_file_state_conflicts(file_ops: list) -> list:
    """
    检测多个 Python 文件在模块级别定义了同名的可变状态变量。

    典型错误：models.py 和 dependencies.py 各定义 task_store = {}
    LLM 不理解 Python 模块作用域隔离，导致数据被写入一个模块但路由从另一个模块读取。
    """
    # {变量名: [(文件路径, 赋值行), ...]}
    state_map = {}
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        content = op.get("content") or ""
        if not content:
            continue
        for match in _MUTABLE_ASSIGN_PATTERN.finditer(content):
            line = match.group().strip()
            varname = line.split("=")[0].strip()
            if varname in _HEADLESS_SINGLETON_NAMES:
                continue
            if varname not in state_map:
                state_map[varname] = set()
            state_map[varname].add(path)

    findings = []
    for varname, paths in state_map.items():
        if len(paths) > 1:
            findings.append({
                "type": "duplicate_mutable_state",
                "paths": sorted(paths),
                "variable": varname,
                "detail": (
                    f"'{varname}' is defined as mutable in {len(paths)} files: "
                    f"{', '.join(paths)}. Data written to one module's {varname} "
                    f"is invisible to the other module. Choose one canonical module "
                    f"and import it."
                ),
                "fix_hint": (
                    f"keep '{varname}' in one module (e.g., {sorted(paths)[0]}), "
                    f"delete the duplicate in others, and import it"
                ),
            })
    return findings


# ── 6.3 Python 语法验证 ─────────────────────────────────────

def _validate_python_syntax(file_ops: list) -> list:
    """
    对所有 .py 文件执行 AST 语法检查。
    compile() 通过的不报告；SyntaxError 捕获后报告具体位置。
    """
    findings = []
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        content = op.get("content") or ""
        if not content or not content.strip():
            continue
        try:
            _ast.parse(content)
        except SyntaxError as e:
            findings.append({
                "type": "python_syntax_error",
                "path": path,
                "line": e.lineno,
                "detail": f"SyntaxError at line {e.lineno}: {e.msg}",
                "fix_hint": f"fix syntax error on line {e.lineno} in {path}",
            })
    return findings


# ── 6.4 导入完整性检查 ──────────────────────────────────────

# Extract relative imports: from .module import X / from ..pkg import Y
_REL_IMPORT_PATTERN = re.compile(
    r'^from\s+(\.+[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s+import\s+',
    re.MULTILINE
)


def _check_import_integrity(file_ops: list) -> list:
    """
    检测 Python 文件的相对导入是否指向不存在于生成文件集中的模块。

    例如: from .dependencies import get_db_session
    如果 dependencies.py 不在 file_ops 中 → 报告 orphan_import
    """
    # 构建生成文件的模块名→路径映射
    generated_modules = {}
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        # 将文件路径转为模块名: backend/main.py → backend.main
        module_path = path.replace("/", ".").replace("\\", ".").removesuffix(".py")
        generated_modules[path] = module_path
        # 也注册短名: backend/main.py → main
        short = module_path.split(".")[-1] if "." in module_path else module_path
        generated_modules[short] = module_path

    findings = []
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        content = op.get("content") or ""
        if not content:
            continue
        for match in _REL_IMPORT_PATTERN.finditer(content):
            import_target = match.group(1)
            # 跳过标准库和第三方导入（不跟相对路径）
            if import_target.startswith("."):
                # 解析相对导入的目标模块
                current_module = path.replace("/", ".").replace("\\", ".").removesuffix(".py")
                current_parts = current_module.split(".")
                dots = len(import_target) - len(import_target.lstrip("."))
                base = import_target.lstrip(".")
                if dots > len(current_parts):
                    continue  # 过多的 .. 无法解析
                target_parts = current_parts[:len(current_parts) - dots]
                if base:
                    target_parts = target_parts + base.split(".")
                target_module = ".".join(target_parts)

                # 检查目标模块是否在生成文件集中
                known = False
                for known_mod in generated_modules.values():
                    if known_mod == target_module or known_mod.endswith("." + target_module):
                        known = True
                        break
                if not known:
                    findings.append({
                        "type": "orphan_import",
                        "path": path,
                        "import_path": import_target,
                        "detail": (
                            f"'{import_target}' imports module '{target_module}' "
                            f"which is not in the generated file set"
                        ),
                        "fix_hint": (
                            f"ensure '{target_module.replace('.', '/')}.py' is created "
                            f"or fix the import path"
                        ),
                    })
    return findings


# ── 6.5 前端依赖完整性检查 ─────────────────────────────────

_JS_PACKAGE_MANAGER_COMMANDS = frozenset({
    "react-scripts", "vite", "webpack", "parcel", "rollup", "esbuild",
    "next", "nuxt", "gatsby", "expo", "tsc", "ts-node", "jest",
    "vitest", "cypress", "playwright", "eslint", "prettier",
})


def _check_frontend_dependency_gaps(file_ops: list) -> list:
    """
    检测前端 package.json 中 scripts 引用了但未在 dependencies/devDependencies
    中声明的构建工具/测试工具。

    典型错误：scripts 中有 "react-scripts start" 但 react-scripts 未安装。
    """
    findings = []
    seen_pairs = set()
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith("package.json"):
            continue
        content = op.get("content") or ""
        if not content:
            continue
        try:
            pkg = json.loads(content)
        except json.JSONDecodeError:
            continue
        scripts = pkg.get("scripts", {})
        deps = set(pkg.get("dependencies", {}).keys())
        dev_deps = set(pkg.get("devDependencies", {}).keys())
        all_deps = deps | dev_deps

        for _script_name, script_cmd in scripts.items():
            if not isinstance(script_cmd, str):
                continue
            for tool in _JS_PACKAGE_MANAGER_COMMANDS:
                if tool in script_cmd and tool not in all_deps:
                    key = (path, tool)
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    findings.append({
                        "type": "missing_frontend_dep",
                        "path": path,
                        "dependency": tool,
                        "detail": (
                            f"'{tool}' is used in scripts but not declared "
                            f"in dependencies or devDependencies"
                        ),
                        "fix_hint": f"run 'npm install {tool}' or add to devDependencies",
                    })
    return findings


# ── 6.6 ORM 模型完整性检查 ─────────────────────────────────
# 检测 models/ 目录中的文件是否包含 SQLAlchemy ORM 模型（Base 子类）。
# 如果 models/ 文件存在但不含任何 Base 子类 → 模型层可能被错误替换。

_SQLALCHEMY_ORM_PATTERN = re.compile(
    r'class\s+(\w+)\s*\(\s*(?:(\w+\.)?Base\s*[,\)])',
    re.MULTILINE
)
_SQLALCHEMY_IMPORT_PATTERN = re.compile(
    r'from\s+sqlalchemy\s+import\s+.*\b(?:Column|Integer|String|Float|Boolean|DateTime)\b',
    re.MULTILINE
)


def _check_orm_model_integrity(file_ops: list) -> list:
    """检测 models/ 目录中的 .py 文件是否包含 SQLAlchemy ORM 模型（Base 子类）。

    如果 models/ 中只有 Pydantic BaseModel 而没有 SQLAlchemy Base 子类，
    说明 LLM 在重构时错误地将 ORM 模型替换成了纯 Pydantic schema。
    """
    findings = []
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        if "models" not in path.replace("\\", "/").split("/"):
            continue
        content = op.get("content") or ""
        if not content.strip():
            continue

        has_orm_class = bool(_SQLALCHEMY_ORM_PATTERN.search(content))
        has_sqlalchemy_cols = bool(_SQLALCHEMY_IMPORT_PATTERN.search(content))
        has_pydantic = "BaseModel" in content
        has_tablename = "__tablename__" in content

        if (has_tablename or has_pydantic) and not has_orm_class and not has_sqlalchemy_cols:
            if has_pydantic:
                findings.append({
                    "type": "model_layer_corrupted",
                    "path": path,
                    "detail": (
                        f"models/ 文件 {path} 包含 Pydantic BaseModel 但没有 SQLAlchemy ORM 模型 "
                        f"(缺少 Base 子类或 sqlalchemy Column 导入)。"
                        f"ORM 模型被错误替换为纯 Pydantic schema——数据库操作将失败。"
                    ),
                    "fix_hint": (
                        f"恢复 {path} 中的 SQLAlchemy ORM 模型：类必须继承 Base，"
                        f"使用 Column(String/Integer/Float) 定义字段，设置 __tablename__。"
                        f"Pydantic schema 只能放在 schemas/ 目录中。"
                    ),
                })

    return findings


# ── 6.7 Pydantic Schema 完整性检查 ──────────────────────────

_PYDANTIC_BASEMODEL_PATTERN = re.compile(
    r'class\s+(\w+)\s*\(\s*(?:(\w+\.)?BaseModel\s*[,\)])',
    re.MULTILINE
)


def _check_schema_model_integrity(file_ops: list) -> list:
    """检测 schemas/ 目录中的 .py 文件是否包含 Pydantic BaseModel 子类。

    如果 schemas/ 文件存在但不含任何 BaseModel → schema 层可能被破坏。
    """
    findings = []
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        path_parts = path.replace("\\", "/").split("/")
        if "schemas" not in path_parts:
            continue
        content = op.get("content") or ""
        if not content.strip():
            continue

        has_basemodel = bool(_PYDANTIC_BASEMODEL_PATTERN.search(content))
        has_pydantic_import = "from pydantic import" in content or "from pydantic import BaseModel" in content
        has_sqlalchemy_cols = bool(_SQLALCHEMY_IMPORT_PATTERN.search(content))
        has_tablename = "__tablename__" in content

        if has_sqlalchemy_cols or has_tablename:
            findings.append({
                "type": "schema_layer_corrupted",
                "path": path,
                "detail": (
                    f"schemas/ 文件 {path} 包含 SQLAlchemy ORM 定义 "
                    f"(__tablename__ 或 sqlalchemy Column)。"
                    f"Schema 层不应该包含 ORM 模型——请移除并放入 models/。"
                ),
                "fix_hint": (
                    f"从 {path} 中移除 SQLAlchemy ORM 模型类，只保留 Pydantic BaseModel。"
                    f"ORM 模型只能放在 models/ 目录中。"
                ),
            })

        if has_pydantic_import and not has_basemodel:
            findings.append({
                "type": "schema_missing_basemodel",
                "path": path,
                "detail": (
                    f"schemas/ 文件 {path} 导入了 pydantic 但没有定义 BaseModel 子类。"
                ),
                "fix_hint": f"在 {path} 中确保至少有一个 class 继承 BaseModel。",
            })

    return findings


# ── 6.8 架构层隔离检查 ──────────────────────────────────────

def _check_architectural_layer_isolation(file_ops: list) -> list:
    """检测架构层的职责隔离：ORM 模型不应出现在非 models/ 目录，
    Pydantic schema 不应出现在非 schemas/ 目录。

    这是预防性检查：当 LLM 重构时可能把 ORM 模型写到 routers/ 或 services/ 中。
    """
    findings = []
    for op in file_ops:
        path = op.get("path") or ""
        if not path or not path.endswith(".py"):
            continue
        content = op.get("content") or ""
        if not content.strip():
            continue

        path_parts = path.replace("\\", "/").split("/")
        dir_name = path_parts[-2] if len(path_parts) >= 2 else ""

        has_orm_class = bool(_SQLALCHEMY_ORM_PATTERN.search(content))
        has_tablename = "__tablename__" in content
        has_basemodel_class = bool(_PYDANTIC_BASEMODEL_PATTERN.search(content))

        # ORM 模型出现在非 models/ 目录
        if (has_orm_class or has_tablename) and "models" not in path_parts and dir_name != "models":
            findings.append({
                "type": "orm_model_in_wrong_layer",
                "path": path,
                "detail": (
                    f"SQLAlchemy ORM 模型出现在 {path}（非 models/ 目录）。"
                    f"ORM 类只能放在 models/ 中以确保数据层隔离。"
                ),
                "fix_hint": f"将 ORM 模型类移动到 backend/models/ 目录，在 routers/services 中通过 import 引用。",
            })

        # BaseModel 出现在非 schemas/ 且非 models/ 的目录
        if has_basemodel_class and dir_name not in ("schemas", "models"):
            findings.append({
                "type": "schema_in_wrong_layer",
                "path": path,
                "detail": (
                    f"Pydantic BaseModel 定义出现在 {path}（非 schemas/ 目录）。"
                    f"数据校验 schema 应集中在 schemas/ 中。"
                ),
                "fix_hint": f"将 Pydantic schema 类移动到 backend/schemas/ 目录。",
            })

    return findings


# =========================================================
# 7. 自清理机制 (v3.2)
#    防止每次 write_code 积累上次的垃圾文件
#    通过 Redis 缓存追踪 AlphaPilot 生成的文件
# =========================================================

def cleanup_previous_generated(redis_client, workspace_root: str, context_final_file_ops: list) -> list:
    """
    从 Redis 缓存读取上次 AlphaPilot 生成的文件列表，生成 delete file_ops 清理它们
    
    Args:
        redis_client: Redis 客户端实例
        workspace_root: 工作区根目录
        context_final_file_ops: 当前的 final_file_ops 列表（新的 delete ops 会追加到此列表）
    
    Returns:
        追加了清理操作后的 final_file_ops 列表
    """
    import hashlib
    cache_key = f"alphapilot:generated:{hashlib.md5(workspace_root.encode()).hexdigest()[:12]}"
    try:
        raw = redis_client.get(cache_key)
        if raw:
            old_paths = json.loads(raw)
            if isinstance(old_paths, list):
                for path in old_paths:
                    if path and isinstance(path, str):
                        context_final_file_ops.append(create_file_op(
                            "delete", path,
                            reason="清理上次 AlphaPilot 生成的临时文件",
                            from_step="workspace"
                        ))
    except Exception:
        pass
    return context_final_file_ops


def track_generated_files(redis_client, workspace_root: str, context_final_file_ops: list):
    """
    将本次 AlphaPilot 生成的文件路径写入 Redis 缓存，供下次清理使用
    
    Args:
        redis_client: Redis 客户端实例
        workspace_root: 工作区根目录
        context_final_file_ops: 当前的 final_file_ops 列表
    """
    import hashlib
    cache_key = f"alphapilot:generated:{hashlib.md5(workspace_root.encode()).hexdigest()[:12]}"
    try:
        paths = [
            op["path"] for op in context_final_file_ops
            if op.get("path") and op.get("op") in ("create", "modify", "test", "doc")
            and not op.get("_internal") and not op.get("op") == "delete"
        ]
        # 始终追加 .alphapilot_generated.mark 到追踪列表
        mark_path = ".alphapilot_generated.mark"
        if mark_path not in paths:
            paths.append(mark_path)
        redis_client.set(cache_key, json.dumps(paths))
    except Exception:
        pass