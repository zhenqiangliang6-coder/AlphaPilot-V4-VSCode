# -*- coding: utf-8 -*-
# intent_router.py — 官方 + 智能增强版（2026）
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
#    - 不允许出现“write 找不到 plan”、“refine 找不到 write”这种断链情况
#
# 本文件是 Worker 的核心智能模块，负责：
# 1. 识别用户意图
# 2. 选择人格
# 3. 决定执行链（analyze → plan → write → test → refine）
#
# ---------------------------------------------------------

import re
from typing import Dict, Tuple, List


class IntentRouter:
    """
    Intent Router — Worker 内部的智能决策模块
    ---------------------------------------------------------
    设计原则：
    - 工程任务优先级最高（write_code）
    - 文档任务优先级最低（generate_doc）
    - creative_writing 不覆盖工程任务
    - 执行链必须完整，不允许断链
    - 所有逻辑必须在 Worker 内部执行（Worker = 真相）
    """

    # =========================================================
    # ① 强制工程任务（最高优先级）
    # =========================================================
    FORCE_WRITE_CODE_PATTERNS = [
        r"创建.*模块", r"创建.*项目", r"创建.*文件", r"创建.*脚本",
        r"生成.*代码", r"实现.*功能", r"开发.*功能",
        r"写.*代码", r"编写.*代码", r"写一个.*模块",
        r"build.*module", r"create.*module", r"generate.*code",
        r"implement.*function", r"implement.*module",
        r"write.*script", r"create.*project",
    ]

    # =========================================================
    # ② 普通意图匹配（按优先级）
    # =========================================================
    INTENT_PATTERNS = {
        # ⭐ 对话/问答意图（高优先级，避免误判为代码生成）
        "chat": [
            r"你是谁", r"你是.*谁", r"介绍一下.*自己",
            r"hello", r"hi\b", r"hey\b",
            r"what.*are.*you", r"who.*are.*you",
            r"你好", r"您好", r"哈喽",
        ],

        "fix_code": [
            r"修复.*错误", r"解决.*bug", r"报错", r"无法运行",
            r"fix.*error", r"debug", r"exception", r"crash"
        ],

        "explain_code": [
            r"解释.*代码", r"说明.*这段", r"理解.*这个",
            r"explain.*code", r"what does.*mean"
        ],

        "creative_writing": [
            r"写.*诗", r"写.*故事", r"创作.*文章",
            r"write.*poem", r"write.*story"
        ],

        "analysis": [
            r"分析.*需求", r"评估.*方案",
            r"analyze.*requirement", r"evaluate.*solution"
        ],

        "architecture": [
            r"设计.*系统", r"架构.*方案",
            r"design.*system", r"architecture.*design"
        ],

        "refactor": [
            r"重构.*代码", r"优化.*结构",
            r"refactor.*code", r"optimize.*structure"
        ],

        # ⭐ generate_doc 放在最低优先级
        "generate_doc": [
            r"生成.*文档", r"写.*注释",
            r"generate.*documentation", r"write.*comments"
        ],
    }

    # =========================================================
    # ③ 意图 → 人格
    # =========================================================
    INTENT_TO_PERSONA = {
        "chat": "conversational",  # ⭐ 对话人格
        "write_code": "engineer",
        "fix_code": "engineer",
        "explain_code": "engineer",
        "creative_writing": "creator",
        "analysis": "engineer",
        "architecture": "engineer",
        "refactor": "engineer",
        "generate_doc": "engineer",
    }

    # =========================================================
    # ④ 意图 → 执行链（Execution Chain）
    # =========================================================
    INTENT_TO_CHAIN = {
        "chat": ["analyze", "write"],  # ⭐ 对话链路（简短）
        "write_code": ["analyze", "plan", "write", "test", "refine"],
        "fix_code": ["analyze", "fix", "test"],
        "explain_code": ["analyze", "write"],
        "creative_writing": ["write", "refine"],
        "analysis": ["analyze", "write"],
        "architecture": ["analyze", "plan", "write"],
        "refactor": ["analyze", "refine", "test"],
        "generate_doc": ["analyze", "write"],
    }

    @classmethod
    def detect_intent(cls, prompt: str) -> Tuple[str, str, List[str]]:
        """
        智能增强版意图识别（符合架构信条）
        ---------------------------------------------------------
        Worker = 真相：
            - 所有意图判断必须在 Worker 内部执行
        协议 = 宪法：
            - 执行链必须完整、可预测、可验证
        """

        if not prompt or not prompt.strip():
            return "write_code", "engineer", cls.INTENT_TO_CHAIN["write_code"]

        prompt_lower = prompt.lower().strip()

        # =========================================================
        # ① 强制工程任务（最高优先级）
        # =========================================================
        for pattern in cls.FORCE_WRITE_CODE_PATTERNS:
            if re.search(pattern, prompt_lower):
                intent = "write_code"
                persona = cls.INTENT_TO_PERSONA[intent]
                chain = cls.INTENT_TO_CHAIN[intent]

                print("\n🧠 Intent Router（强制工程任务识别）:")
                print(f"  意图: {intent}")
                print(f"  人格: {persona}")
                print(f"  执行链: {' → '.join(chain)}")

                return intent, persona, chain

        # =========================================================
        # ② 普通意图匹配（按优先级）
        # =========================================================
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower):
                    persona = cls.INTENT_TO_PERSONA[intent]
                    chain = cls.INTENT_TO_CHAIN[intent]

                    print("\n🧠 Intent Router 识别结果:")
                    print(f"  意图: {intent}")
                    print(f"  人格: {persona}")
                    print(f"  执行链: {' → '.join(chain)}")

                    return intent, persona, chain

        # =========================================================
        # ③ 默认：工程任务（完整链路）
        # =========================================================
        print("\n⚠️ Intent Router 未识别明确意图，使用默认工程链路")
        return "write_code", "engineer", cls.INTENT_TO_CHAIN["write_code"]

    @classmethod
    def get_persona_config(cls, persona_type: str) -> Dict:
        from .agents.qwen.personas import get_persona_config
        return get_persona_config(persona_type)


def detect_user_intent(prompt: str) -> Tuple[str, str, List[str]]:
    return IntentRouter.detect_intent(prompt)
