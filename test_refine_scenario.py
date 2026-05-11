# -*- coding: utf-8 -*-
"""
test_refine_scenario.py - 模拟真实 refine 步骤的 FileOps 解析场景

基于用户提供的日志中的实际输出进行测试
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_worker'))

from file_ops import parse_fileops_v3


def test_real_refine_output():
    """测试真实 refine 步骤的输出(来自用户日志)"""
    
    # 这是从用户日志中提取的实际 refine 输出片段
    refine_output = """
# FILE: hello_script.py
```python
import os

def create_hello_script(file_path: str) -> bool:
    content = 'print("Hello AlphaPilot")'
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        handle_error(e)
        return False

if __name__ == "__main__":
    main()
```

# META:
{"version": "1.0", "author": "AlphaPilot"}

## 2. 优化说明

1. 将 `main()` 函数重命名为更清晰的 `greet()` 函数，使功能更明确
2. 添加了函数文档字符串，提高可读性和可维护性

# DEPENDS:
{"requirements": []}

### 其他优化内容...
"""
    
    print("正在解析真实 refine 输出...")
    ops = parse_fileops_v3(refine_output)
    
    print(f"\n解析结果: 共 {len(ops)} 个 FileOps")
    for i, op in enumerate(ops):
        print(f"  [{i}] op={op['op']}, path={op.get('path', 'N/A')}")
        if op['op'] in ['meta', 'depends']:
            if 'error' in op.get('data', {}):
                print(f"      ❌ 错误: {op['data']['error']}")
                print(f"      原始内容前 100 字符: {op['data'].get('raw', '')[:100]}...")
            else:
                print(f"      ✅ 成功: {op['data']}")
    
    # 验证关键操作
    file_ops = [op for op in ops if op['op'] == 'create']
    meta_ops = [op for op in ops if op['op'] == 'meta']
    depends_ops = [op for op in ops if op['op'] == 'depends']
    
    assert len(file_ops) >= 1, "应该至少有一个文件操作"
    print(f"\n✅ 文件操作: {len(file_ops)} 个")
    
    if meta_ops:
        meta_op = meta_ops[0]
        if 'error' not in meta_op.get('data', {}):
            print(f"✅ META 解析成功: {meta_op['data']}")
        else:
            print(f"⚠️  META 解析失败(但已记录原始内容): {meta_op['data'].get('error')}")
    
    if depends_ops:
        depends_op = depends_ops[0]
        if 'error' not in depends_op.get('data', {}):
            print(f"✅ DEPENDS 解析成功: {depends_op['data']}")
        else:
            print(f"⚠️  DEPENDS 解析失败(但已记录原始内容): {depends_op['data'].get('error')}")
    
    print("\n" + "=" * 60)
    print("🎉 真实场景测试完成!")
    print("=" * 60)


if __name__ == '__main__':
    test_real_refine_output()
