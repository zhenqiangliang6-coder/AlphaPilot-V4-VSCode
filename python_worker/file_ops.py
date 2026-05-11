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

FILE_PATTERN = re.compile(r"^#\s*FILE:\s*(.+)$", re.MULTILINE)
TEST_PATTERN = re.compile(r"^#\s*TEST:\s*(.+)$", re.MULTILINE)
DOC_PATTERN = re.compile(r"^#\s*DOC:\s*(.+)$", re.MULTILINE)
META_PATTERN = re.compile(r"^#\s*META:\s*(.+)$", re.MULTILINE)
DEPENDS_PATTERN = re.compile(r"^#\s*DEPENDS:\s*(.+)$", re.MULTILINE)


def contains_multi_file_protocol(text: str) -> bool:
    """
    判断是否包含多文件协议
    """
    return (
        "# FILE:" in text
        or "# TEST:" in text
        or "# DOC:" in text
        or "# META:" in text
        or "# DEPENDS:" in text
    )


def parse_fileops_v3(text: str):
    """
    将 LLM 输出解析为 file_ops 列表
    
    ⭐ v3.1 修复：所有文件操作统一使用 create/modify/delete，通过 reason 和 from_step 区分用途
    """
    file_ops = []

    # 1) FILE - 主代码文件
    for match in FILE_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        file_ops.append(create_file_op("create", path, content, reason="主代码文件", from_step="write"))

    # 2) TEST - 测试文件（使用 create 操作，标注来源）
    for match in TEST_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        file_ops.append(create_file_op("create", path, content, reason="测试文件", from_step="test"))

    # 3) DOC - 文档文件（使用 create 操作，标注来源）
    for match in DOC_PATTERN.finditer(text):
        path = match.group(1).strip()
        content = extract_block(text, match.end())
        file_ops.append(create_file_op("create", path, content, reason="文档文件", from_step="doc"))

    # 4) META - 元数据（保留特殊操作类型，但标记为内部使用）
    for match in META_PATTERN.finditer(text):
        data = parse_meta(match.group(1))
        meta_op = create_file_op("meta", data=data)
        meta_op["_internal"] = True  # 标记为内部元数据，不推送给前端
        file_ops.append(meta_op)

    # 5) DEPENDS - 依赖声明（保留特殊操作类型，但标记为内部使用）
    for match in DEPENDS_PATTERN.finditer(text):
        deps = [d.strip() for d in match.group(1).split(",")]
        depends_op = create_file_op("depends", data={"files": deps})
        depends_op["_internal"] = True  # 标记为内部依赖信息
        file_ops.append(depends_op)

    return file_ops


# =========================================================
# 3. 工具函数
# =========================================================

def extract_block(text: str, start_pos: int) -> str:
    """
    提取 FILE/TEST/DOC 后面的代码块
    """
    lines = text[start_pos:].splitlines()
    collected = []

    for line in lines:
        if line.startswith("# FILE:") or line.startswith("# TEST:") or line.startswith("# DOC:"):
            break
        collected.append(line)

    return "\n".join(collected).strip()


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
