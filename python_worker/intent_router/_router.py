# -*- coding: utf-8 -*-
# intent_router._router — Intent Router 主类
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有意图判断、人格选择、执行链决策都必须发生在 Worker 内部
#    - 任何前端、扩展、Node API 都不得参与意图判断
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - Intent → Persona → Execution Chain 必须遵守统一协议
#    - 执行链必须完整、可预测、可验证
#    - 不允许出现"write 找不到 plan"、"refine 找不到 write"这种断链情况
#
# 本模块是 Worker 的核心智能模块，负责：
# 1. 识别用户意图
# 2. 选择人格
# 3. 从唯一映射中为任务选择最小可用执行链
#
# ---------------------------------------------------------

import re
import json
import os
import concurrent.futures
from typing import Dict, Tuple, List, Optional

from ._data import (
    ALL_INTENTS, ALL_TARGET_TYPES, LITE_CLASSIFY_PROMPT,
    FORCE_WRITE_CODE_PATTERNS, PROJECT_IMPLEMENTATION_PATTERNS,
    READ_ONLY_DESIGN_PATTERNS, INTENT_PATTERNS, INTENT_TO_PERSONA,
    ExecutionProfile, _INTENT_DEFAULT_PROFILE, _TEST_EXECUTION_PATTERNS,
)
from ._classification import llm_classify, get_provider_config, call_provider_for_classify

# ⭐ v4.0: Skill 集成 — 技能系统参与执行决策
try:
    from skills.router import route_skill
    from skills.base import Skill as SkillDef
except ImportError:
    route_skill = None
    SkillDef = None


class IntentRouter:
    """
    Intent Router — Worker 内部的智能决策模块
    ---------------------------------------------------------
    设计原则：
    - 明确任务意图优先，未知请求保持只读对话
    - 文档任务优先级最低（generate_doc）
    - creative_writing 不覆盖工程任务
    - 执行链必须完整，不允许断链
    - 所有逻辑必须在 Worker 内部执行（Worker = 真相）
    """

    # 类变量 — 从 _data 模块导入
    ALL_INTENTS = ALL_INTENTS
    ALL_TARGET_TYPES = ALL_TARGET_TYPES
    LITE_CLASSIFY_PROMPT = LITE_CLASSIFY_PROMPT
    FORCE_WRITE_CODE_PATTERNS = FORCE_WRITE_CODE_PATTERNS
    PROJECT_IMPLEMENTATION_PATTERNS = PROJECT_IMPLEMENTATION_PATTERNS
    READ_ONLY_DESIGN_PATTERNS = READ_ONLY_DESIGN_PATTERNS
    INTENT_PATTERNS = INTENT_PATTERNS
    INTENT_TO_PERSONA = INTENT_TO_PERSONA
    ExecutionProfile = ExecutionProfile
    _INTENT_DEFAULT_PROFILE = _INTENT_DEFAULT_PROFILE
    _TEST_EXECUTION_PATTERNS = _TEST_EXECUTION_PATTERNS

    # =========================================================
    # 分类方法 — 委托给 _classification 模块
    # =========================================================

    @classmethod
    def _llm_classify(cls, prompt: str, model_name: str = "qwen") -> Dict:
        return llm_classify(prompt, model_name)

    @classmethod
    def _get_provider_config(cls, model_name: str) -> Dict:
        return get_provider_config(model_name)

    @classmethod
    def _call_provider_for_classify(cls, prompt: str, model_name: str, max_timeout: int = 5) -> str:
        return call_provider_for_classify(prompt, model_name, max_timeout)

    # =========================================================
    # ⭐ v4.0: ExecutionProfile — LLM 无需在 analyze 阶段输出
    # =========================================================

    @classmethod
    def resolve_execution_profile(cls, intent: str, prompt: str = "", matched_skill=None) -> "IntentRouter.ExecutionProfile":
        """
        ⭐ v4.0 核心：由 intent + skill + prompt 联合决策执行维度。

        优先级: Skill.output_profile > 意图默认 profile > 兜底 code 模式
        """
        # 1) 尝试从 skill 获取 output_profile（最高优先级）
        if matched_skill is not None:
            try:
                skill_profile = getattr(matched_skill, "output_profile", None)
                if skill_profile:
                    return cls.ExecutionProfile(
                        output_mode=skill_profile.get("output_mode", "code"),
                        workspace_dependency=skill_profile.get("workspace_dependency", "rw"),
                        target_format=skill_profile.get("target_format", "plain_text"),
                        requires_fileops=skill_profile.get("requires_fileops", True),
                        requires_workspace_scan=skill_profile.get("requires_workspace_scan", True),
                        requires_test=skill_profile.get("requires_test", False),
                        estimated_complexity="moderate",
                    )
            except Exception:
                pass

        # 2) 意图默认 profile
        defaults = cls._INTENT_DEFAULT_PROFILE.get(intent, cls._INTENT_DEFAULT_PROFILE["chat"])

        # 3) prompt 级微调 — 补充规则（不依赖 LLM，快速且可靠）
        ws_dep = defaults["ws_dep"]
        if ws_dep != "read_write" and prompt:
            prompt_lower = prompt.lower()
            # 需要写文件的信号
            if re.search(r"(?:保存|写入|生成文件|创建文件|输出文件|存为|另存为|save|export|output to file)", prompt_lower):
                ws_dep = "read_write"
                defaults = {**defaults, "fileops": True, "scan": True}
            # 需要看项目的信号
            elif re.search(r"(?:项目|当前代码|这个项目|工作区|workspace|代码库|仓库|repo)", prompt_lower):
                if ws_dep == "none":
                    ws_dep = "read_only"
                    defaults = {**defaults, "scan": True}

        return cls.ExecutionProfile(
            output_mode=defaults.get("output_mode", "code"),
            workspace_dependency=ws_dep,
            target_format=defaults.get("fmt", "plain_text"),
            requires_fileops=defaults.get("fileops", False),
            requires_workspace_scan=defaults.get("scan", False),
            requires_test=defaults.get("test", False),
            estimated_complexity=defaults.get("complexity", "moderate"),
        )

    @classmethod
    def build_execution_chain(
        cls,
        intent: str,
        profile: "IntentRouter.ExecutionProfile" = None,
        worker: str = "qwen",
    ) -> List[str]:
        """
        ⭐ v4.0 核心：动态组装执行链，完全替代静态 INTENT_TO_CHAIN。

        当 profile 未传入时，自动从 intent + prompt 解析。
        """
        if profile is None:
            profile = cls.resolve_execution_profile(intent)

        chain = ["analyze"]  # 所有任务都从 analyze 开始

        # 工作区依赖
        if profile.workspace_dependency != "none":
            chain.append("workspace")

        # plan — 非纯 text 模式需要计划
        if profile.output_mode != "text":
            chain.append("plan")

        # write — 核心生成
        chain.append("write")

        # refine — 代码/文档模式
        if profile.output_mode in ("code", "document"):
            chain.append("refine")

        # test — 仅代码模式且需要测试
        if profile.output_mode == "code" and profile.requires_test:
            chain.append("test")

        # fix — 代码模式
        if profile.output_mode == "code":
            chain.append("fix")

        # doc — 代码/文档模式
        if profile.output_mode in ("code", "document"):
            chain.append("doc")

        # docstring — 代码模式
        if profile.output_mode == "code":
            chain.append("docstring")

        # 特殊意图覆盖 — chat/mentor 直接 respond
        if intent in ("chat", "mentor_explain"):
            chain = ["analyze", "plan", "respond"]

        # external_git 不需 write/refine
        if intent == "external_git":
            chain = [s for s in chain if s not in ("write", "refine", "test", "fix", "doc")]
            if "plan" not in chain:
                chain.insert(1, "plan")

        # local worker 简化
        if worker == "local":
            chain = ["write"]

        return chain

    @classmethod
    def _is_test_execution_request(cls, prompt: str) -> bool:
        prompt_lower = prompt.lower().strip()
        for pattern in cls._TEST_EXECUTION_PATTERNS:
            if re.search(pattern, prompt_lower):
                return True
        return False

    # ⭐ v4.0 Phase 4: LLM 分析输出中提取 ExecutionProfile
    @classmethod
    def parse_execution_profile_from_analysis(cls, analysis_output: str) -> Optional["IntentRouter.ExecutionProfile"]:
        """
        从 LLM 的 analyze_step 输出中提取 [EXECUTION_PROFILE] JSON 块。

        容错策略：
        1. 精确匹配 [EXECUTION_PROFILE] 后的 JSON 块
        2. 尝试 JSON 解析，失败时逐字段正则提取
        3. 完全无法提取时返回 None（调用方保持原始链）
        """
        if not analysis_output:
            return None

        _PROFILE_MARKER = "[EXECUTION_PROFILE]"
        marker_idx = analysis_output.find(_PROFILE_MARKER)

        if marker_idx == -1:
            return None

        json_block = analysis_output[marker_idx + len(_PROFILE_MARKER):].strip()

        # 截取到下一个可能的标记块或代码块
        for delimiter in ("\n\n---", "\n```", "[EXECUTION_PROFILE]", "\n# ", "\n【"):
            if delimiter in json_block:
                json_block = json_block[:json_block.find(delimiter)]
        json_block = json_block.strip()

        # 尝试 JSON 解析
        profile_dict = None
        try:
            if json_block.startswith("{"):
                profile_dict = json.loads(json_block)
        except json.JSONDecodeError:
            pass

        if not profile_dict:
            profile_dict = {}
            field_patterns = {
                "output_mode": r'"output_mode"\s*:\s*"(text|document|code|mixed)"',
                "workspace_dependency": r'"workspace_dependency"\s*:\s*"(none|read_only|read_write)"',
                "target_format": r'"target_format"\s*:\s*"(py|md|txt|json|html|plain_text)"',
                "requires_fileops": r'"requires_fileops"\s*:\s*(true|false)',
                "requires_workspace_scan": r'"requires_workspace_scan"\s*:\s*(true|false)',
                "requires_test": r'"requires_test"\s*:\s*(true|false)',
                "estimated_complexity": r'"estimated_complexity"\s*:\s*"(simple|moderate|complex)"',
            }
            for field, pattern in field_patterns.items():
                m = re.search(pattern, json_block, re.IGNORECASE)
                if m:
                    val = m.group(1).lower()
                    profile_dict[field] = True if val == "true" else (False if val == "false" else val)

        if not profile_dict or "output_mode" not in profile_dict:
            return None

        try:
            return cls.ExecutionProfile(
                output_mode=profile_dict.get("output_mode", "code"),
                workspace_dependency=profile_dict.get("workspace_dependency", "rw"),
                target_format=profile_dict.get("target_format", "plain_text"),
                requires_fileops=profile_dict.get("requires_fileops", True),
                requires_workspace_scan=profile_dict.get("requires_workspace_scan", True),
                requires_test=profile_dict.get("requires_test", False),
                estimated_complexity=profile_dict.get("estimated_complexity", "moderate"),
            )
        except Exception:
            return None

    # ⭐ v4.0: Skill 匹配缓存 — 避免 detect_intent 内多次调用 route_skill
    @classmethod
    def _resolve_chain(
        cls, intent: str, prompt: str = "", worker: str = "qwen", matched_skill=None
    ) -> List[str]:
        profile = cls.resolve_execution_profile(intent, prompt, matched_skill)
        return cls.build_execution_chain(intent, profile, worker)

    @classmethod
    def execution_chain_for(cls, intent: str, worker: str = "qwen", prompt: str = "") -> List[str]:
        chain = cls._resolve_chain(intent, prompt=prompt, worker=worker)

        if worker == "local":
            chain = ["write"]
        elif worker != "qwen":
            if "workspace" in chain:
                chain = ["analyze", "plan"]
            else:
                chain = ["write" if step == "respond" else step for step in chain]

        prompt_lower = (prompt or "").lower()
        if intent in {"write_code", "refactor"}:
            if re.search(r"(?:文档|说明文档|documentation|readme)", prompt_lower):
                if "doc" not in chain:
                    chain.append("doc")
            if re.search(r"(?:docstring|文档字符串)", prompt_lower):
                if "docstring" not in chain:
                    chain.append("docstring")
            if re.search(r"(?:性能|profile|profiling|性能分析)", prompt_lower):
                if "profile" not in chain:
                    chain.append("profile")
        return chain

    @classmethod
    def detect_intent(cls, prompt: str, model_name: str = "qwen") -> Tuple[str, str, List[str]]:
        """
        智能增强版意图识别（符合架构信条）
        ---------------------------------------------------------
        参数:
            prompt: 用户输入文本
            model_name: Worker 类型 (qwen/gemini/modelscope/maas/local)
                       决定使用哪个 LLM 做语义分类；无对应 API Key 时自动降级 Regex
        Worker = 真相：
            - 所有意图判断必须在 Worker 内部执行
            - 每个 Worker 使用自己的 LLM 做语义分类
        协议 = 宪法：
            - 执行链必须完整、可预测、可验证
        """

        if not prompt or not prompt.strip():
            intent = "chat"
            return intent, cls.INTENT_TO_PERSONA[intent], cls._resolve_chain(intent, prompt, worker=model_name)

        # ============================================================
        # ⭐ v4.0: Skill 匹配（在意图检测之前，影响执行链决策）
        # ============================================================
        matched_skill = None
        if route_skill is not None:
            try:
                matched_skill = route_skill(prompt)
                if matched_skill:
                    print(f"\n🎯 Skill Router 匹配: {matched_skill.id} ({matched_skill.name})")
            except Exception:
                pass

        # ============================================================
        # ⓪ LLM 语义路由（第一层）— LLM + Regex 联合路由
        # ============================================================
        llm_result = cls._llm_classify(prompt, model_name)
        if llm_result and llm_result["confidence"] >= 0.75:
            intent = llm_result["intent"]
            target_type = llm_result["target_type"]
            confidence = llm_result["confidence"]
            reasoning = llm_result["reasoning"]

            if intent == "workspace_maintenance" and cls._is_test_execution_request(prompt):
                intent = "write_code"
                target_type = "test"
                print(f"\n🔧 Intent Router 硬覆盖：测试执行请求不应归类为 workspace_maintenance → write_code")

            persona = cls.INTENT_TO_PERSONA.get(intent, "engineer")
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)

            print(f"\n🧠 Intent Router（{model_name.upper()} 语义路由 | confidence={confidence:.2f}）:")
            print(f"  意图: {intent} | 目标类型: {target_type}")
            print(f"  人格: {persona} | 推理: {reasoning}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        if llm_result:
            print(f"\n⚠️ Intent Router（LLM低置信={llm_result['confidence']:.2f}，降级Regex）")
        else:
            print(f"\n⚠️ Intent Router（LLM不可用，降级Regex）")

        prompt_lower = prompt.lower().strip()
        prompt_stripped = prompt.strip()

        for pattern in cls.INTENT_PATTERNS["workspace_maintenance"]:
            if re.search(pattern, prompt_lower):
                intent = "workspace_maintenance"
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)
                print("\n🧠 Intent Router（工作区工具任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")
                return intent, persona, chain

        for intent in ("explain_and_fix", "code_review", "delete_files"):
            if any(re.search(pattern, prompt_lower) for pattern in cls.INTENT_PATTERNS[intent]):
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)
                print("\n🧠 Intent Router（复合任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")
                return intent, persona, chain

        # =========================================================
        # ① 强制工程任务（最高优先级）
        # =========================================================
        explicitly_read_only_design = (
            any(
                re.search(pattern, prompt_stripped, re.IGNORECASE)
                for pattern in cls.READ_ONLY_DESIGN_PATTERNS
            )
            and any(
                re.search(pattern, prompt_stripped, re.IGNORECASE)
                for pattern in cls.INTENT_PATTERNS["architecture"]
            )
        )
        if not explicitly_read_only_design:
            for pattern in cls.FORCE_WRITE_CODE_PATTERNS:
                if re.search(pattern, prompt_stripped, re.IGNORECASE):
                    intent = "write_code"
                    persona = cls.INTENT_TO_PERSONA[intent]
                    chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)

                    print("\n🧠 Intent Router（强制工程任务识别）:")
                    print(f"  意图: {intent}")
                    print(f"  人格: {persona}")
                    print(f"  执行链: {' → '.join(chain)}")

                    return intent, persona, chain

        if not explicitly_read_only_design and any(
            re.search(pattern, prompt_stripped, re.IGNORECASE)
            for pattern in cls.PROJECT_IMPLEMENTATION_PATTERNS
        ):
            intent = "write_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)

            print("\n🧠 Intent Router（全栈项目交付识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")

            return intent, persona, chain

        # =========================================================
        # ② 普通意图匹配（按优先级）
        # =========================================================
        if cls._is_test_execution_request(prompt):
            intent = "write_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)
            print("\n🧠 Intent Router（Regex 测试执行识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        for intent, patterns in cls.INTENT_PATTERNS.items():
            if intent == "workspace_maintenance":
                continue
            for pattern in patterns:
                if re.search(pattern, prompt_lower):
                    persona = cls.INTENT_TO_PERSONA[intent]
                    chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)

                    print("\n🧠 Intent Router 识别结果:")
                    print(f"  意图: {intent}")
                    print(f"  人格: {persona}")
                    print(f"  执行链: {' → '.join(chain)}")

                    return intent, persona, chain

        # =========================================================
        # ③ 默认：对话
        # =========================================================
        print("\n⚠️ Intent Router 未识别明确意图，使用安全的对话链路")
        intent = "chat"
        return intent, cls.INTENT_TO_PERSONA[intent], cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill)

    @classmethod
    def plan_request(
        cls,
        prompt: str,
        workspace_available: bool = False,
        source_files_available: bool = False,
        worker: str = "qwen",
        detected_intent: str = None,
        detected_persona: str = None,
        detected_chain: list = None,
        matched_skill=None,
    ) -> Dict:
        if detected_intent and detected_persona and detected_chain is not None:
            intent, persona, chain = detected_intent, detected_persona, list(detected_chain)
        else:
            intent, persona, chain = cls.detect_intent(prompt, model_name=worker)
        chain = cls._resolve_chain(intent, prompt, worker=worker, matched_skill=matched_skill)

        if intent in {"mentor_explain", "explain_code", "chat"}:
            mode = "MENTOR_EXPLAIN"
            context_requirements = (
                ["README", "tests", "startup scripts"]
                if intent == "mentor_explain"
                else ["user-provided code or error context"]
            )
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "qwen.explain", "available": True},
            ]
            side_effects = []
            approval = {"required": False, "before": []}
            validation = ["Do not claim tests or commands were executed"]
            recovery = ["Explain missing project context and provide a general procedure"]
        elif intent == "code_review":
            mode = "REVIEW_ONLY"
            context_requirements = ["requested source files", "related project instructions"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available or source_files_available},
                {"id": "qwen.review", "available": True},
            ]
            side_effects = []
            approval = {"required": False, "before": []}
            validation = ["Return findings only; do not create or modify files"]
            recovery = ["State clearly when requested source files are unavailable"]
        elif intent == "delete_files":
            mode = "FILE_DELETE_PROPOSAL"
            context_requirements = ["explicit workspace-relative target paths"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "fileops.delete.propose", "available": True},
            ]
            side_effects = ["propose deletion candidates; host applies recycle-bin and confirmation policy"]
            approval = {"required": True, "before": ["batch or directory deletion"]}
            validation = [
                "Propose only explicitly named relative paths",
                "Never delete sensitive paths or execute filesystem commands",
            ]
            recovery = ["Ask for exact relative paths when a target is ambiguous"]
        elif intent == "workspace_maintenance":
            mode = "WORKSPACE_MAINTENANCE"
            context_requirements = ["Project source inventory", "syntax and indentation diagnostics", "dependency manifests"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "workspace.environment", "available": workspace_available and worker == "qwen"},
                {"id": "workspace.syntax", "available": workspace_available},
            ]
            side_effects = (
                ["in-scope source changes", "project virtual environment", "declared dependency installation"]
                if worker == "qwen"
                else []
            )
            approval = {"required": False, "before": []}
            validation = ["Compile the language payload and report results", "Report the actual environment and dependency command results"]
            recovery = ["Keep failed operations explicit and do not claim they completed"]
            if worker != "qwen":
                recovery.append("This Worker does not provide the workspace maintenance tool; do not claim a scan or environment operation")
        elif intent == "external_git":
            mode = "EXTERNAL_CAPABILITY"
            context_requirements = ["git status", "branch", "remote", ".gitignore"]
            capabilities = [
                {"id": "git.inspect", "available": False},
                {"id": "git.push", "available": False},
            ]
            side_effects = ["git add", "git commit", "git push"]
            approval = {"required": True, "before": side_effects}
            validation = ["Verify remote and push result after execution"]
            recovery = ["Stop without changing the repository when Git capability is unavailable"]
        else:
            mode = "ENGINEER_EXECUTE"
            if intent in {"fix_code", "explain_and_fix"}:
                context_requirements = ["named source files", "reported error", "related tests"]
            else:
                context_requirements = ["target files", "related tests", "project instructions"]
            capabilities = [
                {"id": "qwen.analyze", "available": True},
                {"id": "qwen.generate_changes", "available": True},
                {"id": "workspace.read", "available": source_files_available or workspace_available},
                {"id": "fileops.apply", "available": True},
                {"id": "project.test", "available": False},
            ]
            side_effects = ["workspace file changes"]
            approval = {"required": True, "before": side_effects + ["project tests"]}
            validation = ["Run relevant project tests after approval"]
            recovery = ["Preserve the proposed changes and report failed validation"]

        return {
            "mode": mode,
            "intent": intent,
            "persona": persona,
            "context_requirements": context_requirements,
            "capabilities": capabilities,
            "execution_chain": list(chain),
            "side_effects": side_effects,
            "approval": approval,
            "validation": validation,
            "recovery": recovery,
        }

    @classmethod
    def get_persona_config(cls, persona_type: str) -> Dict:
        from .agents.qwen.personas import get_persona_config
        return get_persona_config(persona_type)


def detect_user_intent(prompt: str, model_name: str = "qwen") -> Tuple[str, str, List[str]]:
    return IntentRouter.detect_intent(prompt, model_name)


def requires_authorization_before_step(execution_plan: Dict, step_type: str) -> bool:
    return bool(execution_plan.get("approval", {}).get("required")) and step_type == "test"