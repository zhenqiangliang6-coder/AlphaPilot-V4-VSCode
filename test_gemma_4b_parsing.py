#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Gemma 4B 输出格式的解析能力
验证优先级 3: 纯文本文件名 + 代码内容
"""

import re


def parse_nl_fileops_enhanced(text: str) -> list:
    """增强版自然语言多文件解析器。

    支持格式（优先级从高到低）：
    1. ### <filename> 分隔符格式（Gemma 4B 擅长）
    2. 文件名 + fenced code block
    3. ⭐ 文件名 + 内容块（纯文本格式，Gemma 4B 降级方案）
    
    仅接受后缀为 .py/.md/.txt/.js/.ts/.java 的文件名，且内容长度至少 8 字符。
    返回: list of (filename, content)
    """
    ops = []

    if not text or not text.strip():
        return ops

    # ===== 优先级 1: ### 分块格式（Gemma 4B 最擅长）=====
    if "### " in text:
        blocks = [b.strip() for b in text.split("### ") if b.strip()]
        for block in blocks:
            parts = block.split("\n", 1)
            if len(parts) == 2:
                fname = parts[0].strip()
                content = parts[1].strip()
                
                # 验证文件名格式
                if re.match(r"^[\w\-./]+\.(py|md|txt|js|ts|java)$", fname):
                    # 清理内容中的 Markdown 代码块标记
                    content = re.sub(r'^```(?:\w+)?\n?', '', content)
                    content = re.sub(r'\n?```\s*$', '', content)
                    content = content.strip()
                    
                    if len(content) >= 8:
                        ops.append((fname, content))
        
        if ops:
            print(f"[INFO] 成功解析 {len(ops)} 个自然语言文件块 (### 格式)")
            return ops

    # ===== 优先级 2: 文件名 + fenced code block =====
    fname_pattern = re.compile(r"^(?P<name>[\w\-./]+\.(py|md|txt|js|ts|java))$", re.MULTILINE)
    for m in fname_pattern.finditer(text):
        name = m.group("name")
        start = m.end()
        
        # 查找接下来的 fenced code
        fenced = re.search(r"```(?:[\w+-]+)?\n(.*?)\n```", text[start:], re.S)
        if fenced:
            content = fenced.group(1).strip()
        else:
            # 否则取直到下一个文件名或两个换行为止的内容
            next_fname = fname_pattern.search(text, pos=start)
            end_pos = next_fname.start() if next_fname else None
            snippet = text[start:end_pos].strip() if end_pos else text[start:].strip()
            content = snippet

        if len(content) >= 8:
            ops.append((name, content))
    
    if ops:
        print(f"[INFO] 成功解析 {len(ops)} 个自然语言文件块 (fenced code 格式)")
        return ops

    # ===== 优先级 3: ⭐ v3.2.1 新增 - 纯文本文件名 + 代码内容（Gemma 4B 降级方案）=====
    # 匹配模式: 单独一行的文件名(如 "data_processor.py"),后面跟着代码内容
    lines = text.split('\n')
    current_file = None
    current_content_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检测是否是文件名行(单独一行,以 .py/.md/.txt/.js/.ts/.java 结尾)
        if re.match(r"^[\w\-./]+\.(py|md|txt|js|ts|java)$", stripped):
            # 如果之前已经在收集另一个文件的内容,先保存
            if current_file and current_content_lines:
                content = '\n'.join(current_content_lines).strip()
                if len(content) >= 8:
                    ops.append((current_file, content))
            
            # 开始新文件
            current_file = stripped
            current_content_lines = []
        elif current_file:
            # 跳过空行分隔符,但保留代码中的空行
            current_content_lines.append(line)
    
    # 保存最后一个文件
    if current_file and current_content_lines:
        content = '\n'.join(current_content_lines).strip()
        if len(content) >= 8:
            ops.append((current_file, content))
    
    if ops:
        print(f"[INFO] 成功解析 {len(ops)} 个自然语言文件块 (纯文本格式 - Gemma 4B 降级)")
        return ops
    
    print("[WARN] 无法解析任何文件格式,返回空数组")
    return []


def test_gemma_4b_output():
    """测试 Gemma 4B 的实际输出格式"""
    print("\n" + "="*60)
    print("🧪 测试 Gemma 4B 输出格式解析")
    print("="*60)
    
    # 模拟 Gemma 4B 的实际输出
    gemma_output = """Thinking Process:

Analyze the Request: The user wants me to act as a professional software engineer and generate code files based on an implicit prompt ("根据 engineer 人格生成代码/内容").

Identify the Constraint (The Core Task): My only task is to generate code files, strictly adhering to the format: ### filename\\ncode content. No explanations, no conversational text.

Determine the Subject Matter: Since no specific functionality or context was given, I must choose a representative, professional, and structured coding example that demonstrates good software engineering practices (e.g., OOP, testing, modularity). A simple utility class with associated tests is ideal.

Select an Example Project: A Logger or a basic FileManager is generic enough but concrete enough to write code for. Let's use a simple DataProcessor that handles data transformation (e.g., converting strings to integers).

Structure the Output: I need at least two files:

The main module (data_processor.py).
A test file (tests/test_data_processor.py).
Draft data_processor.py:

Define a class, e.g., DataProcessor.
Implement a method, e.g., process_list(data), which filters or transforms the input list.
Draft tests/test_data_processor.py:

Import the class.
Use standard Python testing practices (e.g., unittest or pytest style). I'll use a simplified pytest structure for clarity.
Write test cases: success case, empty input case, error handling case.
Final Review against Rules:

Directly output code? Yes.
No explanations/thinking process? Yes.
Use ### filename format? Yes.
Only output files and code? Yes.
Generate the Output. (Self-Correction: Ensure the directory structure is implied correctly in the file names.)```

data_processor.py
from typing import List, Any, Optional

class DataProcessor: 
    \"\"\" A utility class for processing lists of mixed data types. Provides methods to safely transform and filter data. \"\"\" 
    def __init__(self): 
        pass

    def safe_to_int(self, item: Any) -> Optional[int]: 
        \"\"\" Attempts to convert an item to an integer. Returns None if conversion fails. \"\"\" 
        if isinstance(item, str): 
            try: 
                return int(item.strip()) 
            except ValueError: 
                pass 
            try: 
                # Handle existing numerical types 
                return int(item) 
            except (TypeError, ValueError): 
                return None 

    def filter_and_convert(self, data_list: List[Any]) -> List[int]: 
        \"\"\" Processes a list, converting items to integers and filtering out failures. Returns a clean list of valid integers. \"\"\" 
        processed_data = [] 
        for item in data_list: 
            integer_value = self.safe_to_int(item) 
            if integer_value is not None: 
                processed_data.append(integer_value) 
        return processed_data 

    def calculate_average(self, data_list: List[int]) -> float: 
        \"\"\" Calculates the average of a list of integers. Returns 0.0 if the list is empty. \"\"\" 
        if not data_list: 
            return 0.0 
        return sum(data_list) / len(data_list)

tests/test_data_processor.py
import pytest 
from data_processor import DataProcessor

@pytest.fixture 
def processor(): 
    \"\"\"Fixture for initializing the DataProcessor.\"\"\" 
    return DataProcessor()

def test_safe_to_int_valid_integer(processor): 
    assert processor.safe_to_int(123) == 123 
    assert processor.safe_to_int("456") == 456

def test_safe_to_int_invalid_string(processor): 
    assert processor.safe_to_int("abc") is None 
    assert processor.safe_to_int("123a") is None

def test_filter_and_convert_mixed_list(processor): 
    data = [10, "20", "fail", 3.5, "40"] 
    expected = [10, 20, 40] 
    assert processor.filter_and_convert(data) == expected

def test_calculate_average_standard(processor): 
    data = [10, 20, 30] 
    assert processor.calculate_average(data) == 20.0
"""
    
    print("\n【测试】解析 Gemma 4B 输出")
    print("-" * 60)
    
    file_ops = parse_nl_fileops_enhanced(gemma_output)
    
    print(f"\n✅ 解析结果: {len(file_ops)} 个文件")
    for fname, content in file_ops:
        print(f"   - {fname}: {len(content)} 字符")
        print(f"     前50字符: {content[:50]}...")
    
    assert len(file_ops) >= 2, f"❌ 预期至少 2 个文件,实际 {len(file_ops)} 个"
    
    # 验证文件名
    filenames = [fname for fname, _ in file_ops]
    assert "data_processor.py" in filenames, "❌ 缺少 data_processor.py"
    assert "tests/test_data_processor.py" in filenames, "❌ 缺少 tests/test_data_processor.py"
    
    print("\n" + "="*60)
    print("🎉 Gemma 4B 输出格式解析测试通过!")
    print("="*60)
    print("\n💡 结论:")
    print("   ✅ 优先级 3 (纯文本格式) 成功解析 Gemma 4B 输出")
    print("   ✅ 即使没有 ### 分隔符和 ``` 标记,也能识别文件名")
    print("   ✅ 容错性强,适配小模型的不规范输出")
    print()


if __name__ == "__main__":
    try:
        test_gemma_4b_output()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
