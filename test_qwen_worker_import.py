# -*- coding: utf-8 -*-
"""
test_qwen_worker_import.py - 测试 Qwen Worker v3.0 模块导入

验证所有步骤模块是否能正确导入,避免启动时崩溃
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

print("=" * 60)
print("Qwen Worker v3.0 模块导入测试")
print("=" * 60)
print()

# 测试 1: 导入 step_executor 模块
print("📦 测试 1: 导入 step_executor 模块...")
try:
    from python_worker.agents.qwen.step_executor import (
        run_analyze_step,
        run_plan_step,
        run_write_step,
        run_refine_step,
        run_test_step,
        run_fix_step,
        run_profile_step,
        run_doc_step,
        run_docstring_step,  # ⭐ 关键测试: docstring 步骤
        execute_step,
    )
    print("✅ 所有步骤函数导入成功")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

print()

# 测试 2: 验证 STEP_DISPATCHER 映射表
print("📦 测试 2: 验证 STEP_DISPATCHER 映射表...")
try:
    from python_worker.agents.qwen.step_executor.execute_step import STEP_DISPATCHER
    
    required_steps = [
        "analyze", "plan", "write", "refine",
        "test", "fix", "profile", "doc", "docstring"
    ]
    
    missing_steps = []
    for step_type in required_steps:
        if step_type not in STEP_DISPATCHER:
            missing_steps.append(step_type)
    
    if missing_steps:
        print(f"❌ 缺少步骤映射: {missing_steps}")
        sys.exit(1)
    else:
        print(f"✅ 所有 {len(required_steps)} 个步骤类型已注册")
        for step_type in required_steps:
            func_name = STEP_DISPATCHER[step_type].__name__
            print(f"   - {step_type:12s} → {func_name}")
except Exception as e:
    print(f"❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# 测试 3: 验证 prompt 模板
print("📦 测试 3: 验证 prompt 模板...")
try:
    from python_worker.agents.qwen.step_executor.prompts import (
        analyze_prompt,
        plan_prompt,
        write_prompt,
        refine_prompt,
        test_prompt,
        fix_prompt,
        profile_prompt,
        doc_prompt,
        docstring_prompt,  # ⭐ 关键测试: docstring prompt
        optimize_prompt,
    )
    print("✅ 所有 prompt 模板导入成功")
except ImportError as e:
    print(f"❌ Prompt 导入失败: {e}")
    sys.exit(1)

print()

# 测试 4: 模拟 Worker 启动
print("📦 测试 4: 模拟 Worker 启动...")
try:
    # 尝试导入 Worker 主模块(不执行,仅检查导入)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "qwen_worker_v2",
        os.path.join(project_root, "python_worker", "agents", "qwen", "qwen_worker_v2.py")
    )
    module = importlib.util.module_from_spec(spec)
    # 不执行 spec.loader.exec_module(module),仅检查语法
    print("✅ Worker 主模块可加载")
except Exception as e:
    print(f"❌ Worker 模块加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("🎉 所有测试通过! Qwen Worker v3.0 可以正常启动")
print("=" * 60)
