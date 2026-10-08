"""Shared user-facing collaboration modes and execution policy."""

import re
from pathlib import PurePosixPath


MODE_POLICIES = {
    "automatic": {
        "label": "自动 / Automatic",
        "allow_file_changes": True,
        "instruction": (
            "自动模式：遵循 Worker 根据用户目标选择的任务策略。只执行请求范围内的操作；"
            "不得删除文件、运行高风险命令或扩大修改范围，除非获得明确授权。"
        ),
    },
    "teacher": {
        "label": "导师 / Teacher",
        "allow_file_changes": False,
        "instruction": (
            "导师模式：解释原理、给出步骤并可提供示范代码。不要修改或创建项目文件，"
            "不要运行代码、测试或命令，也不要声称已经执行。"
        ),
    },
    "architect": {
        "label": "架构师 / Architect",
        "allow_file_changes": False,
        "instruction": (
            "架构师模式：分析系统边界、模块职责、接口、数据流和权衡。默认只读；"
            "只有用户明确要求保存架构文档时，才可创建或修改 docs/ 下的架构文档；"
            "不得实现应用代码、运行代码或测试。"
        ),
    },
    "pair_programmer": {
        "label": "协作者 / Pair Programmer",
        "allow_file_changes": True,
        "instruction": (
            "协作者模式：先在计划中简要说明准备修改哪些文件及原因，再实施直接相关的最小改动。"
            "避免无关重构，只运行与改动直接相关的检查。"
        ),
    },
    "engineer": {
        "label": "工程师 / Engineer",
        "allow_file_changes": True,
        "instruction": (
            "工程师模式：在当前任务范围内自主检查代码、实施修改、运行相关测试并排查问题；"
            "破坏性或超出范围的操作仍需先确认。"
        ),
    },
    "reviewer": {
        "label": "审查者 / Reviewer",
        "allow_file_changes": False,
        "instruction": (
            "审查者模式：只读审查，不修改或创建文件，默认不运行测试。先按严重程度列出问题，"
            "提供文件和行号及影响；没有发现时明确说明。"
        ),
    },
    "file_manager": {
        "label": "文件管理 / File Manager",
        "allow_file_changes": True,
        "instruction": (
            "文件管理模式：只通过 # DELETE: 相对路径提出用户明确指定的删除候选项。"
            "不得执行删除、shell 命令或其他文件修改；宿主负责校验、回收站和确认。"
            "目标不明确时先询问，不得猜测或扩大范围。"
        ),
    },
    "creative": {
        "label": "创作者 / Creative",
        "allow_file_changes": False,
        "instruction": (
            "创作者模式：直接完成用户要求的创作，不把简单创作变成工程流程；"
            "不要修改项目文件或运行命令，除非用户明确要求。"
        ),
    },
    "navigator": {
        "label": "导航员 / Navigator",
        "allow_file_changes": False,
        "instruction": (
            "导航员模式：只回答运行方式、负责文件位置和项目结构等导航问题。"
            "不要修改文件、运行命令或代替用户执行操作。"
        ),
    },
}

READ_ONLY_MODES = {
    mode for mode, policy in MODE_POLICIES.items()
    if not policy["allow_file_changes"]
}

MODE_EXECUTION_CHAINS = {
    "architect": ["analyze", "plan", "write"],
    "teacher": ["analyze", "plan", "write"],
    "pair_programmer": ["analyze", "plan", "write", "test"],
    "reviewer": ["analyze", "plan", "write"],
    "creative": ["analyze", "plan", "write"],
    "navigator": ["analyze", "plan", "write"],
}


def normalize_collaboration_mode(mode):
    if isinstance(mode, str) and mode in MODE_POLICIES:
        return mode
    return "automatic"

def infer_collaboration_mode(intent):
    if intent == "architecture":
        return "architect"
    if intent in {"mentor_explain", "explain_code", "chat", "analysis"}:
        return "teacher"
    if intent == "code_review":
        return "reviewer"
    if intent == "delete_files":
        return "file_manager"
    if intent == "creative_writing":
        return "creative"
    return "engineer"

def prepare_collaboration_mode(mode, prompt, default_chain, preserve_chain=False, intent=None):
    """Return the normalized mode, an instruction-bearing prompt, and its chain."""
    automatic = mode is None or mode == "automatic"
    mode = infer_collaboration_mode(intent) if automatic else normalize_collaboration_mode(mode)
    policy = MODE_POLICIES[mode]
    chain = list(default_chain)

    if not automatic and not preserve_chain and mode in MODE_EXECUTION_CHAINS:
        chain = list(MODE_EXECUTION_CHAINS[mode])

    mode_prompt = f"[协作模式：{policy['label']}。以下模式规则优先于通用执行步骤。]\n{policy['instruction']}\n\n用户请求：\n{prompt}"
    return mode, mode_prompt, chain


def apply_mode_to_steps(steps, mode):
    instruction = MODE_POLICIES[normalize_collaboration_mode(mode)]["instruction"]
    for step in steps:
        step_input = step.get("input")
        if isinstance(step_input, dict) and step_input.get("prompt"):
            step_input["prompt"] = f"{instruction}\n\n{step_input['prompt']}"
    return steps


def apply_mode_to_persona(persona_config, mode):
    updated = dict(persona_config)
    existing_prompt = updated.get("system_prompt", "")
    instruction = MODE_POLICIES[normalize_collaboration_mode(mode)]["instruction"]
    updated["system_prompt"] = f"{instruction}\n\n{existing_prompt}"
    return updated


def enforce_file_operation_policy(context, mode, steps=None, events=None):
    mode = normalize_collaboration_mode(mode)
    meta = context.setdefault("meta", {})
    meta["collaboration_mode"] = mode
    if mode == "architect":
        allowed = (
            meta.get("intent") == "architecture"
            and _requests_architecture_document(meta.get("user_request", ""))
        )
        meta["file_changes_allowed"] = allowed
        if allowed:
            _restrict_architecture_file_operations(context)
            _restrict_architecture_file_operations(steps)
            _restrict_architecture_file_operations(events)
        else:
            _clear_file_operations(context)
            _clear_file_operations(steps)
            _clear_file_operations(events)
        return context

    meta["file_changes_allowed"] = MODE_POLICIES[mode]["allow_file_changes"]
    if mode in READ_ONLY_MODES:
        _clear_file_operations(context)
        _clear_file_operations(steps)
        _clear_file_operations(events)

    return context


def _clear_file_operations(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"file_ops", "final_file_ops"}:
                value[key] = []
            else:
                _clear_file_operations(child)
    elif isinstance(value, list):
        for child in value:
            _clear_file_operations(child)


def _requests_architecture_document(prompt):
    if not isinstance(prompt, str):
        return False
    has_architecture_document = re.search(
        r"(?i)(?:架构(?:设计)?文档|architecture document|"
        r"docs[/\\][\w./\\-]*(?:architecture|架构)[\w./\\-]*\.(?:md|mmd|puml))",
        prompt,
    )
    if not has_architecture_document:
        return False

    for action in re.finditer(
        r"(?i)保存|写入|生成|创建|输出|save|write|generate|create",
        prompt,
    ):
        preceding = prompt[max(0, action.start() - 24):action.start()]
        if re.search(
            r"(?i)(?:不要|无需|不需要|不必|不得|禁止|勿|do not|don't).{0,16}$",
            preceding,
        ):
            continue
        return True
    return False


def _is_architecture_document_operation(operation):
    if not isinstance(operation, dict):
        return False
    raw_path = operation.get("path")
    if not isinstance(raw_path, str):
        return False
    normalized = raw_path.replace("\\", "/").strip()
    if re.match(r"^[A-Za-z]:", normalized):
        return False
    parts = PurePosixPath(normalized.lstrip("/")).parts
    if not parts or parts[0] != "docs" or ".." in parts:
        return False
    filename = parts[-1].lower()
    suffix = PurePosixPath(filename).suffix
    stem = filename[:-len(suffix)] if suffix else filename
    return suffix in {".md", ".mmd", ".puml"} and (
        "architecture" in stem or "架构" in stem
    )


def _restrict_architecture_file_operations(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"file_ops", "final_file_ops"}:
                value[key] = [
                    operation
                    for operation in child
                    if _is_architecture_document_operation(operation)
                ] if isinstance(child, list) else []
            else:
                _restrict_architecture_file_operations(child)
    elif isinstance(value, list):
        for child in value:
            _restrict_architecture_file_operations(child)