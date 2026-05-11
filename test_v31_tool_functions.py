# -*- coding: utf-8 -*-
"""
AlphaPilot OS v3.1.1 FileOps 工具函数测试
测试 filter_valid_file_ops 和 get_python_files 的功能
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from file_ops import filter_valid_file_ops, get_python_files

def test_filter_valid_file_ops():
    """测试 filter_valid_file_ops 函数"""
    
    print("🚀 AlphaPilot OS v3.1.1 FileOps 工具函数测试\n")
    
    # 模拟包含内部元数据的 final_file_ops
    mock_file_ops = [
        {
            "op": "create",
            "path": "calculator.py",
            "content": "def add(a, b): return a + b",
            "from_step": "write"
        },
        {
            "op": "create",
            "path": "utils.py",
            "content": "def is_even(n): return n % 2 == 0",
            "from_step": "write"
        },
        {
            "op": "meta",
            "path": None,  # ❌ path 为 None
            "content": "",
            "_internal": True
        },
        {
            "op": "depends",
            "path": None,  # ❌ path 为 None
            "content": "",
            "data": {"files": ["numpy>=1.20"]},
            "_internal": True
        },
        {
            "op": "create",
            "path": "README.md",
            "content": "# Test Project",
            "from_step": "write"
        },
        {
            "op": "create",
            "path": "",  # ❌ path 为空字符串
            "content": "test",
            "from_step": "write"
        }
    ]
    
    print(f"📋 模拟 FileOps 总数: {len(mock_file_ops)}")
    print()
    
    # 测试 1: 默认过滤（排除内部元数据）
    valid_ops = filter_valid_file_ops(mock_file_ops)
    print(f"✅ 测试 1: 过滤后有效 FileOps: {len(valid_ops)}")
    for fo in valid_ops:
        print(f"   - {fo['path']} (op: {fo['op']})")
    
    assert len(valid_ops) == 3, f"期望 3 个有效操作，实际 {len(valid_ops)}"
    assert all(fo.get("path") for fo in valid_ops), "所有有效操作的 path 不应为空"
    assert all(not fo.get("_internal", False) for fo in valid_ops), "有效操作不应包含内部元数据"
    print("   ✅ 通过\n")
    
    # 测试 2: 不排除内部元数据（但仍会过滤掉 path 为 None 或空的）
    all_ops = filter_valid_file_ops(mock_file_ops, exclude_internal=False)
    print(f"✅ 测试 2: 不排除内部元数据: {len(all_ops)}")
    for fo in all_ops:
        print(f"   - {fo.get('path', 'N/A')} (op: {fo['op']}, _internal: {fo.get('_internal', False)})")
    
    # 注意：即使不排除内部元数据，path 为 None 或空的仍会被过滤
    assert len(all_ops) == 3, f"期望 3 个操作（排除空 path），实际 {len(all_ops)}"
    print("   ✅ 通过\n")
    
    # 测试 3: 空列表
    empty_result = filter_valid_file_ops([])
    assert empty_result == [], "空列表应返回空列表"
    print("✅ 测试 3: 空列表处理正确")
    print("   ✅ 通过\n")
    
    # 测试 4: None 列表
    none_result = filter_valid_file_ops(None)
    assert none_result == [], "None 应返回空列表"
    print("✅ 测试 4: None 处理正确")
    print("   ✅ 通过\n")

def test_get_python_files():
    """测试 get_python_files 函数"""
    
    mock_file_ops = [
        {"op": "create", "path": "calculator.py", "content": "..."},
        {"op": "create", "path": "utils.py", "content": "..."},
        {"op": "create", "path": "README.md", "content": "..."},
        {"op": "create", "path": "test_calc.py", "content": "..."},
        {"op": "meta", "path": None, "content": "", "_internal": True}
    ]
    
    py_files = get_python_files(mock_file_ops)
    print(f"✅ 测试 5: Python 文件数量: {len(py_files)}")
    for pf in py_files:
        print(f"   - {pf['path']}")
    
    assert len(py_files) == 3, f"期望 3 个 Python 文件，实际 {len(py_files)}"
    assert all(pf["path"].endswith(".py") for pf in py_files), "所有文件应以 .py 结尾"
    print("   ✅ 通过\n")

if __name__ == "__main__":
    try:
        test_filter_valid_file_ops()
        test_get_python_files()
        
        print("=" * 60)
        print("🎉 所有测试通过！v3.1.1 FileOps 工具函数工作正常！")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
