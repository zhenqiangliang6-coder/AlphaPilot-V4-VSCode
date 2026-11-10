# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（v3.0 多文件协议版本）
#
# P3: 串行多轮写 — 大任务自动拆分为多个 LLM 子调用，
#     每轮只生成 ≤MAX_FILES_PER_ROUND 个文件，避免 token 瓶颈。
# ---------------------------------------------------------

import re
import os
from ..qwen_api import call_llm, call_qwen_stream, call_qwen_with_persona, call_llm_with_persona
from .utils import extract_code
from .prompts import write_prompt, creative_write_prompt, write_prompt_focused
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3, create_file_op, normalize_fileop_paths


# =========================================================
# P1: 目标语言检测（确定性，零 LLM）
# =========================================================

_KNOWN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".html", ".css",
    ".md", ".yaml", ".yml", ".toml", ".sql", ".sh", ".env",
}


def _detect_target_formats(meta: dict, plan_text: str, user_request: str) -> list:
    """从多个信号源检测任务的目标语言/文件格式

    优先级：
    1. plan 输出中的 EXPECTED_FILE / 文件路径（最准确 —— LLM 已规划好的）
    2. 用户原始请求中的语言关键词（"React"→tsx, "TypeScript"→ts, "FastAPI"→py）
    3. EXECUTION_PROFILE.target_format（LLM 分析阶段的结果）
    4. 默认 ["py"]（向后兼容）

    Returns:
        格式扩展名列表（去重），如 ["py", "ts", "tsx", "json"]
    """
    formats = set()

    # 优先级 1: plan 输出中的文件路径
    file_matches = re.findall(
        r'(?:EXPECTED_FILE|# FILE|路径)[:\s]*([a-zA-Z0-9_\-/.]+\.[a-z]{1,10})',
        plan_text, re.IGNORECASE
    )
    for path in file_matches:
        for ext in _KNOWN_EXTENSIONS:
            if path.endswith(ext):
                formats.add(ext.lstrip("."))

    # 优先级 2: 用户原始请求中的语言/框架关键词
    if user_request:
        req_lower = user_request.lower()
        _keyword_map = {
            "react":       "tsx",
            "vue":         "ts",
            "angular":     "ts",
            "typescript":  "ts",
            "javascript":  "js",
            "node.js":     "js",
            "nodejs":      "js",
            "fastapi":     "py",
            "flask":       "py",
            "django":      "py",
            "python":      "py",
            "frontend":    "tsx",
            "前端":         "tsx",
            "go":          "go",
            "rust":        "rs",
            "java":        "java",
            "html":        "html",
            "css":         "css",
            "docker":      "yaml",
            "ci/cd":       "yaml",
            "github actions": "yaml",
        }
        for keyword, fmt in _keyword_map.items():
            if keyword in req_lower:
                formats.add(fmt)

    # 优先级 3: EXECUTION_PROFILE.target_format
    exec_profile = meta.get("execution_profile", {})
    target_format = exec_profile.get("target_format", "")
    if target_format and target_format in _FORMAT_EXT_TO_SET:
        formats.add(target_format)

    # Fallback 到 "py"
    if not formats:
        return ["py"]

    # 排序保证一致性
    return sorted(formats)


_FORMAT_EXT_TO_SET = {
    ext.lstrip(".") for ext in _KNOWN_EXTENSIONS
}


# ── P3: 串行多轮写 ──────────────────────────────────────────

MAX_FILES_PER_ROUND = 5  # 每轮 LLM 调用最多生成的文件数

_EXPECTED_FILE_RE = re.compile(
    # 匹配 plan 输出中各种格式的文件路径声明：
    #   1) EXPECTED_FILE: path/to/file.py
    #   2) 预期文件: path/to/file.py
    #   3) - **`path/to/file.py`** (LLM 常见 Markdown plan 格式)
    #   4) - **path/to/file.py**
    #   5) - `path/to/file.py`
    #   6) ### path/to/file.py (Markdown heading)
    r'(?:EXPECTED_FILE|预期文件)\s*:\s*([^\n]+)'
    r'|[*]{0,2}`([a-zA-Z0-9_\-/.]+\.\w{1,10})`[*]{0,2}'
    r'|###\s+([a-zA-Z0-9_\-/.]+\.\w{1,10})',
    re.IGNORECASE,
)


def _parse_expected_files(plan_text: str) -> list:
    """从 plan 输出中提取文件路径列表。

    支持多种格式：
      - EXPECTED_FILE: path/to/file.py
      - - **`path/to/file.py`**  (LLM Markdown plan)
      - ### path/to/file.py       (Markdown heading)

    返回去重排序后的文件路径列表。
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
    """将文件列表分组为多轮，按目录层级优先。

    策略：
    1. 按父目录分组（同目录文件放同一轮 → 保持上下文连贯）
    2. 每组不超过 max_per_round 个文件
    3. 排序保证确定性

    Returns:
        [[file1, file2, ...], [file3, file4, ...], ...]
    """
    if max_per_round is None:
        max_per_round = MAX_FILES_PER_ROUND

    if len(files) <= max_per_round:
        return [files]

    # 按目录分组
    dir_groups = {}
    for f in files:
        dirname = os.path.dirname(f) or "."
        dir_groups.setdefault(dirname, []).append(f)

    # 按目录排序后扁平化
    rounds = []
    current_round = []
    for dirname in sorted(dir_groups.keys()):
        for f in sorted(dir_groups[dirname]):
            current_round.append(f)
            if len(current_round) >= max_per_round:
                rounds.append(current_round)
                current_round = []
    if current_round:
        # 如果最后一轮 ≤2 且合并后不超限，合并到前一轮
        if (len(current_round) <= 2 and len(rounds) >= 1
                and len(rounds[-1]) + len(current_round) <= max_per_round):
            rounds[-1].extend(current_round)
        else:
            rounds.append(current_round)

    return rounds


def _build_round_context(prev_rounds_results: list) -> str:
    """从前几轮结果中提取上下文摘要，注入下一轮 prompt。

    只提取文件路径和简要描述，不传递完整代码（节省 token）。
    """
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
    """从完整 plan 中提取只包含当前轮文件的相关描述。

    策略：
    仅保留与当前文件组相关的 plan 行（EXPECTED_FILE 行 +
    前后各 2 行上下文），在保证连贯的同时大幅减少 prompt 长度。
    """
    plan_lines = plan_text.splitlines()
    relevant_indices = set()

    # 找到所有与 group 中文件相关的行
    for fp in file_group:
        fp_escaped = re.escape(fp)
        for i, line in enumerate(plan_lines):
            if re.search(fp_escaped, line, re.IGNORECASE):
                # 包含该行及其上下文（前后各 2 行）
                for offset in range(-2, 3):
                    idx = i + offset
                    if 0 <= idx < len(plan_lines):
                        relevant_indices.add(idx)

    if not relevant_indices:
        # 回退：返回包含文件路径的最小上下文
        return plan_text

    # 构建带上下文间隔的 plan
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
    """判断是否需要多轮写。"""
    files = _parse_expected_files(plan_text)
    return len(files) > MAX_FILES_PER_ROUND


def _execute_single_write_round(
    plan_text: str,
    user_request: str,
    target_formats: list,
    persona_config,
    task_id: str,
    round_idx: int,
    total_rounds: int,
    file_group: list,
    prev_results: list,
) -> str:
    """执行单轮 write LLM 调用。

    Returns:
        LLM 原始输出文本
    """
    focused_plan = _build_focused_plan(plan_text, file_group)
    round_ctx = _build_round_context(prev_results)
    prompt = write_prompt_focused(
        focused_plan, user_request, file_group,
        target_formats, round_ctx, round_idx, total_rounds,
    )

    if task_id:
        stream_chunk(task_id, f"\n🔄 第 {round_idx}/{total_rounds} 轮写入 ({len(file_group)} 文件): "
                     f"{', '.join(f[:30] + ('...' if len(f)>30 else '') for f in file_group)}\n",
            phase="write", channel="reasoning")

    result = ""
    if persona_config:
        for chunk in call_llm_with_persona(prompt, persona_config, use_stream=True):
            result += chunk
            if task_id:
                stream_chunk(task_id, chunk, phase="write", channel="content")
    else:
        for chunk in call_llm_stream(prompt):
            result += chunk
            if task_id:
                stream_chunk(task_id, chunk, phase="write", channel="content")

    return result


# ── 主流程 ─────────────────────────────────────────────────


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（v3.0）：
    - 支持多文件协议 (# FILE: / # TEST: / # DOC: / # META: / # DEPENDS:)
    - 自动生成 file_ops
    - 自动写入 context
    - 支持 persona / intent
    - 支持流式输出
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成代码...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 1. 获取 persona / intent =====
    persona_config = None
    intent = "write_code"

    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        intent = meta.get("intent", "write_code")

        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)

        print(f"🎨 write_step 使用人格: {persona_config['name']}")
        print(f"🧠 意图: {intent}")

    except Exception as e:
        print(f"[WARN] 获取人格失败: {e}")
        persona_config = None

    # ===== 2. 获取 plan 输出（若无 plan 则回退到 analyze 输出 + 用户请求）=====
    plan_outputs = [
        item.get("plan", "")
        for item in context.get("intermediate_results", [])
        if item.get("type") == "plan"
    ]

    # ===== 2.5. 获取用户原始请求 =====
    user_request = meta.get("user_request", "")

    # ⭐ v4.3: 检查 step input 是否已被 worker 注入了视觉分析结果
    _step_input_prompt = step.get("input", {}).get("prompt", "")
    _has_vision_injection = "[图片分析结果]" in _step_input_prompt

    if not plan_outputs:
        # ⭐ v4.3: worker 预注入的视觉上下文优先级最高（高于 analyze 通用输出）
        if _has_vision_injection:
            plan_text = _step_input_prompt
            print(f"[INFO] write_step 使用 worker 注入的视觉上下文 prompt")
        else:
            analyze_outputs = [
                item.get("analysis", "") or item.get("text", "")
                for item in context.get("intermediate_results", [])
                if item.get("type") == "analyze"
            ]
            vision_outputs = [
                item.get("text", "")
                for item in context.get("intermediate_results", [])
                if item.get("type") == "vision_analysis"
            ]
            if vision_outputs:
                plan_text = f"# 图片分析结果\n{vision_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
                print(f"[INFO] write_step 未找到 plan，回退使用 vision_analysis 输出 + 用户请求")
            elif analyze_outputs:
                plan_text = f"# 任务分析\n{analyze_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
                print(f"[INFO] write_step 未找到 plan/vision，回退使用 analyze 输出 + 用户请求")
            else:
                plan_text = user_request or "请根据上下文生成内容"
                print(f"[INFO] write_step 未找到任何分析结果，回退使用用户请求")
    else:
        plan_text = plan_outputs[-1]

    # ===== 2.6 注入工作区路径约束（工业级修复：路径错位）=====
    # LLM 生成 # FILE: 路径时可能把 workspace root 的 basename（项目文件夹名）
    # 误写进路径，导致写盘落到嵌套目录。此处显式告知根目录名，禁止重复前缀。
    # 与下方 normalize_fileop_paths 形成双层防护：提示词预防 + 解析后确定性兜底。
    _ws_root = context.get("meta", {}).get("workspace_path")
    if _ws_root:
        _ws_basename = _ws_root.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if _ws_basename:
            plan_text += (
                "\n\n【工作区路径约束（必须遵守）】\n"
                f"- 项目根目录文件夹名为：{_ws_basename}\n"
                "- 生成 # FILE: / # TEST: / # DOC: / # DELETE: 时，路径必须相对项目根目录。\n"
                f"- 绝对禁止在路径开头重复项目文件夹名（错误示例：{_ws_basename}/backend/models/x.py）。\n"
                "- 正确示例：backend/models/x.py（直接以项目内目录开头，不包含项目名）。\n"
            )

    # ===== 3. 调用 LLM（v3.0 + P3 串行多轮写）=====
    result = ""
    llm_success = False

    _creative_intents = {"creative_writing", "translate", "summarization", "chat", "mentor_explain", "vision_analysis"}

    try:
        if intent in _creative_intents:
            prompt = creative_write_prompt(plan_text, user_request, intent)
            stream_label = "开始生成内容...\n"

            if task_id:
                stream_chunk(task_id, stream_label, phase="write", channel="reasoning")

                if persona_config:
                    for chunk in call_llm_with_persona(prompt, persona_config, use_stream=True):
                        result += chunk
                        stream_chunk(task_id, chunk, phase="write", channel="content")
                else:
                    for chunk in call_llm_stream(prompt):
                        result += chunk
                        stream_chunk(task_id, chunk, phase="write", channel="content")
            else:
                if persona_config:
                    result = call_llm_with_persona(prompt, persona_config, use_stream=False)
                else:
                    result = call_llm(prompt)

        else:
            # P1: 检测目标语言
            target_formats = _detect_target_formats(meta, plan_text, user_request)

            # ═══════════════════════════════════════════════════
            # ⭐ P3 串行多轮写：大任务自动拆分
            # ═══════════════════════════════════════════════════
            needs_multi = _needs_multi_round(plan_text)

            if needs_multi and task_id:
                all_files = _parse_expected_files(plan_text)
                rounds = _group_files_into_rounds(all_files)
                round_results = []

                if task_id:
                    stream_chunk(
                        task_id,
                        f"\n📦 检测到大任务（{len(all_files)} 个文件），"
                        f"自动拆分为 {len(rounds)} 轮串行写入。\n",
                        phase="write", channel="reasoning",
                    )

                for r_idx, file_group in enumerate(rounds, 1):
                    round_result = _execute_single_write_round(
                        plan_text, user_request, target_formats,
                        persona_config, task_id,
                        r_idx, len(rounds), file_group, round_results,
                    )
                    round_results.append(round_result)

                    if not round_result:
                        raise ValueError(f"第 {r_idx}/{len(rounds)} 轮 LLM 返回空")

                # 合并所有轮次的结果
                result = "\n\n".join(round_results)

                if task_id:
                    stream_chunk(
                        task_id,
                        f"\n✅ 多轮写入完成：{len(rounds)} 轮，{len(all_files)} 个文件。\n",
                        phase="write", channel="reasoning",
                    )

            else:
                # 单轮模式（原有逻辑，未改动）
                prompt = write_prompt(plan_text, user_request, target_formats)
                stream_label = "开始生成代码...\n"

                if task_id:
                    stream_chunk(task_id, stream_label, phase="write", channel="reasoning")

                    if persona_config:
                        for chunk in call_llm_with_persona(prompt, persona_config, use_stream=True):
                            result += chunk
                            stream_chunk(task_id, chunk, phase="write", channel="content")
                    else:
                        for chunk in call_llm_stream(prompt):
                            result += chunk
                            stream_chunk(task_id, chunk, phase="write", channel="content")
                else:
                    if persona_config:
                        result = call_llm_with_persona(prompt, persona_config, use_stream=False)
                    else:
                        result = call_llm(prompt)

        if not result:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        result = err
        if task_id:
            stream_chunk(task_id, err, phase="write", channel="reasoning")

    # ===== 4. 提取代码（单文件降级用）=====
    code = extract_code(result, fallback_strategies=True)

    # ===== 5. 解析多文件协议（创意/对话类意图跳过 FileOps）=====
    if intent in _creative_intents:
        print(f"[INFO] 创意/对话类意图 ({intent})，跳过 FileOps 解析，直接输出文本")
        file_ops = []
    else:
        try:
            file_ops = parse_fileops_v3(result)

            if not file_ops:
                print("[WARN] 未检测到多文件协议，降级为单文件模式")

                file_op = create_file_op(
                    action="create",
                    path="main.py",
                    content=code,
                    file_type="file",
                    language="python",
                    reason="单文件降级模式",
                    from_step="write",
                    intent=intent
                )
                file_ops = [file_op]

            print(f"✅ write_step 生成 {len(file_ops)} 个 FileOp")

            # ===== 路径归一化：去掉 LLM 误加的项目名前缀 =====
            # 工业级修复：LLM 可能把 workspace root 的 basename 写进 `# FILE:`，
            # 导致写盘落到嵌套目录（shopflow_ecommerce/shopflow_ecommerce/...）。
            # 在 Worker 真相源做确定性修正，Node 侧仍只忠实执行 FileOps。
            _ws_root = context.get("meta", {}).get("workspace_path")
            if _ws_root:
                file_ops = normalize_fileop_paths(file_ops, _ws_root)

            # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
            if "final_file_ops" not in context:
                context["final_file_ops"] = []
            
            # 追加而非覆盖
            context["final_file_ops"].extend(file_ops)
            
            # 向后兼容：仍然保留 file_ops 字段
            context["file_ops"] = context["final_file_ops"]

            # ===== v3.4: 语法门控 — Python 文件 compile() 校验 =====
            # 在 FileOps 写入 context 后立即对所有 .py 文件执行编译检查。
            # LLM 可能将 Markdown / 全角标点等非代码内容混入 .py 文件
            # （如 test_orders.py 末尾的 ## Summary 文档段），
            # 此门控在写盘前拦截，标记为 _compile_error 供下游修复。
            _compile_errors = []
            for _op in context["final_file_ops"]:
                _path = _op.get("path", "")
                _content = _op.get("content", "")
                if _path.endswith(".py") and _content and not _op.get("_internal"):
                    try:
                        compile(_content, _path, "exec")
                    except SyntaxError as _se:
                        _op["_compile_error"] = str(_se)
                        _op["_needs_fix"] = True
                        _compile_errors.append(f"{_path}: {_se}")
            if _compile_errors:
                print(
                    f"[WARN] write_step: {len(_compile_errors)} Python "
                    f"文件存在语法错误（已标记 _needs_fix）"
                )
                context["meta"].setdefault("_write_compile_errors", []).extend(
                    _compile_errors
                )

        except Exception as e:
            print(f"[ERROR] 解析 FileOps 失败: {e}")
            file_ops = []

    # ===== 6. 写入输出 =====
    step["output"] = {
        "text": result,
        "code": code,
        "llm_success": llm_success,
        "file_ops_count": len(file_ops),
        "file_ops": file_ops
    }

    # ===== 7. 写入上下文 =====
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "code": code,
        "file_ops": file_ops
    })

    # ===== 8. 写入事件流 =====
    events.append(create_event("write_output", {
        "text": result,
        "code": code,
        "file_ops": file_ops
    }))

    # ===== 9. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")