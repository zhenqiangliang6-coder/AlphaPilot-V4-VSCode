# -*- coding: utf-8 -*-
# test_worker_context_injection.py
# ⭐ AlphaPilot OS v3.5 Worker 上下文注入测试脚本
# 用途：验证 prompt 注入功能是否正常工作

import sys
import os
import json

# 直接导入 prompts.py（避免复杂的相对导入）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker', 'agents', 'qwen', 'step_executor'))

# 手动加载 prompts 模块
import importlib.util
spec = importlib.util.spec_from_file_location("prompts", os.path.join(os.path.dirname(__file__), 'python_worker', 'agents', 'qwen', 'step_executor', 'prompts.py'))
prompts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prompts)

inject_memory_context = prompts.inject_memory_context
analyze_prompt = prompts.analyze_prompt
write_prompt = prompts.write_prompt

print('🧪 AlphaPilot OS v3.5 Worker 上下文注入测试\n')
print('=' * 60)

# 测试 1：inject_memory_context 函数
print('\n📝 测试 1：inject_memory_context 函数')
print('-' * 60)

test_context = {
    "memory": {
        "project_context": {
            "name": "测试项目 V3.5",
            "tech_stack": {
                "framework": "FastAPI + React",
                "languages": ["Python", "JavaScript"],
                "code_style": "snake_case"
            }
        },
        "memory_context": {
            "user_preferences": {
                "language": "zh-CN",
                "preferred_model": "qwen-turbo",
                "explanation_style": "detailed"
            },
            "project_memories": [
                {
                    "type": "rule",
                    "content": "所有 API 必须使用 async/await 异步模式",
                    "importance": 5
                },
                {
                    "type": "rule",
                    "content": "所有文件命名必须使用 snake_case",
                    "importance": 4
                }
            ],
            "similar_tasks": [
                {
                    "prompt": "帮我创建一个 FastAPI 用户认证模块，包含登录和注册功能",
                    "result_summary": "创建了 auth 模块，包含 models.py 和 routes.py",
                    "steps": [
                        {
                            "step_type": "analyze",
                            "output": {"analysis": "需要实现用户注册、登录、JWT 认证"}
                        }
                    ]
                },
                {
                    "prompt": "实现 JWT Token 生成和验证逻辑",
                    "result_summary": "实现了 JWT 逻辑",
                    "steps": []
                }
            ],
            "recent_tasks": [
                {
                    "prompt": "创建数据库迁移脚本",
                    "result_summary": "创建了 Alembic 迁移"
                }
            ]
        }
    }
}

memory_text = inject_memory_context(test_context)
print("✅ 上下文注入成功！")
print("\n生成的记忆文本:")
print(memory_text)

# 测试 2：analyze_prompt 带上下文
print('\n\n📝 测试 2：analyze_prompt 带上下文')
print('-' * 60)

analyze_result = analyze_prompt("帮我创建一个用户登录接口", context=test_context)
print("✅ analyze_prompt 生成成功！")
print(f"\nPrompt 长度: {len(analyze_result)} 字符")
print(f"\nPrompt 预览 (前800字符):")
print(analyze_result[:800])

# 测试 3：write_prompt 带上下文
print('\n\n📝 测试 3：write_prompt 带上下文')
print('-' * 60)

plan_text = """
1. 创建 User 模型
2. 实现登录接口
3. 实现 JWT Token 生成
"""

write_result = write_prompt(plan_text, context=test_context)
print("✅ write_prompt 生成成功！")
print(f"\nPrompt 长度: {len(write_result)} 字符")
print(f"\nPrompt 预览 (前800字符):")
print(write_result[:800])

# 测试 4：空上下文（降级测试）
print('\n\n📝 测试 4：空上下文（降级测试）')
print('-' * 60)

empty_context = {}
memory_text_empty = inject_memory_context(empty_context)
print(f"✅ 空上下文处理成功，返回长度: {len(memory_text_empty)}")

analyze_no_context = analyze_prompt("测试任务", context=None)
print(f"✅ None 上下文处理成功，Prompt 长度: {len(analyze_no_context)}")

print('\n' + '=' * 60)
print('🎉 所有测试通过！Worker 上下文注入功能正常')
print('=' * 60)
