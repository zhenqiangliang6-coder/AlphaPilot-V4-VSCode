"""
G1 会话状态增量契约 (Session State Delta Contract)

冻结日期: 2026-10-27
用途: 定义临时会话记忆的数据结构、证据分级、注入规则和失效策略。
     本模块是记忆系统的「契约层」，不依赖任何存储实现。
     所有对 temp_session_memory 的读写必须遵守本契约。

核心原则:
    1. 状态优先于原文 —— 保存任务事实/决策/变化，不重复注入历史对话
    2. 证据优先于模型陈述 —— 生成/尝试/执行/验证/成功 必须明确区分
    3. 相关性优先于最近性 —— 不能仅凭最近三轮或关键词决定注入
    4. Worker 状态优先于记忆摘要 —— 记忆只辅助理解，不成为第二个任务状态真相源
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ============================================================
# 证据分级 (Evidence Tier)
# ============================================================

class EvidenceTier(str, Enum):
    """
    每一条 attempted_action / verified_change 都携带证据等级。

    设计原理:
    - 生成脚本 ≠ 执行了操作 ≠ 操作成功
    - 记忆系统不能把模型的陈述自动升级为系统事实
    """

    STATED = "stated"
    """模型声明要做某事，但无任何执行证据。例如: "我将为你创建一个脚本" """

    GENERATED = "generated"
    """已生成文件/脚本/计划，但未执行。例如: 写出了 code_counter.py """

    ATTEMPTED = "attempted"
    """尝试执行但结果未知。例如: 调用了 git push 但未确认远端是否成功 """

    EXECUTED = "executed"
    """已执行并获得系统级输出。例如: 运行了 pytest 并获得测试报告 """

    VERIFIED = "verified"
    """执行结果经过独立验证。例如: 代码行数统计后与 cloc 交叉验证一致 """

    SUCCEEDED = "succeeded"
    """操作完全成功，远端/系统确认。例如: GitHub 远端确认仓库已创建并含文件列表 """


# ============================================================
# 行动类型 (ActionType)
# ============================================================

class ActionType(str, Enum):
    """任务对工作区的操作类型"""
    CREATED_FILES = "created_files"
    MODIFIED_FILES = "modified_files"
    DELETED_FILES = "deleted_files"
    READ_FILES = "read_files"
    EXECUTED_COMMAND = "executed_command"
    ANALYZED_PROJECT = "analyzed_project"
    EXTERNAL_OPERATION = "external_operation"


# ============================================================
# 核心数据结构
# ============================================================

@dataclass
class ActionRecord:
    """单条操作记录（attempted_action / verified_change 的载体）"""
    description: str
    """操作的人类可读描述。不超过 200 字符。"""
    evidence_tier: EvidenceTier
    """此操作的证据等级。"""
    actionable_files: List[str] = field(default_factory=list)
    """涉及的文件路径（相对于工作区根目录，最多 5 个）。"""

    def to_compact(self) -> str:
        """压缩为单行摘要，约 30-80 字符"""
        tier_mark = {
            EvidenceTier.STATED: "?",
            EvidenceTier.GENERATED: "~",
            EvidenceTier.ATTEMPTED: "→",
            EvidenceTier.EXECUTED: "✓",
            EvidenceTier.VERIFIED: "✓✓",
            EvidenceTier.SUCCEEDED: "✓✓✓",
        }
        mark = tier_mark.get(self.evidence_tier, "?")
        files = f" ({', '.join(self.actionable_files[:3])})" if self.actionable_files else ""
        return f"{mark} {self.description}{files}"


@dataclass
class SessionStateDelta:
    """
    单轮任务的「状态增量」—— 不是对话内容，是工作区变化。

    每个字段的设计意图:
    - attempted_actions: 尝试做了什么（不代表成功）
    - verified_changes: 已经通过证据确认的变化
    - key_facts: 经过确认、且对后续任务有帮助的事实
    - unresolved_items: 未完成事项、失败事项或等待确认的事项
    - evidence_refs: 指向可追溯证据的引用（文件路径/事件ID）
    """

    task_id: str
    """任务唯一标识"""

    workspace_id: str
    """规范化的工作区标识（不能只依赖用户说的"这个项目"）"""

    intent: str
    """意图类型: write_code / analysis / execute_operation / fix_code / ..."""

    attempted_actions: List[ActionRecord] = field(default_factory=list)
    """尝试执行的操作列表"""

    verified_changes: List[ActionRecord] = field(default_factory=list)
    """已验证确认的变化列表"""

    key_facts: List[str] = field(default_factory=list)
    """经过确认、对后续任务有帮助的事实。每条不超过 200 字符，最多 3 条。"""

    unresolved_items: List[str] = field(default_factory=list)
    """未完成事项、失败事项。每条不超过 200 字符。"""

    evidence_refs: List[str] = field(default_factory=list)
    """指向可追溯证据的引用（文件路径/事件ID/任务日志引用）。最多 5 条。"""

    outcome: str = "unknown"
    """任务结果: success / partial / failed"""

    errors: List[str] = field(default_factory=list)
    """如果失败，记录错误摘要（不超过 3 条，每条不超过 200 字符）"""

    # ============================================================
    # 验证规则
    # ============================================================

    def validate(self) -> List[str]:
        """自检：返回违反契约的规则列表。空列表表示合法。"""
        issues = []

        if not self.task_id:
            issues.append("task_id 不能为空")
        if not self.workspace_id:
            issues.append("workspace_id 不能为空")
        if not self.intent:
            issues.append("intent 不能为空")

        if len(self.key_facts) > 3:
            issues.append(f"key_facts 最多 3 条，当前 {len(self.key_facts)} 条")
        if len(self.evidence_refs) > 5:
            issues.append(f"evidence_refs 最多 5 条，当前 {len(self.evidence_refs)} 条")
        if len(self.errors) > 3:
            issues.append(f"errors 最多 3 条，当前 {len(self.errors)} 条")

        for i, fact in enumerate(self.key_facts):
            if len(fact) > 300:
                issues.append(f"key_facts[{i}] 超过 300 字符限制")
        for i, item in enumerate(self.unresolved_items):
            if len(item) > 300:
                issues.append(f"unresolved_items[{i}] 超过 300 字符限制")

        # 检查 evidence_refs 格式
        for i, ref in enumerate(self.evidence_refs):
            if not isinstance(ref, str) or not ref.strip():
                issues.append(f"evidence_refs[{i}] 为空或无效格式")

        return issues

    # ============================================================
    # 注入预算计算
    # ============================================================

    def estimate_tokens(self) -> int:
        """
        估算此 delta 注入 LLM 时的 token 消耗。
        使用保守估算: 1 token ≈ 4 中文字符 ≈ 1 英文单词
        """
        return max(1, len(self._raw_text()) // 3)

    def _raw_text(self) -> str:
        """计算 token 时用的原始文本（不触发预算裁剪）"""
        parts = []
        outcome_icon = {"success": "✓", "partial": "⚠", "failed": "✗"}.get(self.outcome, "?")
        parts.append(f"[{self.intent}] {outcome_icon}")
        for change in self.verified_changes[:3]:
            parts.append(change.to_compact())
        for fact in self.key_facts[:2]:
            parts.append(f"· {fact[:200]}")
        if self.unresolved_items:
            parts.append(f"⚠ 未完成: {'; '.join(self.unresolved_items[:2])}")
        if self.errors:
            parts.append(f"✗ 错误: {'; '.join(self.errors[:1])}")
        return "\n".join(parts)

    def to_injectable(self, max_tokens: int = 500) -> str:
        """
        格式化为可注入 LLM 的紧凑上下文。

        目标: ≤300 tokens (约 1200 字符)
        硬上限: max_tokens (默认 500 tokens ≈ 2000 字符)

        格式设计原则:
        - 使用紧凑的符号标记（✓ → ✗），不占用多余 token
        - 只保留对后续任务有用的状态信息
        - 不注入原始用户 prompt 或模型输出原文
        """
        lines = []

        # 意图 + 结果
        outcome_icon = {"success": "✓", "partial": "⚠", "failed": "✗"}.get(self.outcome, "?")
        lines.append(f"[{self.intent}] {outcome_icon}")

        # 已验证的变化（最有价值的信息）
        if self.verified_changes:
            for change in self.verified_changes[:3]:
                lines.append(change.to_compact())

        # 关键事实（最多 2 条）
        if self.key_facts:
            for fact in self.key_facts[:2]:
                lines.append(f"· {fact[:200]}")

        # 未完成事项（对"继续"类请求最重要）
        if self.unresolved_items:
            lines.append(f"⚠ 未完成: {'; '.join(self.unresolved_items[:2])}")

        # 失败信息
        if self.errors:
            lines.append(f"✗ 错误: {'; '.join(self.errors[:1])}")

        result = "\n".join(lines)

        # 硬性截断: 使用原始文本长度而非估算 token 数（避免循环）
        char_limit = max_tokens * 4
        if len(result) > char_limit:
            result = result[:char_limit] + "..."

        return result


# ============================================================
# 注入决策规则
# ============================================================

@dataclass
class InjectionDecision:
    """注入决策结果"""
    should_inject: bool
    """是否应该注入记忆上下文"""
    reason: str
    """决策原因"""
    selected_deltas: List[SessionStateDelta] = field(default_factory=list)
    """选中的状态增量列表"""


def decide_injection(
    current_workspace_id: str,
    current_prompt: str,
    recent_deltas: List[SessionStateDelta],
    max_deltas: int = 3,
    max_total_tokens: int = 1500,
) -> InjectionDecision:
    """
    三步注入决策:

    第一步: 边界判断
    - 工作区是否匹配？
    - 用户是否要求忽略历史？
    - 是否是首次对话？

    第二步: 选择相关事实
    - 是否有引用词（"上面/刚才/继续"）？
    - 是否有未完成事项值得延续？
    - 工作区是否有最近操作？

    第三步: 预算裁剪
    - 按重要性排序
    - 按 token 预算装入
    - 超预算时丢弃低价值 delta
    """
    import re

    # ---- 第一步: 边界判断 ----
    ignore_patterns = [
        r'重新开始', r'忽略上文', r'忽略历史', r'从头开始',
        r'new session', r'start over', r'clear context', r'reset',
    ]
    for pattern in ignore_patterns:
        if re.search(pattern, current_prompt, re.IGNORECASE):
            return InjectionDecision(
                should_inject=False,
                reason="用户要求忽略历史上下文",
            )

    # ---- 第二步: 关联性判断 ----
    reference_patterns = [
        r'(?:上面|上文|前面|之前|刚才|上一轮|前述|上述|以上|前述|刚刚)',
        r'(?:继续|接着|然后|下一步|往下)',
        r'(?:那个|这个|它|其|该)',
        r'(?:好的|OK|okay?|对的|不错|行|可以|嗯嗯?|是的|没错)',
    ]
    has_reference = any(
        re.search(p, current_prompt) for p in reference_patterns
    )

    # 选定相关 delta
    selected: List[SessionStateDelta] = []
    current_token_estimate = 0

    # 优先级 1: 同工作区的最近 delta
    same_ws = [
        d for d in recent_deltas
        if d.workspace_id == current_workspace_id
    ][:max_deltas]

    # 优先级 2: 有未完成事项的 delta（对"继续"请求最有用）
    has_unresolved = [d for d in same_ws if d.unresolved_items]

    # 优先级 3: 有引用词时，包含最近 2 条
    if has_reference:
        candidates = has_unresolved + [
            d for d in same_ws if d not in has_unresolved
        ]
        candidates = candidates[:max(2, max_deltas)]
    else:
        # 无引用词时，仅注入有未完成事项的 delta
        candidates = has_unresolved[:1]

    # ---- 第三步: 预算裁剪 ----
    for delta in candidates:
        est = delta.estimate_tokens()
        if current_token_estimate + est <= max_total_tokens:
            selected.append(delta)
            current_token_estimate += est
        else:
            break

    if not selected:
        return InjectionDecision(
            should_inject=False,
            reason="无相关记忆或预算不足",
        )

    return InjectionDecision(
        should_inject=True,
        reason=f"找到 {len(selected)} 条相关状态增量 (est. {current_token_estimate} tokens)",
        selected_deltas=selected,
    )


# ============================================================
# 构建辅助函数
# ============================================================

def build_delta_from_task_result(
    task_id: str,
    workspace_path: str,
    intent: str,
    task_result: dict,
    context: dict,
    changed_files: List[str] = None,
) -> SessionStateDelta:
    """
    从任务结果构建 SessionStateDelta。

    这是 temp_session_memory 写入侧的工厂函数。
    确保每条 delta 都经过证据分级。
    """
    import hashlib

    workspace_id = hashlib.md5(
        str(workspace_path).encode("utf-8")
    ).hexdigest()[:12]

    delta = SessionStateDelta(
        task_id=task_id,
        workspace_id=workspace_id,
        intent=intent,
        outcome=task_result.get("status", "unknown"),
    )

    # 从 context 提取事实
    user_request = context.get("user_request", "") or ""
    executed_commands = context.get("executed_commands", [])
    file_ops = context.get("final_file_ops", [])
    tool_results = context.get("tool_results", [])

    # --- attempted_actions ---
    if intent in ("write_code", "fix_code", "refactor"):
        if changed_files:
            for f in changed_files[:3]:
                delta.attempted_actions.append(ActionRecord(
                    description=f"生成/修改文件 {f}",
                    evidence_tier=EvidenceTier.GENERATED,
                    actionable_files=[f],
                ))
        else:
            delta.attempted_actions.append(ActionRecord(
                description=f"响应 {intent} 请求",
                evidence_tier=EvidenceTier.STATED,
            ))

    elif intent == "execute_operation":
        for cmd in executed_commands[:3]:
            delta.attempted_actions.append(ActionRecord(
                description=f"执行命令: {cmd[:80]}",
                evidence_tier=EvidenceTier.ATTEMPTED,
            ))

    # --- verified_changes (从 tool_results 提取) ---
    for tr in tool_results[:3]:
        result_type = tr.get("type", "")
        result = tr.get("result", {})
        if result_type == "code_analysis":
            stats = result.get("stats", {})
            delta.verified_changes.append(ActionRecord(
                description=f"代码统计: {stats.get('total_lines', '?')} 行, {stats.get('total_files', '?')} 文件",
                evidence_tier=EvidenceTier.EXECUTED,
            ))
        elif result_type == "file_created":
            path = result.get("path", "")
            delta.verified_changes.append(ActionRecord(
                description=f"创建文件: {path}",
                evidence_tier=EvidenceTier.VERIFIED,
                actionable_files=[path],
            ))

    # --- key_facts (从 context 提取) ---
    tech_stack = context.get("tech_stack", [])
    if tech_stack:
        delta.key_facts.append(f"技术栈: {', '.join(tech_stack[:5])}")

    workspace_info = context.get("workspace_info", {})
    if workspace_info:
        py_count = workspace_info.get("python_file_count", 0)
        if py_count:
            delta.key_facts.append(f"项目规模: {py_count} 个 Python 文件")

    # --- unresolved_items ---
    if file_ops:
        failed_ops = [op for op in file_ops if op.get("status") == "failed"]
        for op in failed_ops[:2]:
            delta.unresolved_items.append(
                f"文件操作失败: {op.get('path', '?')} ({op.get('error', '?')})"
            )

    if task_result.get("status") == "failed":
        err_msg = task_result.get("error", "未知错误")
        delta.unresolved_items.append(f"任务失败: {err_msg[:200]}")
        delta.errors.append(err_msg[:200])

    # --- evidence_refs ---
    for tr in tool_results[:3]:
        ref = tr.get("ref") or tr.get("id") or tr.get("type")
        if ref:
            delta.evidence_refs.append(str(ref))
    for f in (changed_files or [])[:3]:
        if f not in delta.evidence_refs:
            delta.evidence_refs.append(f)

    return delta


def build_injectable_context(
    current_workspace_id: str,
    current_prompt: str,
    recent_deltas: List[SessionStateDelta],
) -> str:
    """
    一站式注入函数: 决策 + 格式化。

    返回:
        可注入 LLM 的上下文字符串。如果不应注入则返回空字符串。
    """
    decision = decide_injection(
        current_workspace_id=current_workspace_id,
        current_prompt=current_prompt,
        recent_deltas=recent_deltas,
    )

    if not decision.should_inject or not decision.selected_deltas:
        return ""

    parts = ["[工作区最近状态]\n"]
    for i, delta in enumerate(decision.selected_deltas):
        parts.append(delta.to_injectable(max_tokens=150))

    parts.append("\n[状态结束] — 以上仅供参考，以当前工作区实际状态为准。")
    return "\n".join(parts)