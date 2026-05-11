# -*- coding: utf-8 -*-
"""
AlphaPilot OS v2.7 refine_step 多文件协议测试

目标：验证 refine_step 是否正确支持 # FILE: 协议
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_refine_step_imports():
    """测试1: 验证 refine_step 导入正常"""
    print("\n" + "=" * 60)
    print("测试1: 验证 refine_step 导入正常")
    print("=" * 60)
    
    try:
        # 尝试导入 refine_step 模块
        from python_worker.agents.qwen.step_executor import refine_step
        
        # 检查关键函数是否存在
        assert hasattr(refine_step, 'run_refine_step'), "缺少 run_refine_step 函数"
        assert hasattr(refine_step, '_parse_multi_file_protocol'), "缺少 _parse_multi_file_protocol 函数"
        assert hasattr(refine_step, '_infer_language'), "缺少 _infer_language 函数"
        
        print("✅ run_refine_step 函数存在")
        print("✅ _parse_multi_file_protocol 函数存在")
        print("✅ _infer_language 函数存在")
        
        return True
        
    except ImportError as e:
        if 'os' in str(e):
            print(f"❌ 导入失败: 缺少 os 模块 - {e}")
            return False
        else:
            print(f"❌ 导入失败: {e}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parse_multi_file_protocol():
    """测试2: 验证 # FILE: 协议解析"""
    print("\n" + "=" * 60)
    print("测试2: 验证 # FILE: 协议解析")
    print("=" * 60)
    
    try:
        # 直接导入解析函数
        import importlib.util
        refine_step_path = project_root / "python_worker" / "agents" / "qwen" / "step_executor" / "refine_step.py"
        
        spec = importlib.util.spec_from_file_location("refine_step", refine_step_path)
        refine_step_module = importlib.util.module_from_spec(spec)
        
        # 执行模块 (会触发 import os)
        try:
            spec.loader.exec_module(refine_step_module)
        except ModuleNotFoundError as e:
            if 'dotenv' in str(e):
                print("⚠️  警告: 缺少 dotenv 依赖,但不影响 _parse_multi_file_protocol 函数")
            else:
                raise
        
        # 模拟 LLM 输出 (多文件优化)
        llm_output = """
让我优化排序算法模块...

# FILE: sort_module/__init__.py
# 优化后的 __init__.py
ALGORITHM_BUBBLE = 'bubble'
ALGORITHM_QUICK = 'quick'

def sort(data, algorithm='quick'):
    from .sort_engine import sort_engine
    return sort_engine(data, algorithm)

# FILE: sort_module/algorithms.py
# 优化后的 algorithms.py
def bubble_sort(data):
    n = len(data)
    for i in range(n):
        for j in range(0, n - i - 1):
            if data[j] > data[j + 1]:
                data[j], data[j + 1] = data[j + 1], data[j]
    return data

def quick_sort(data):
    if len(data) <= 1:
        return data
    pivot = data[0]
    left = [x for x in data[1:] if x < pivot]
    right = [x for x in data[1:] if x >= pivot]
    return quick_sort(left) + [pivot] + quick_sort(right)
"""
        
        # 调用解析函数
        file_ops = refine_step_module._parse_multi_file_protocol(llm_output, intent="write_code", action="modify")
        
        assert len(file_ops) == 2, f"期望2个FileOp,实际{len(file_ops)}个"
        assert file_ops[0]['action'] == 'modify', f"期望 action=modify,实际 {file_ops[0]['action']}"
        assert file_ops[0]['path'] == "sort_module/__init__.py"
        assert file_ops[1]['path'] == "sort_module/algorithms.py"
        
        print(f"✅ 解析到 {len(file_ops)} 个 FileOp:")
        for op in file_ops:
            print(f"   - {op['action']} {op['path']} ({len(op['content'])} bytes)")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_infer_language():
    """测试3: 验证语言推断"""
    print("\n" + "=" * 60)
    print("测试3: 验证语言推断")
    print("=" * 60)
    
    try:
        import importlib.util
        refine_step_path = project_root / "python_worker" / "agents" / "qwen" / "step_executor" / "refine_step.py"
        
        spec = importlib.util.spec_from_file_location("refine_step", refine_step_path)
        refine_step_module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(refine_step_module)
        except ModuleNotFoundError:
            pass  # 忽略 dotenv 错误
        
        # 测试不同扩展名
        test_cases = [
            ("test.py", "python"),
            ("test.ts", "typescript"),
            ("test.js", "javascript"),
            ("test.java", "java"),
            ("test.go", "go"),
            ("test.md", "markdown"),
            ("test.json", "json"),
            ("test.unknown", "python"),  # 未知类型默认 python
        ]
        
        all_passed = True
        for file_path, expected_lang in test_cases:
            result = refine_step_module._infer_language(file_path)
            if result == expected_lang:
                print(f"✅ {file_path} -> {result}")
            else:
                print(f"❌ {file_path} -> {result} (期望: {expected_lang})")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n🚀 AlphaPilot OS v2.7 refine_step 多文件协议测试\n")
    print("=" * 60)
    print("目标: 验证 refine_step 是否正确支持 # FILE: 协议")
    print("=" * 60)
    
    tests = [
        ("refine_step 导入正常", test_refine_step_imports),
        ("# FILE: 协议解析", test_parse_multi_file_protocol),
        ("语言推断", test_infer_language),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {name}")
    
    print("\n" + "=" * 60)
    print(f"总计: {passed}/{total} 通过")
    print("=" * 60)
    
    if passed == total:
        print("\n[SUCCESS] 所有测试通过! refine_step v2.7 已就绪")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} 个测试失败,请检查代码")
        return 1


if __name__ == "__main__":
    exit(main())
