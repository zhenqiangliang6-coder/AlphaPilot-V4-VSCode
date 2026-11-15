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
    ALL_INTENTS, ALL_TARGET_TYPES, ALL_TARGET_LANGUAGES,
    LITE_CLASSIFY_PROMPT,
    FORCE_WRITE_CODE_PATTERNS, PROJECT_IMPLEMENTATION_PATTERNS,
    FORCE_EXECUTE_OPERATION_PATTERNS, READ_ONLY_DESIGN_PATTERNS,
    _INTENT_DEFAULT_PROFILE, INTENT_TO_PERSONA, INTENT_PATTERNS,
    ExecutionProfile, _TEST_EXECUTION_PATTERNS, DEPENDENCY_INSTALL_PATTERNS,
)
from ._classification import llm_classify, get_provider_config, call_provider_for_classify
from ._planning_contract import get_impl_plan_requirement, validate_replan, needs_reauthorization
from ._chains import get_language_format, apply_language_modifiers

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
    FORCE_EXECUTE_OPERATION_PATTERNS = FORCE_EXECUTE_OPERATION_PATTERNS
    READ_ONLY_DESIGN_PATTERNS = READ_ONLY_DESIGN_PATTERNS
    INTENT_PATTERNS = INTENT_PATTERNS
    INTENT_TO_PERSONA = INTENT_TO_PERSONA
    ExecutionProfile = ExecutionProfile
    _INTENT_DEFAULT_PROFILE = _INTENT_DEFAULT_PROFILE
    _TEST_EXECUTION_PATTERNS = _TEST_EXECUTION_PATTERNS
    DEPENDENCY_INSTALL_PATTERNS = DEPENDENCY_INSTALL_PATTERNS

    # ⭐ 确定性优先：文档-only 的架构设计请求
    # 取证（2026-11-14 ShopFlow R5）：同一 Prompt、同一模型 qwen3.7-flash
    # 连续 5 次分类，3 次 architecture / 2 次 write_code —— 40% 漂移。
    # 误判为 write_code 后协作模式切到 engineer，架构师只读文件策略失效，
    # 执行链还多出 test/fix/docstring 三个无关步骤（长 Prompt 超时的直接来源）。
    # 这类请求语言特征明确（要文档 + 明确禁止实现代码），不该交给 LLM 猜。
    _ARCH_DOC_REQUEST_PATTERNS = (
        r"架构(?:设计)?文档",
        r"(?:架构|architecture)\s*(?:设计|design)",
        r"(?:设计|design)\s*(?:文档|document|blueprint)",
        r"architecture\s*(?:document|blueprint|design)",
        r"(?:系统|backend|平台)\s*(?:架构|architecture)",
    )
    _NO_IMPLEMENTATION_PATTERNS = (
        r"不要写(?:任何)?(?:实现)?代码",
        r"不(?:要)?(?:输出|生成|创建)(?:任何)?(?:实现)?代码",
        r"只(?:输出|写|生成)(?:设计)?文档",
        r"仅(?:输出|生成)(?:设计)?文档",
        r"不(?:写|生成)(?:任何)?实现",
        r"documentation\s*only",
        r"do\s*not\s*write\s*(?:any\s*)?(?:implementation\s*)?code",
        r"design\s*document\s*only",
    )

    # ⭐ 测试失败修复确定性优先
    # 取证（2026-11-14 ShopFlow R7）：同一类「pytest 报错 + 请修复」请求，
    # 两次真实链路分别被判成 explain_and_fix 和 write_code。误判为 write_code
    # 后 write_step 做全量生成，一次改了 27 个文件（题面要求最小修改），
    # 反而引入 422 / 缺表等 6 个新失败。
    _FAILURE_CONTEXT_PATTERNS = (
        r"pytest", r"traceback", r"测试失败", r"运行.{0,12}错误",
        r"errors?\b", r"failed\b",
    )
    _REPAIR_INTENT_PATTERNS = (
        r"定位根因", r"修复所有", r"逐一排查", r"修复.{0,12}错误",
        r"修复.{0,12}问题", r"fix.{0,12}bug",
    )
    _GREENFIELD_PATTERNS = (
        r"从零", r"新建项目", r"实现.{0,12}核心功能",
        r"创建.{0,12}模块", r"请实现",
    )

    # ⭐ G10.23：枚举值级联替换确定性优先（LLM 不可用时的 Regex 兜底会误判 chat）
    # 取证（2026-11-15 ShopFlow R9 / shopflow_v4_1）：分类模型 qwen-plus 免费额度
    # 耗尽(403) → 分类器被锁死在单点模型 → 降级 Regex 没命中任何既有模式 →
    # 判成 chat，执行链 analyze→workspace→plan→respond，零 FileOps、无授权记录，
    # 却写回 outcome=success，质量+治理双红并连锁 R10。
    # 这类题面有三个不可混淆的特征（代码实体 + 修改动词 + 跨文件级联范围），
    # 据此确定性判 write_code，不依赖 LLM 是否可用。
    _ENUM_CASCADE_ENTITY_PATTERNS = (
        r"枚举", r"状态值", r"状态枚举", r"状态机", r"OrderStatus",
    )
    _ENUM_CASCADE_VERB_PATTERNS = (
        r"修改", r"更新", r"替换", r"改为", r"同步更新",
    )
    _ENUM_CASCADE_SCOPE_PATTERNS = (
        r"所有引用", r"找出所有", r"一次性全部", r"所有.{0,8}地方",
        r"不得再出现", r"不要遗留", r"全部更新", r"同步更新",
    )
    # R5 架构题面同样有大量 `→`（状态流转、API 契约），箭头计数会误伤；
    # 只有「带引号的旧值 → 带引号的新值」才是值替换的确定性特征。
    _ENUM_CASCADE_MAPPING_PATTERN = (
        r"[\"'][a-z_]+[\"']\s*(?:→|->)\s*[\"'][a-z_]+[\"']"
    )

    # =========================================================
    # 分类方法 — 委托给 _classification 模块
    # =========================================================

    # ⭐ G8.0: 存储最近一次 LLM 分类原始结果，供 detect_intent_multi 读取 compound 信息
    _last_classify_result: Optional[Dict] = None

    @classmethod
    def _llm_classify(cls, prompt: str, model_name: str = "qwen") -> Dict:
        result = llm_classify(prompt, model_name)
        cls._last_classify_result = result
        return result

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
    def resolve_execution_profile(cls, intent: str, prompt: str = "", matched_skill=None, language: str = "python") -> "IntentRouter.ExecutionProfile":
        """
        ⭐ v4.0 核心：由 intent + skill + prompt 联合决策执行维度。

        优先级: Skill.output_profile > 意图默认 profile > 兜底 code 模式
        ⭐ G8.2: language 参数 → target_format 按语言自动切换
        """
        if intent == "run_tests":
            return cls.ExecutionProfile(
                output_mode="text",
                workspace_dependency="read_only",
                target_format="plain_text",
                requires_fileops=False,
                requires_workspace_scan=True,
                requires_test=True,
                estimated_complexity="simple",
            )

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

        # ⭐ G8.2: target_format 按语言切换（代码类意图）
        format_override = get_language_format(language)
        if defaults.get("output_mode") == "code" and format_override != "plain_text":
            defaults = {**defaults, "fmt": format_override}

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
        language: str = "python",
    ) -> List[str]:
        """
        ⭐ v4.0 核心：动态组装执行链，完全替代静态 INTENT_TO_CHAIN。

        当 profile 未传入时，自动从 intent + prompt 解析。

        ⭐ G8.2: language 参数启用多语言横向扩展
        - 编译型语言自动注入 compile 步骤
        - target_format 按语言自动切换
        """
        if intent == "run_tests":
            return ["analyze", "plan", "test"]

        if profile is None:
            profile = cls.resolve_execution_profile(intent, language=language)

        chain = ["analyze"]  # 所有任务都从 analyze 开始

        # 修复类任务只改已有代码：不做依赖装配、不产出文档/docstring。
        # 取证（2026-11-14 ShopFlow R7）：explain_and_fix 默认 10 步链，
        # 加上长 traceback Prompt，单轮超过 900s 轮询窗口 → R7–R10 连锁超时。
        # setup 还可能凭 DEPENDS 块新建无关文件，与「最小修改」题面相冲突。
        _is_repair_intent = intent in {"fix_code", "explain_and_fix"}

        # 工作区依赖
        if profile.workspace_dependency != "none":
            chain.append("workspace")

        # plan — 非纯 text 模式需要计划
        if profile.output_mode != "text":
            chain.append("plan")

        # setup — P2: DEPENDS 块处理、缺失文件 stub、清单文件自动创建
        # 仅在代码/文档模式（有文件生成）时运行；修复类任务跳过
        if profile.output_mode in ("code", "document") and not _is_repair_intent:
            chain.append("setup")

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

        # doc / docstring — 代码/文档模式；修复类任务不产出任何文档
        if profile.output_mode in ("code", "document") and not _is_repair_intent:
            chain.append("doc")

        if profile.output_mode == "code" and not _is_repair_intent:
            chain.append("docstring")

        # respond — generate_doc 需要 respond 步骤触发产物提取（Mermaid 架构图等）
        if intent == "generate_doc":
            chain.append("respond")

        # 特殊意图覆盖 — chat/mentor 直接 respond
        # v4.x Phase B: 仅当不需要工作区时才使用轻量链；
        # 需要工作区时插入 workspace 步骤
        if intent in ("chat", "mentor_explain"):
            if profile.workspace_dependency != "none":
                chain = ["analyze", "workspace", "plan", "respond"]
            else:
                chain = ["analyze", "plan", "respond"]

        # ⭐ G8.2: 应用 per-language 步骤修饰器（编译型语言注入 compile 等）
        chain = apply_language_modifiers(chain, language)

        # set_preference — 只需理解约定并写入
        if intent == "set_preference":
            chain = ["analyze", "plan", "write"]

        # external_git 不需 write/refine
        if intent == "external_git":
            chain = [s for s in chain if s not in ("write", "refine", "test", "fix", "doc")]
            if "plan" not in chain:
                chain.insert(1, "plan")

        # ⭐ G7.0 execute_operation — 执行系统操作：直接 operate → respond
        #    operate 步骤内部已完整处理：检测操作类型 → 执行 → 格式化结果
        #    不需要 analyze/workspace/plan 前置（那是代码生成链的步骤）
        if intent == "execute_operation":
            chain = ["operate", "respond"]

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

    @classmethod
    def _is_project_test_request(cls, prompt: str) -> bool:
        if not cls._is_test_execution_request(prompt):
            return False
        # G10.13（ShopFlow R8 实证）：题面里只要出现「pytest」就会命中
        # _TEST_EXECUTION_PATTERNS（含裸 `pytest\b`），但增量/重构类题面
        # 常常是在描述「否则 pytest 会报错」，并非要求跑测试。
        # ① 结构化交付清单 = 必然写文件：编号/列表形式的代码路径、
        #    「新增内容:」「变更内容:」等小节标题，一律不判 run_tests。
        delivery_signals = (
            r"(?:新增|变更|修改|交付|输出|需要|要求)\s*(?:内容|清单|文件)\s*[:：]",
            r"(?m)^\s*(?:\d+[.、)]|[-*])\s*"
            r"(?:backend|src|app|tests|frontend)/[\w/\-.]+\.py\b",
        )
        if any(re.search(p, prompt, re.IGNORECASE) for p in delivery_signals):
            return False
        # ② 显式修改信号：动词表补「增加/重构/提取…」、名词表补
        #    「模型/路由/服务…」（R8 首句正是「增加…模块」，旧表漏了「增加」）。
        explicit_change_patterns = (
            r"(?:新增|添加|增加|创建|编写|生成|实现|开发|搭建|修改|更新|重构|"
            r"提取|拆分|迁移|新建|加入|补充|扩展|add|create|write|implement|"
            r"develop|edit|modify|update|refactor)"
            r".{0,24}(?:功能|模块|组件|接口|业务|代码|文件|模型|路由|服务|服务层|"
            r"schema|字段|表|API|endpoint|逻辑|测试用例|test case|spec)",
            r"(?:功能|模块|组件|接口|业务|代码|文件|模型|路由|服务|服务层|"
            r"schema|字段|表|API|endpoint|逻辑|测试用例|test case|spec)"
            r".{0,24}(?:新增|添加|增加|创建|编写|生成|实现|开发|搭建|修改|更新|重构|"
            r"提取|拆分|迁移|新建|加入|补充|扩展|add|create|write|implement|"
            r"develop|edit|modify|update|refactor)",
        )
        return not any(
            re.search(pattern, prompt, re.IGNORECASE)
            for pattern in explicit_change_patterns
        )

    # ⭐ C: 依赖安装确定性优先 — 在 LLM 语义路由之前拦截
    # "安装依赖/创建虚拟环境" 关键词特征明确, 不需要 LLM 猜测
    @classmethod
    def _is_dependency_install_request(cls, prompt: str) -> bool:
        prompt_lower = prompt.lower().strip()
        for pattern in cls.DEPENDENCY_INSTALL_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _is_architecture_document_request(cls, prompt: str) -> bool:
        """文档-only 架构设计请求的确定性识别（与 LLM 分类结果无关）。

        必须同时满足：① 明确要架构/设计文档；② 明确禁止写实现代码 / 只输出文档。
        只命中①的「请设计一个架构并给出实现」不会被拦截，避免误伤正常编码任务。
        """
        if not prompt or not prompt.strip():
            return False
        has_doc_request = any(
            re.search(pattern, prompt, re.IGNORECASE)
            for pattern in cls._ARCH_DOC_REQUEST_PATTERNS
        )
        if not has_doc_request:
            return False
        return any(
            re.search(pattern, prompt, re.IGNORECASE)
            for pattern in cls._NO_IMPLEMENTATION_PATTERNS
        )

    @classmethod
    def _is_test_failure_repair_request(cls, prompt: str) -> bool:
        """「运行报错 + 请定位并修复」的确定性识别。

        必须同时有失败上下文与修复意图，且不能是「从零实现」类请求，
        避免把 R6 建项目、R8 加模块误判成修复。
        """
        if not prompt or not prompt.strip():
            return False
        if any(re.search(p, prompt, re.IGNORECASE) for p in cls._GREENFIELD_PATTERNS):
            return False
        has_failure = any(
            re.search(p, prompt, re.IGNORECASE) for p in cls._FAILURE_CONTEXT_PATTERNS
        )
        has_repair = any(
            re.search(p, prompt, re.IGNORECASE) for p in cls._REPAIR_INTENT_PATTERNS
        )
        return has_failure and has_repair

    @classmethod
    def _is_enum_cascade_change_request(cls, prompt: str) -> bool:
        """「枚举值跨文件级联替换」的确定性识别（早于 LLM，漂移免疫）。

        必须同时具备：① 枚举 / 状态机代码实体；② 明确修改动词；
        ③ 跨文件级联范围措辞 **或** 至少两组 `"A" → "B"` 值映射。
        从零建项目类题面直接排除，避免误伤 R6 / R8。
        任一条不满足就完全不拦截，交回原有 LLM / Regex 路由（FAIL-OPEN）。
        """
        if not prompt or not prompt.strip():
            return False
        # 架构文档题面里同样有 OrderStatus 枚举 + 大量 `→`，必须显式排除，
        # 不能只依赖 detect_intent 里的调用顺序（顺序依赖太脆弱）。
        if cls._is_architecture_document_request(prompt):
            return False
        if any(re.search(p, prompt, re.IGNORECASE)
               for p in cls._GREENFIELD_PATTERNS):
            return False
        has_entity = any(re.search(p, prompt, re.IGNORECASE)
                         for p in cls._ENUM_CASCADE_ENTITY_PATTERNS)
        has_verb = any(re.search(p, prompt, re.IGNORECASE)
                       for p in cls._ENUM_CASCADE_VERB_PATTERNS)
        if not (has_entity and has_verb):
            return False
        has_scope = any(re.search(p, prompt, re.IGNORECASE)
                        for p in cls._ENUM_CASCADE_SCOPE_PATTERNS)
        has_mapping = len(re.findall(cls._ENUM_CASCADE_MAPPING_PATTERN,
                                     prompt, re.IGNORECASE)) >= 2
        return has_scope or has_mapping

    @classmethod
    def requests_test_failure_repair(cls, prompt: str) -> bool:
        if not cls._is_test_execution_request(prompt):
            return False
        return bool(re.search(
            r"(?:失败|未通过|不通过|错误|问题|fail(?:ed|ure)?|error)"
            r".{0,32}(?:修复|解决|优化|改进|fix|repair)|"
            r"(?:修复|解决|优化|改进|fix|repair)"
            r".{0,32}(?:失败|未通过|不通过|错误|问题|fail(?:ed|ure)?|error)",
            prompt,
            re.IGNORECASE | re.DOTALL,
        ))

    # ⭐ G7.0: 强制执行操作硬覆盖 — 防止 LLM 将 Git 上传/代码统计误判为 write_code
    @classmethod
    def _is_force_execute_operation(cls, prompt: str) -> bool:
        prompt_lower = prompt.lower().strip()
        for pattern in cls.FORCE_EXECUTE_OPERATION_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
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
        marker_idx = analysis_output.rfind(_PROFILE_MARKER)

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
        cls, intent: str, prompt: str = "", worker: str = "qwen", matched_skill=None, language: str = "python"
    ) -> List[str]:
        profile = cls.resolve_execution_profile(intent, prompt, matched_skill, language=language)
        return cls.build_execution_chain(intent, profile, worker, language=language)

    @classmethod
    def execution_chain_for(cls, intent: str, worker: str = "qwen", prompt: str = "", language: str = "python") -> List[str]:
        if intent == "run_tests":
            return ["analyze", "plan", "test"]

        chain = cls._resolve_chain(intent, prompt=prompt, worker=worker, language=language)

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
            if re.search(r"(?:changelog|CHANGELOG|工作日志|更新日志|变更日志|注入.*更新时间)", prompt_lower):
                if "changelog" not in chain:
                    _insert_after_fix = len(chain)
                    for _i, _step in enumerate(chain):
                        if _step == "fix":
                            _insert_after_fix = _i + 1
                            break
                    else:
                        for _i, _step in enumerate(chain):
                            if _step == "test":
                                _insert_after_fix = _i + 1
                                break
                    chain.insert(_insert_after_fix, "changelog")
        return chain

    @classmethod
    def detect_intent(cls, prompt: str, model_name: str = "qwen", language: str = "python") -> Tuple[str, str, List[str]]:
        """
        智能增强版意图识别（符合架构信条）
        ---------------------------------------------------------
        参数:
            prompt: 用户输入文本
            model_name: Worker 类型 (qwen/gemini/modelscope/maas/local)
                       决定使用哪个 LLM 做语义分类；无对应 API Key 时自动降级 Regex
            language: 目标编程语言 (python/java/nodejs/typescript/go/...)
                     ⭐ G8.2: 按语言动态定制执行链
        Worker = 真相：
            - 所有意图判断必须在 Worker 内部执行
            - 每个 Worker 使用自己的 LLM 做语义分类
        协议 = 宪法：
            - 执行链必须完整、可预测、可验证
        """

        if not prompt or not prompt.strip():
            intent = "chat"
            return intent, cls.INTENT_TO_PERSONA[intent], cls._resolve_chain(intent, prompt, worker=model_name, language=language)

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

        if cls._is_project_test_request(prompt.strip()):
            intent = "run_tests"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(
                intent,
                prompt,
                worker=model_name,
                matched_skill=matched_skill,
                language=language,
            )
            print("\n🧠 Intent Router（项目测试请求识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # ⭐ C: 依赖安装确定性优先 — 在 LLM 语义路由之前拦截, 防止误分类为 execute_operation 之外的意图
        if cls._is_dependency_install_request(prompt):
            intent = "execute_operation"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(
                intent,
                prompt,
                worker=model_name,
                matched_skill=matched_skill,
                language=language,
            )
            print("\n🧠 Intent Router（依赖安装确定性识别）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # ⭐ 文档-only 架构设计确定性优先 — 必须早于 LLM 语义路由。
        # 语义分类对该题型实测 40% 漂移（architecture ↔ write_code），
        # 一旦误判，协作模式与文件策略守卫会整条走错。
        if cls._is_architecture_document_request(prompt):
            intent = "architecture"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(
                intent,
                prompt,
                worker=model_name,
                matched_skill=matched_skill,
                language=language,
            )
            print("\n🧠 Intent Router（架构文档确定性识别 | LLM 漂移免疫）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # ⭐ 测试失败修复确定性优先 — 必须早于 LLM 语义路由。
        # 「pytest 报错 + 请修复」若被判成 write_code，write_step 会做全量生成，
        # 与题面「只允许最小行数变更」直接冲突（R7 曾一次改 27 个文件）。
        if cls._is_test_failure_repair_request(prompt):
            intent = "fix_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(
                intent,
                prompt,
                worker=model_name,
                matched_skill=matched_skill,
                language=language,
            )
            print("\n🧠 Intent Router（测试失败修复确定性识别 | LLM 漂移免疫）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # ⭐ G10.23：枚举值级联修改确定性优先 — 必须早于 LLM 语义路由。
        # LLM 分类服务不可用时，Regex 兜底会把这类题面判成 chat（零 FileOps），
        # 即使分类模型恢复，语义漂移也会带来同类风险。
        if cls._is_enum_cascade_change_request(prompt):
            intent = "write_code"
            persona = cls.INTENT_TO_PERSONA[intent]
            chain = cls._resolve_chain(
                intent,
                prompt,
                worker=model_name,
                matched_skill=matched_skill,
                language=language,
            )
            print("\n🧠 Intent Router（枚举级联修改确定性识别 | LLM 漂移免疫）:")
            print(f"  意图: {intent}")
            print(f"  人格: {persona}")
            print(f"  执行链: {' → '.join(chain)}")
            return intent, persona, chain

        # ============================================================
        # ⓪ LLM 语义路由（第一层）— LLM + Regex 联合路由
        # ============================================================
        llm_result = cls._llm_classify(prompt, model_name)
        if llm_result and llm_result["confidence"] >= 0.75:
            intent = llm_result["intent"]
            target_type = llm_result["target_type"]
            detected_language = llm_result.get("target_language", language)
            if detected_language and detected_language in ALL_TARGET_LANGUAGES:
                language = detected_language
            confidence = llm_result["confidence"]
            reasoning = llm_result["reasoning"]

            if intent == "workspace_maintenance" and cls._is_test_execution_request(prompt):
                intent = "write_code"
                target_type = "test"
                print(f"\n🔧 Intent Router 硬覆盖：测试执行请求不应归类为 workspace_maintenance → write_code")

            if intent != "execute_operation" and cls._is_force_execute_operation(prompt):
                intent = "execute_operation"
                target_type = "infra"
                print(f"\n🔧 Intent Router 硬覆盖：操作执行请求不应归类为 {llm_result['intent']} → execute_operation")

            persona = cls.INTENT_TO_PERSONA.get(intent, "engineer")
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)

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
                chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)
                print("\n🧠 Intent Router（工作区工具任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")
                return intent, persona, chain

        for intent in ("explain_and_fix", "code_review", "delete_files"):
            if any(re.search(pattern, prompt_lower) for pattern in cls.INTENT_PATTERNS[intent]):
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)
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
                    chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)

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
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)

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
            chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)
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
                    chain = cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)

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
        return intent, cls.INTENT_TO_PERSONA[intent], cls._resolve_chain(intent, prompt, worker=model_name, matched_skill=matched_skill, language=language)

    @classmethod
    def detect_intent_multi(cls, prompt: str, model_name: str = "qwen"):
        """G8.0: 增强型意图识别 — 支持复合请求分解。

        与 detect_intent 相同的输入，但返回 CompoundPlan 而非单阶段元组。
        复合计划包含有序 Phase 列表，单阶段计划通过 fallback_* 字段表达。

        内部复用 detect_intent 的完整逻辑（LLM + Regex 降级），
        并读取 LLM 分类结果中的 is_compound / phases 字段。

        降级策略：
        - LLM 不可用 → Regex 降级（永远不返回复合）
        - phases 格式无效 → 降级单阶段
        - phases 不足 2 个 → 降级单阶段
        """
        from ._decompose import CompoundPlan

        if cls._is_project_test_request(prompt):
            intent, persona, chain = cls.detect_intent(prompt, model_name)
            return CompoundPlan(
                is_compound=False,
                fallback_intent=intent,
                fallback_persona=persona,
                fallback_chain=chain,
            )

        intent, persona, chain = cls.detect_intent(prompt, model_name)
        raw_result = cls._last_classify_result

        if raw_result and raw_result.get("is_compound"):
            raw_phases = raw_result.get("phases")
            if isinstance(raw_phases, list) and len(raw_phases) >= 2:
                try:
                    from ._decompose import Phase
                    phases = []
                    for p in raw_phases:
                        if isinstance(p, dict) and "type" in p and "prompt" in p:
                            phases.append(Phase(type=p["type"].strip(), prompt=p["prompt"].strip()))
                    if len(phases) >= 2:
                        print(f"\n🔀 IntentRouter: {len(phases)} 阶段复合请求")
                        for i, ph in enumerate(phases):
                            print(f"   阶段 {i + 1}: [{ph.type}] {ph.prompt[:80]}")
                        return CompoundPlan(is_compound=True, phases=phases)
                except Exception as e:
                    print(f"\n⚠️ IntentRouter: 复合分解异常 ({e})，降级单阶段")

        return CompoundPlan(
            is_compound=False,
            fallback_intent=intent,
            fallback_persona=persona,
            fallback_chain=chain,
        )

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
        language: str = "python",
    ) -> Dict:
        if detected_intent and detected_persona and detected_chain is not None:
            intent, persona, chain = detected_intent, detected_persona, list(detected_chain)
        else:
            intent, persona, chain = cls.detect_intent(prompt, model_name=worker)
        chain = cls._resolve_chain(intent, prompt, worker=worker, matched_skill=matched_skill, language=language)

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
        elif intent == "run_tests":
            mode = "TEST_EXECUTION"
            context_requirements = ["existing project test configuration", "workspace root"]
            capabilities = [
                {"id": "workspace.read", "available": workspace_available},
                {"id": "project.test", "available": True, "execution": "host_authorized"},
            ]
            side_effects = ["run the existing project test command"]
            approval = {"required": True, "before": ["project test command"]}
            validation = [
                "Only report a test result after the host returns an exit code and output",
                "Do not generate test files or modify project files for a test-only request",
            ]
            recovery = [
                "Stop when no safe project test command can be identified",
                "If tests fail, use the captured failure output only when the user requested repair",
            ]
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
            "implementation_plan_requirement": get_impl_plan_requirement(intent),
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