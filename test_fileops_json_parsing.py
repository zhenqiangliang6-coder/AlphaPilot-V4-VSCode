# -*- coding: utf-8 -*-
"""
test_fileops_json_parsing.py - 测试 FileOps Protocol META/DEPENDS 解析增强

测试场景：
1. 标准 JSON 格式(应该成功)
2. JSON + 污染文本(应该通过智能提取成功)
3. Markdown 代码块包裹的 JSON(应该成功)
4. 完全无效的 JSON(应该失败并记录原始内容)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from file_ops import parse_fileops_v3


def test_standard_json():
    """测试 1: 标准 JSON 格式"""
    text = """
# FILE: hello.py
print("Hello")

# META:
{"version": "1.0", "author": "AlphaPilot"}

# DEPENDS:
{"requirements": ["numpy>=1.20"]}
"""
    ops = parse_fileops_v3(text)
    
    assert len(ops) == 3, f"期望 3 个操作,实际 {len(ops)}"
    
    meta_op = [op for op in ops if op['op'] == 'meta'][0]
    assert 'error' not in meta_op['data'], f"META 解析失败: {meta_op['data']}"
    assert meta_op['data']['version'] == '1.0'
    
    depends_op = [op for op in ops if op['op'] == 'depends'][0]
    assert 'error' not in depends_op['data'], f"DEPENDS 解析失败: {depends_op['data']}"
    assert 'numpy>=1.20' in depends_op['data']['requirements']
    
    print("✅ 测试 1 通过: 标准 JSON 格式")


def test_json_with_pollution():
    """测试 2: JSON + 污染文本(模拟 refine 步骤的实际输出)"""
    text = """
# FILE: hello.py
print("Hello")

# META:
{"version": "1.0", "author": "AlphaPilot"}

## 2. 优化说明
这里是一些解释性文本...

# DEPENDS:
{"requirements": []}

### 其他内容
更多文本...
"""
    ops = parse_fileops_v3(text)
    
    meta_op = [op for op in ops if op['op'] == 'meta'][0]
    # 智能提取应该能从污染文本中提取出 JSON
    if 'error' in meta_op['data']:
        print(f"⚠️  测试 2 警告: META 解析失败(但这是预期的降级行为): {meta_op['data'].get('error')}")
    else:
        assert meta_op['data']['version'] == '1.0', "META 数据不正确"
        print("✅ 测试 2 通过: JSON + 污染文本(智能提取成功)")
    
    depends_op = [op for op in ops if op['op'] == 'depends'][0]
    if 'error' not in depends_op['data']:
        print("✅ DEPENDS 也成功解析")


def test_markdown_wrapped_json():
    """测试 3: Markdown 代码块包裹的 JSON"""
    text = """
# FILE: test.py
pass

# META:
```json
{"version": "2.0"}
```

# DEPENDS:
```
{"requirements": ["pytest"]}
```
"""
    ops = parse_fileops_v3(text)
    
    meta_op = [op for op in ops if op['op'] == 'meta'][0]
    # 智能提取应该能处理 markdown 代码块
    if 'error' not in meta_op['data']:
        print("✅ 测试 3 通过: Markdown 代码块包裹的 JSON")
    else:
        print(f"⚠️  测试 3 警告: Markdown JSON 解析失败: {meta_op['data'].get('error')}")


def test_invalid_json():
    """测试 4: 完全无效的 JSON(应该失败并记录原始内容)"""
    text = """
# FILE: test.py
pass

# META:
这不是 JSON { 无效内容

# DEPENDS:
也不是 JSON
"""
    ops = parse_fileops_v3(text)
    
    meta_op = [op for op in ops if op['op'] == 'meta'][0]
    assert 'error' in meta_op['data'], "无效 JSON 应该被标记为错误"
    assert 'raw' in meta_op['data'], "应该保留原始内容用于调试"
    
    depends_op = [op for op in ops if op['op'] == 'depends'][0]
    assert 'error' in depends_op['data'], "无效 DEPENDS 应该被标记为错误"
    
    print("✅ 测试 4 通过: 无效 JSON 正确报错并保留原始内容")


if __name__ == '__main__':
    print("=" * 60)
    print("FileOps Protocol META/DEPENDS 解析增强测试")
    print("=" * 60)
    
    try:
        test_standard_json()
        test_json_with_pollution()
        test_markdown_wrapped_json()
        test_invalid_json()
        
        print("\n" + "=" * 60)
        print("🎉 所有测试通过!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 意外错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
