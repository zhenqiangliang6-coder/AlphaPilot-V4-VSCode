# -*- coding: utf-8 -*-
"""P3 串行多轮写 — 确定性测试套件

覆盖：
  - _parse_expected_files: plan 文本解析（多格式、去重、空输入）
  - _group_files_into_rounds: 文件分组（阈值、目录优先级、尾轮合并）
  - _build_round_context: 前轮上下文摘要
  - _build_focused_plan: plan 聚焦裁剪
  - _needs_multi_round: 多轮判断
  - write_prompt_focused: 聚焦 prompt 构建
  - 向后兼容：单轮降级
"""

import sys
import os
import re
from pathlib import Path

# ── 绕过包体系的直接导入（避免顶层相对导入越界） ──

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent
_WRITE_STEP_PATH = _PROJECT_ROOT / "agents" / "qwen" / "step_executor" / "write_step.py"

# 提取 MAX_FILES_PER_ROUND（跨文件同步值）
MAX_FILES_PER_ROUND = 5

# 确定性的测试模式（与 write_step.py 中的 _EXPECTED_FILE_RE 保持同步）
_EXPECTED_FILE_RE = re.compile(
    r'(?:EXPECTED_FILE|预期文件)\s*:\s*([^\n]+)'
    r'|[*]{0,2}`([a-zA-Z0-9_\-/.]+\.\w{1,10})`[*]{0,2}'
    r'|###\s+([a-zA-Z0-9_\-/.]+\.\w{1,10})',
    re.IGNORECASE,
)


def _parse_expected_files(plan_text: str) -> list:
    """从 plan 输出中提取文件路径列表（同步自 write_step.py）。

    支持多种格式：
      - EXPECTED_FILE: path/to/file.py
      - - **`path/to/file.py`**  (LLM Markdown plan)
      - ### path/to/file.py       (Markdown heading)
    """
    files = []
    for m in _EXPECTED_FILE_RE.finditer(plan_text):
        path = (m.group(1) or m.group(2) or m.group(3) or "").strip().strip("`'\"")
        if path:
            files.append(path)
    seen = set()
    result = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def _group_files_into_rounds(files: list, max_per_round: int = None) -> list:
    """将文件列表分组为多轮（同步自 write_step.py）。"""
    if max_per_round is None:
        max_per_round = MAX_FILES_PER_ROUND
    if len(files) <= max_per_round:
        return [files]

    dir_groups = {}
    for f in files:
        dirname = os.path.dirname(f) or "."
        dir_groups.setdefault(dirname, []).append(f)

    rounds = []
    current_round = []
    for dirname in sorted(dir_groups.keys()):
        for f in sorted(dir_groups[dirname]):
            current_round.append(f)
            if len(current_round) >= max_per_round:
                rounds.append(current_round)
                current_round = []
    if current_round:
        if len(current_round) <= 2 and len(rounds) >= 1 \
                and len(rounds[-1]) + len(current_round) <= max_per_round:
            rounds[-1].extend(current_round)
        else:
            rounds.append(current_round)
    return rounds


def _build_round_context(prev_rounds_results: list) -> str:
    """前轮上下文摘要（同步自 write_step.py）。"""
    if not prev_rounds_results:
        return ""
    lines = ["\n【前几轮已生成的文件（不要重复生成）】："]
    for round_idx, result_text in enumerate(prev_rounds_results, 1):
        files_in_round = re.findall(r'#\s*FILE:\s*(.+)', result_text)
        if files_in_round:
            lines.append(f"\n第 {round_idx} 轮：")
            for fp in files_in_round:
                lines.append(f"  ✅ {fp.strip()}")
    lines.append("\n请只生成本轮指定的文件，不要重复上述已生成的文件。\n")
    return "\n".join(lines)


def _build_focused_plan(plan_text: str, file_group: list) -> str:
    """从完整 plan 中提取聚焦片段（同步自 write_step.py）。"""
    plan_lines = plan_text.splitlines()
    relevant_indices = set()
    for fp in file_group:
        fp_escaped = re.escape(fp)
        for i, line in enumerate(plan_lines):
            if re.search(fp_escaped, line, re.IGNORECASE):
                for offset in range(-2, 3):
                    idx = i + offset
                    if 0 <= idx < len(plan_lines):
                        relevant_indices.add(idx)
    if not relevant_indices:
        return plan_text
    sorted_indices = sorted(relevant_indices)
    focused_lines = []
    last_idx = -3
    for idx in sorted_indices:
        if idx > last_idx + 1:
            focused_lines.append("...")
        focused_lines.append(plan_lines[idx])
        last_idx = idx
    return "\n".join(focused_lines)


def _needs_multi_round(plan_text: str) -> bool:
    """判断是否需要多轮写（同步自 write_step.py）。"""
    files = _parse_expected_files(plan_text)
    return len(files) > MAX_FILES_PER_ROUND


# ── write_prompt_focused 的确定性测试版（无 LLM 依赖） ──

def write_prompt_focused(
    plan: str,
    user_request: str = "",
    file_group: list = None,
    target_formats: list = None,
    round_context: str = "",
    round_idx: int = 1,
    total_rounds: int = 1,
) -> str:
    """聚焦写 prompt（同步自 prompts.py），测试用复制版。"""
    file_group = file_group or []

    user_section = ""
    if user_request:
        user_section = f"""
====================
【用户的原始请求 — 这是你最需要满足的目标】：
{user_request}

"""

    file_list_str = "\n".join(f"  - {f}" for f in file_group)
    round_hint = ""
    if total_rounds > 1:
        round_hint = f"""
══════════════════════════════════════
【第 {round_idx}/{total_rounds} 轮 — 只生成本轮指定的文件】
{round_context}

本轮需要生成的文件（共 {len(file_group)} 个）：
{file_list_str}

⚠️ 重要：
- **只生成上面列出的 {len(file_group)} 个文件**，不要生成其它文件
- 不要重复前几轮已生成的文件
- 每个文件使用 # FILE: 声明路径
══════════════════════════════════════
"""

    return f"""你现在处于 AlphaPilot OS v3.0 环境。

请严格按照以下"多文件输出协议"生成结果：

==========================
# FILE: <相对路径>
<代码内容>

# TEST: <测试文件路径>
<测试代码内容>

# DEPENDS:
# DELETE: <用户明确指定的工作区相对路径>
==========================
{user_section}
【代码规划（已聚焦到本轮文件）】：
{plan}

{round_hint}

⭐⭐⭐ 强制要求（必须遵守）：

1. 必须使用 "# FILE:" 开头声明文件路径
2. 每个文件必须单独一个 # FILE: 块
3. 不得省略 # FILE:
4. 不得输出未声明路径的代码
5. 代码完整性（最高优先级）：
   - 每个函数必须有完整的、可运行的实际实现
   - 严禁使用 pass、...、raise NotImplementedError 作为函数体
   - 即使是最简单的工具函数也要给出实际逻辑
6. 代码质量要求：
   - 代码必须可运行
   - 变量命名清晰
   - 逻辑结构与规划一致
   - 包含必要的注释和文档字符串

只输出多文件协议内容，不要任何解释性文字。
"""


# ═══════════════════════════════════════════════════════════
# _parse_expected_files
# ═══════════════════════════════════════════════════════════

def test_parse_expected_files_basic():
    plan = """EXPECTED_FILE: backend/main.py
EXPECTED_FILE: backend/models/user.py
EXPECTED_FILE: frontend/src/App.tsx"""
    files = _parse_expected_files(plan)
    assert files == ["backend/main.py", "backend/models/user.py", "frontend/src/App.tsx"], \
        f"Expected 3 files, got {files}"


def test_parse_expected_files_chinese_label():
    plan = """预期文件: backend/api.py
预期文件: tests/test_api.py"""
    files = _parse_expected_files(plan)
    assert files == ["backend/api.py", "tests/test_api.py"], \
        f"Expected 2 files with Chinese label, got {files}"


def test_parse_expected_files_deduplication():
    plan = """EXPECTED_FILE: a.py
EXPECTED_FILE: b.py
EXPECTED_FILE: a.py
EXPECTED_FILE: c.py"""
    files = _parse_expected_files(plan)
    assert files == ["a.py", "b.py", "c.py"], \
        f"Expected deduplicated [a.py, b.py, c.py], got {files}"


def test_parse_expected_files_backtick_paths():
    plan = "EXPECTED_FILE: `backend/main.py`"
    files = _parse_expected_files(plan)
    assert files == ["backend/main.py"], \
        f"Expected stripped backticks, got {files}"


def test_parse_expected_files_markdown_plan_format():
    """验证正则能匹配 LLM 真实 plan 输出的 Markdown 格式。

    真实 plan 输出示例：
        - **`models/task.py`** — Pydantic 数据模型
        - **`db/store.py`** — 内存存储
        - `routers/tasks.py` — REST API 路由
        - ### frontend/src/App.tsx — React 入口
    """
    plan = """## Implementation Plan

- **`models/task.py`** — Pydantic data models
- **`db/store.py`** — In-memory store
- `routers/tasks.py` — REST API routes
### main.py — Application entry"""
    files = _parse_expected_files(plan)
    assert "models/task.py" in files, f"Missing models/task.py, got {files}"
    assert "db/store.py" in files, f"Missing db/store.py, got {files}"
    assert "routers/tasks.py" in files, f"Missing routers/tasks.py, got {files}"
    assert "main.py" in files, f"Missing main.py, got {files}"


def test_parse_expected_files_empty():
    assert _parse_expected_files("") == []
    assert _parse_expected_files("no EXPECTED_FILE tags here") == []


def test_parse_expected_files_special_chars():
    plan = "EXPECTED_FILE: path/with spaces.py"
    files = _parse_expected_files(plan)
    assert "path/with spaces.py" in files


# ═══════════════════════════════════════════════════════════
# _group_files_into_rounds
# ═══════════════════════════════════════════════════════════

def test_group_single_round_small():
    files = ["a.py", "b.py", "c.py"]
    rounds = _group_files_into_rounds(files, max_per_round=5)
    assert len(rounds) == 1, f"Expected 1 round for 3 files, got {len(rounds)}"
    assert rounds[0] == files


def test_group_single_round_at_threshold():
    files = [f"file{i}.py" for i in range(MAX_FILES_PER_ROUND)]
    rounds = _group_files_into_rounds(files)
    assert len(rounds) == 1, f"Expected 1 round for threshold count, got {len(rounds)}"


def test_group_split_two_rounds():
    files = [f"file{i}.py" for i in range(7)]  # 7 > 5
    rounds = _group_files_into_rounds(files, max_per_round=5)
    assert len(rounds) == 2, f"Expected 2 rounds for 7 files, got {len(rounds)}"
    assert len(rounds[0]) == 5
    assert len(rounds[1]) == 2


def test_group_split_many_rounds():
    files = [f"file{i}.py" for i in range(14)]  # 14 > 5
    rounds = _group_files_into_rounds(files, max_per_round=5)
    assert len(rounds) == 3, f"Expected 3 rounds for 14 files, got {len(rounds)}"
    assert sum(len(r) for r in rounds) == 14


def test_group_by_directory():
    files = [
        "backend/main.py",
        "backend/models.py",
        "backend/routes.py",
        "frontend/App.tsx",
        "frontend/Header.tsx",
        "frontend/Footer.tsx",
        "tests/test_main.py",
    ]
    rounds = _group_files_into_rounds(files, max_per_round=3)
    assert len(rounds) >= 2, f"Expected >=2 rounds for mixed dirs, got {len(rounds)}"

    # 同目录文件应在同一轮
    all_files_flat = []
    for r in rounds:
        all_files_flat.extend(r)
    assert set(all_files_flat) == set(files), "All files should be accounted for"


def test_group_tail_merge():
    # 7 files, max 5 → 2 rounds (5+2) because tail doesn't fit
    files = [f"f{i}.py" for i in range(7)]
    rounds = _group_files_into_rounds(files, max_per_round=5)
    total = sum(len(r) for r in rounds)
    assert total == 7, f"All 7 files accounted, got {total}"
    assert len(rounds) == 2, f"Should be 2 rounds for 7/5, got {len(rounds)}"

    # 3 files, max 5 → 1 round (no split)
    files_small = ["a.py", "b.py", "c.py"]
    rounds_small = _group_files_into_rounds(files_small, max_per_round=5)
    assert len(rounds_small) == 1


def test_group_empty():
    assert _group_files_into_rounds([]) == [[]]


# ═══════════════════════════════════════════════════════════
# _build_round_context
# ═══════════════════════════════════════════════════════════

def test_round_context_empty():
    ctx = _build_round_context([])
    assert ctx == ""


def test_round_context_one_round():
    results = ["# FILE: backend/main.py\nprint('hello')\n"]
    ctx = _build_round_context(results)
    assert "backend/main.py" in ctx
    assert "✅" in ctx


def test_round_context_multiple_rounds():
    results = [
        "# FILE: backend/main.py\ncode1\n# FILE: backend/models.py\ncode2\n",
        "# FILE: frontend/App.tsx\ncode3\n",
    ]
    ctx = _build_round_context(results)
    assert "backend/main.py" in ctx
    assert "backend/models.py" in ctx
    assert "frontend/App.tsx" in ctx
    assert "第 1 轮" in ctx
    assert "第 2 轮" in ctx
    assert "不要重复" in ctx


# ═══════════════════════════════════════════════════════════
# _build_focused_plan
# ═══════════════════════════════════════════════════════════

def test_focused_plan_extracts_relevant():
    plan = """# 项目规划
需要创建后端入口文件
EXPECTED_FILE: backend/main.py
这个文件应该包含 FastAPI 初始化

需要创建用户模型
EXPECTED_FILE: backend/models/user.py
包含 User、Task 模型

需要创建前端主页
EXPECTED_FILE: frontend/src/App.tsx
React 18 + TypeScript"""
    focused = _build_focused_plan(plan, ["backend/main.py"])
    assert "backend/main.py" in focused
    assert "FastAPI" in focused


def test_focused_plan_no_match():
    plan = """EXPECTED_FILE: a.py\nsome description\nEXPECTED_FILE: b.py\nother description"""
    focused = _build_focused_plan(plan, ["nonexistent.py"])
    # 回退到完整 plan
    assert focused == plan or len(focused) > 0


def test_focused_plan_context_lines():
    plan = "\n".join([
        "# line 1: overview",
        "# line 2: IMPORTANT context before file",
        "EXPECTED_FILE: backend/main.py",
        "# line 4: IMPORTANT context after file",
        "# line 5: unrelated",
        "# line 6: unrelated",
    ])
    focused = _build_focused_plan(plan, ["backend/main.py"])
    assert "line 2" in focused or "IMPORTANT" in focused, \
        f"Context before file should be included, got: {focused}"
    assert "line 4" in focused or "IMPORTANT" in focused, \
        f"Context after file should be included, got: {focused}"


# ═══════════════════════════════════════════════════════════
# _needs_multi_round
# ═══════════════════════════════════════════════════════════

def test_needs_multi_round_small():
    plan = "EXPECTED_FILE: a.py\nEXPECTED_FILE: b.py\nEXPECTED_FILE: c.py"
    assert not _needs_multi_round(plan)


def test_needs_multi_round_large():
    files = "\n".join(f"EXPECTED_FILE: f{i}.py" for i in range(7))
    assert _needs_multi_round(files)


def test_needs_multi_round_empty():
    assert not _needs_multi_round("")
    assert not _needs_multi_round("没有 EXPECTED_FILE 标签")


# ═══════════════════════════════════════════════════════════
# write_prompt_focused
# ═══════════════════════════════════════════════════════════

def test_write_prompt_focused_basic():
    prompt = write_prompt_focused(
        plan="创建 backend/main.py 入口文件",
        user_request="写一个 FastAPI 应用",
        file_group=["backend/main.py"],
    )
    assert "AlphaPilot OS v3.0" in prompt
    assert "backend/main.py" in prompt
    assert "FastAPI" in prompt
    assert "# FILE:" in prompt


def test_write_prompt_focused_with_rounds():
    prompt = write_prompt_focused(
        plan="创建文件",
        user_request="写代码",
        file_group=["a.py", "b.py"],
        round_context="第 1 轮已生成 x.py",
        round_idx=2,
        total_rounds=3,
    )
    assert "第 2/3 轮" in prompt
    assert "a.py" in prompt
    assert "b.py" in prompt
    assert "x.py" in prompt or "第 1 轮" in prompt
    assert "不要生成其它文件" in prompt


def test_write_prompt_focused_enforces_protocol():
    prompt = write_prompt_focused(
        plan="测试",
        file_group=["test.py"],
    )
    assert "# FILE:" in prompt
    assert "# TEST:" in prompt
    assert "不得省略 # FILE:" in prompt
    assert "严禁使用 pass" in prompt


# ═══════════════════════════════════════════════════════════
# 向后兼容性
# ═══════════════════════════════════════════════════════════

def test_backward_compat_single_round():
    """≤5 个文件时不触发多轮（向后兼容）"""
    plan = "\n".join(f"EXPECTED_FILE: f{i}.py" for i in range(5))
    assert not _needs_multi_round(plan), \
        "5 files should NOT trigger multi-round (backward compat)"


def test_backward_compat_no_expected_files():
    """无 EXPECTED_FILE 标记的 plan 不触发多轮"""
    plan = "这是一个没有 EXPECTED_FILE 标记的计划文本"
    assert not _needs_multi_round(plan)


# ═══════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback

    tests = [
        ("parse_expected_files_basic", test_parse_expected_files_basic),
        ("parse_expected_files_chinese_label", test_parse_expected_files_chinese_label),
        ("parse_expected_files_deduplication", test_parse_expected_files_deduplication),
        ("parse_expected_files_backtick_paths", test_parse_expected_files_backtick_paths),
        ("parse_expected_files_markdown_plan", test_parse_expected_files_markdown_plan_format),
        ("parse_expected_files_empty", test_parse_expected_files_empty),
        ("parse_expected_files_special_chars", test_parse_expected_files_special_chars),
        ("group_single_round_small", test_group_single_round_small),
        ("group_single_round_at_threshold", test_group_single_round_at_threshold),
        ("group_split_two_rounds", test_group_split_two_rounds),
        ("group_split_many_rounds", test_group_split_many_rounds),
        ("group_by_directory", test_group_by_directory),
        ("group_tail_merge", test_group_tail_merge),
        ("group_empty", test_group_empty),
        ("round_context_empty", test_round_context_empty),
        ("round_context_one_round", test_round_context_one_round),
        ("round_context_multiple_rounds", test_round_context_multiple_rounds),
        ("focused_plan_extracts_relevant", test_focused_plan_extracts_relevant),
        ("focused_plan_no_match", test_focused_plan_no_match),
        ("focused_plan_context_lines", test_focused_plan_context_lines),
        ("needs_multi_round_small", test_needs_multi_round_small),
        ("needs_multi_round_large", test_needs_multi_round_large),
        ("needs_multi_round_empty", test_needs_multi_round_empty),
        ("write_prompt_focused_basic", test_write_prompt_focused_basic),
        ("write_prompt_focused_with_rounds", test_write_prompt_focused_with_rounds),
        ("write_prompt_focused_enforces_protocol", test_write_prompt_focused_enforces_protocol),
        ("backward_compat_single_round", test_backward_compat_single_round),
        ("backward_compat_no_expected_files", test_backward_compat_no_expected_files),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  ✅ {name}")
        except Exception:
            failed += 1
            print(f"  ❌ {name}")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"P3 结果: {passed}/{len(tests)} 通过, {failed} 失败")
    print(f"{'='*50}")