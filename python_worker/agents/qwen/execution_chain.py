# -*- coding: utf-8 -*-
# execution_chain.py
# ---------------------------------------------------------
# Execution Chain — 执行链定义、过滤、步骤构建
#
# Responsibility:
#   - 根据意图 + prompt 构建执行链
#   - 只读 Skill 执行链过滤
#   - 从执行链生成步骤（与 step_executor 协议对齐）
#
# Extracted from qwen_worker_v2.py (v3.0 执行链架构)
# ---------------------------------------------------------

from ...intent_router import IntentRouter
from ...task_state_contract import (
    STEP_STATE_PENDING,
)

# ── 只读 Skill 过滤 ──────────────────────────────────────────
_WRITE_STEP_TYPES = frozenset({"write", "fix", "doc", "docstring", "refine", "test"})


def build_execution_chain(intent: str, prompt: str = "") -> list:
    return IntentRouter.execution_chain_for(intent, worker="qwen", prompt=prompt)


def filter_read_only_chain(chain: list, selected_skill) -> list:
    if selected_skill is None or not getattr(selected_skill, "read_only", False):
        return chain
    filtered = [s for s in chain if s not in _WRITE_STEP_TYPES]
    if len(filtered) < len(chain):
        removed = [s for s in chain if s in _WRITE_STEP_TYPES]
        print(f"[G1.3] 只读 Skill '{selected_skill.id}'：已从执行链剔除 {removed}")
    return filtered


# ── 步骤模板 ─────────────────────────────────────────────────

STEP_TEMPLATES = {
    "vision_analysis": {
        "type": "vision_analysis",
        "input": {"prompt": "", "images": []},
    },
    "analyze": {
        "type": "analyze",
        "input": {"prompt": ""},
    },
    "plan": {
        "type": "plan",
        "input": {"prompt": "根据分析结果制定执行计划"},
    },
    "setup": {
        "type": "setup",
        "input": {"prompt": "自动处理 DEPENDS 块、生成缺失文件 stub 和项目清单文件"},
    },
    "respond": {
        "type": "respond",
        "input": {"prompt": ""},
    },
    "workspace": {
        "type": "workspace",
        "input": {"prompt": "执行已明确请求的工作区检查和 Python 环境操作"},
    },
    "operate": {
        "type": "operate",
        "input": {"prompt": "执行系统操作：根据用户请求完成 Git 上传/代码统计/Shell 命令/环境检测"},
    },
    "write": {
        "type": "write",
        "input": {"prompt": ""},
    },
    "refine": {
        "type": "refine",
        "input": {"prompt": "根据执行结果优化代码（多文件协议 v3.0）"},
    },
    "test": {
        "type": "test",
        "input": {"prompt": "根据授权执行项目测试验证"},
    },
    "fix": {
        "type": "fix",
        "input": {"prompt": "根据错误信息修复代码"},
    },
    "doc": {
        "type": "doc",
        "input": {"prompt": "为代码生成 Markdown 文档"},
    },
    "docstring": {
        "type": "docstring",
        "input": {"prompt": "为代码添加完整 docstring（多文件）"},
    },
    "profile": {
        "type": "profile",
        "input": {"prompt": "分析代码性能并给出优化建议"},
    },
    "changelog": {
        "type": "changelog",
        "input": {"prompt": "更新项目 CHANGELOG，记录本次变更的文件、功能描述和测试结果"},
    },
}


def create_steps_from_chain(execution_chain: list, prompt: str, persona: str, intent: str = None) -> list:
    steps = []
    for i, step_type in enumerate(execution_chain):
        tmpl = STEP_TEMPLATES.get(step_type)
        if not tmpl:
            continue
        step = tmpl.copy()
        step["id"] = f"step-{i + 1}"
        step["status"] = STEP_STATE_PENDING
        # 将 prompt 注入 prompt 型步骤（plan / workspace / operate / refine / docstring / changelog 除外）
        if step_type not in ("plan", "workspace", "operate", "refine", "docstring", "changelog"):
            step["input"]["prompt"] = prompt
        if intent == "run_tests" and step_type == "test":
            step["input"]["prompt"] = (
                "此步骤由宿主根据用户授权执行已识别的项目测试命令；不得生成测试代码。"
            )
        steps.append(step)
    return steps