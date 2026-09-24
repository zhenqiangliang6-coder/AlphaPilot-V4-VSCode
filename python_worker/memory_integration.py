# -*- coding: utf-8 -*-
"""
AlphaPilot 记忆集成层 - Worker 执行链集成模块
架构：海马体-新皮层协作模式
作者：World-Class AI Architect
版本：v1.0.0

功能：
- 在任务开始前调用 build_memory_context → 注入记忆上下文到 Prompt
- 在任务完成后调用 should_remember → 保存新的偏好、事实、经验
- 提供统一的记忆注入接口
"""

import json
from typing import Optional, Dict, List
from dataclasses import dataclass

# 延迟导入，避免循环依赖
_memory_service = None


def get_memory_service():
    """获取记忆服务单例（延迟导入）"""
    global _memory_service
    if _memory_service is None:
        try:
            from .memory_service import MemoryService, MemoryItem, MemoryType
            _memory_service = MemoryService()
        except Exception as e:
            print(f"[WARN] 记忆服务初始化失败: {e}")
            return None
    return _memory_service


@dataclass
class MemoryContext:
    """记忆上下文数据"""
    user_id: str
    task_id: str
    original_prompt: str
    memory_context: str = ""  # 注入的记忆上下文
    has_memory: bool = False  # 是否有相关记忆


class MemoryIntegration:
    """
    记忆集成器 - 在 Worker 执行链中集成记忆服务
    
    使用方式:
        # 任务开始前
        memory_ctx = MemoryIntegration.build_context(user_id, task_id, prompt)
        enhanced_prompt = memory_ctx.memory_context + "\n\n" + prompt
        
        # 任务完成后
        MemoryIntegration.save_task_insights(user_id, task_id, result, context)
    """
    
    @staticmethod
    def build_context(
        user_id: str,
        task_id: str,
        prompt: str,
        max_tokens: int = 2000
    ) -> MemoryContext:
        """
        构建记忆上下文（任务开始前调用）
        
        参数:
            user_id: 用户ID
            task_id: 任务ID
            prompt: 原始提示词
            max_tokens: 最大 token 数
            
        返回:
            MemoryContext: 包含记忆上下文的对象
        """
        service = get_memory_service()
        if service is None:
            return MemoryContext(
                user_id=user_id,
                task_id=task_id,
                original_prompt=prompt,
                memory_context="",
                has_memory=False
            )
        
        try:
            # 调用记忆服务构建上下文
            memory_context = service.build_memory_context(
                user_id=user_id,
                current_query=prompt,
                max_tokens=max_tokens
            )
            
            has_memory = len(memory_context.strip()) > 0
            
            if has_memory:
                print(f"[MEMORY] ✅ 为任务 {task_id} 注入记忆上下文 ({len(memory_context)} 字符)")
            else:
                print(f"[MEMORY] ℹ️ 任务 {task_id} 无相关记忆")
            
            return MemoryContext(
                user_id=user_id,
                task_id=task_id,
                original_prompt=prompt,
                memory_context=memory_context,
                has_memory=has_memory
            )
        except Exception as e:
            print(f"[MEMORY] ⚠️ 构建记忆上下文失败: {e}")
            return MemoryContext(
                user_id=user_id,
                task_id=task_id,
                original_prompt=prompt,
                memory_context="",
                has_memory=False
            )
    
    @staticmethod
    def enhance_prompt(prompt: str, memory_context: MemoryContext) -> str:
        """
        增强提示词（将记忆上下文注入到 Prompt 中）
        
        参数:
            prompt: 原始提示词
            memory_context: 记忆上下文对象
            
        返回:
            str: 增强后的提示词
        """
        if not memory_context.has_memory:
            return prompt
        
        # 构建增强提示词
        enhanced = f"""# 🧠 记忆上下文（来自 AlphaPilot 记忆中枢）

{memory_context.memory_context}

---

# 📝 用户请求

{prompt}
"""
        return enhanced
    
    @staticmethod
    def save_task_insights(
        user_id: str,
        task_id: str,
        task_result: Dict,
        context: Dict = None
    ) -> bool:
        """
        保存任务洞察（任务完成后调用）
        
        参数:
            user_id: 用户ID
            task_id: 任务ID
            task_result: 任务结果
            context: 任务上下文
            
        返回:
            bool: 是否成功保存
        """
        service = get_memory_service()
        if service is None:
            return False
        
        context = context or {}
        
        try:
            # 提取任务中的关键信息
            insights = MemoryIntegration._extract_insights(task_result, context)
            
            saved_count = 0
            for insight in insights:
                # 守门人决策
                decision = service.should_remember(
                    user_id=user_id,
                    content=insight["content"],
                    context={
                        "task_id": task_id,
                        "task_outcome": insight.get("outcome", "success"),
                        "task_complexity": insight.get("complexity", 0.5)
                    }
                )
                
                if decision.remember:
                    # 导入 MemoryItem 和 MemoryType
                    from .memory_service import MemoryItem, MemoryType
                    
                    # 创建记忆
                    memory = MemoryItem(
                        user_id=user_id,
                        content=insight["content"],
                        memory_type=decision.memory_type or MemoryType.INSIGHT,
                        importance_score=decision.importance,
                        domain_tags=insight.get("tags", [])
                    )
                    
                    # 保存
                    memory_id = service.save_memory(memory)
                    saved_count += 1
                    print(f"[MEMORY] ✅ 保存记忆: {memory_id} ({decision.reason})")
            
            print(f"[MEMORY] 📊 任务 {task_id} 共保存 {saved_count} 条记忆")
            return saved_count > 0
            
        except Exception as e:
            print(f"[MEMORY] ⚠️ 保存任务洞察失败: {e}")
            return False
    
    @staticmethod
    def _extract_insights(task_result: Dict, context: Dict) -> List[Dict]:
        """
        从任务结果中提取洞察
        
        参数:
            task_result: 任务结果
            context: 任务上下文
            
        返回:
            List[Dict]: 洞察列表
        """
        insights = []
        
        # 1. 提取成功的代码生成经验
        if task_result.get("status") == "success":
            # 提取生成的代码
            code_content = task_result.get("content", "")
            if code_content and len(code_content) > 100:
                insights.append({
                    "content": f"成功生成代码: {code_content[:200]}...",
                    "outcome": "success",
                    "complexity": 0.7,
                    "tags": ["code-generation", "success"]
                })
            
            # 提取修复经验
            fix_steps = [s for s in task_result.get("steps", []) if s.get("type") == "fix"]
            if fix_steps:
                for fix in fix_steps:
                    insights.append({
                        "content": f"修复了代码问题: {fix.get('output', '')[:200]}",
                        "outcome": "success",
                        "complexity": 0.6,
                        "tags": ["bug-fix", "debugging"]
                    })
        
        # 2. 提取用户偏好（从上下文中）
        if "preferred_language" in context:
            insights.append({
                "content": f"用户偏好使用 {context['preferred_language']} 进行开发",
                "outcome": "success",
                "complexity": 0.3,
                "tags": ["preference", "coding-style"]
            })
        
        # 3. 提取技术事实
        if "technical_facts" in context:
            for fact in context["technical_facts"]:
                insights.append({
                    "content": fact,
                    "outcome": "success",
                    "complexity": 0.5,
                    "tags": ["technical-fact"]
                })
        
        return insights


# ============================================================
# 便捷函数（供 Worker 直接调用）
# ============================================================

def build_memory_context(user_id: str, task_id: str, prompt: str) -> MemoryContext:
    """
    构建记忆上下文（便捷函数）
    
    使用示例:
        memory_ctx = build_memory_context(user_id, task_id, prompt)
        enhanced_prompt = enhance_prompt_with_memory(prompt, memory_ctx)
    """
    return MemoryIntegration.build_context(user_id, task_id, prompt)


def enhance_prompt_with_memory(prompt: str, memory_ctx: MemoryContext) -> str:
    """
    增强提示词（便捷函数）
    
    使用示例:
        memory_ctx = build_memory_context(user_id, task_id, prompt)
        enhanced_prompt = enhance_prompt_with_memory(prompt, memory_ctx)
    """
    return MemoryIntegration.enhance_prompt(prompt, memory_ctx)


def save_task_memories(user_id: str, task_id: str, result: Dict, context: Dict = None) -> bool:
    """
    保存任务记忆（便捷函数）
    
    使用示例:
        # 任务完成后
        save_task_memories(user_id, task_id, result, context)
    """
    return MemoryIntegration.save_task_insights(user_id, task_id, result, context)
