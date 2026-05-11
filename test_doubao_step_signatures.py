# -*- coding: utf-8 -*-
# test_doubao_step_signatures.py
"""
验证所有 Doubao 步骤处理器的函数签名兼容性
"""

import sys
import inspect

sys.path.insert(0, '.')

from python_worker.agents.Volcengine.step_executor import (
    run_analyze_step,
    run_plan_step,
    run_write_step,
    run_refine_step,
    run_test_step,
    run_fix_step,
    run_doc_step,
    run_docstring_step,
    run_profile_step,
)

print("=" * 60)
print("Doubao Worker v3.2 步骤处理器函数签名验证")
print("=" * 60)
print()

steps = [
    ('analyze', run_analyze_step),
    ('plan', run_plan_step),
    ('write', run_write_step),
    ('refine', run_refine_step),
    ('test', run_test_step),
    ('fix', run_fix_step),
    ('doc', run_doc_step),
    ('docstring', run_docstring_step),
    ('profile', run_profile_step),
]

all_passed = True

for name, func in steps:
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    has_api_func = 'api_func' in params
    
    status = '✅' if has_api_func else '❌'
    print(f"{status} {name:12s}: {params}")
    
    if not has_api_func:
        all_passed = False

print()
print("=" * 60)

if all_passed:
    print("✅ 所有步骤处理器都支持 api_func 参数")
    print("=" * 60)
    sys.exit(0)
else:
    print("❌ 存在步骤处理器缺少 api_func 参数")
    print("=" * 60)
    sys.exit(1)
