#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Gemma 4B 真实输出的解析能力
使用从日志中复制的真实输出内容
"""

import re


def parse_files(text):
    """简化版解析器,只测试 ### 格式"""
    ops = []
    
    # 优先级 1: 直接匹配 ### filename
    blocks = [b.strip() for b in text.split('### ') if b.strip()]
    
    for block in blocks:
        lines = block.split('\n', 1)
        if len(lines) < 2:
            continue
        
        fname = lines[0].strip()
        content = lines[1].strip()
        
        # 验证文件名是否合法
        if re.match(r'^[\w\-./]+\.(py|md|txt|js|ts|java)$', fname):
            ops.append((fname, content))
            print(f"  ✅ 找到文件: {fname} ({len(content)} 字符)")
    
    return ops


def test_gemma_real_output():
    """测试 Gemma 4B 的真实输出(来自 LM Studio 对话)"""
    print("\n" + "="*80)
    print("🧪 测试 Gemma 4B 真实输出解析(标准 ### 分隔格式)")
    print("="*80)
    
    # 从日志中复制的 Gemma 4B 真实输出
    gemma_output = """
The user wants me to act as a professional software engineer and generate multiple files for a calculator module, following a strict format.

Files required:
1.  `calculator.py`: The main module logic.
2.  `tests/test_calculator.py`: Unit tests for the module.
3.  `README.md`: Documentation for the project.

Constraints checklist:
1.  Must use `###` as file separator. (Yes)
2.  No explanation, thinking process, or meta-description. (Yes)
3.  Directly output code files starting with `###`. (Yes)

Plan:
1. Implement basic calculator functions (e.g., add, subtract, multiply, divide) in `calculator.py`.
2. Write unit tests covering these functions in `tests/test_calculator.py`.
3. Create a standard README structure explaining the project and usage in `README.md`.### calculator.py
class Calculator:
    \"\"\"
    A simple calculator class providing basic arithmetic operations.
    \"\"\"

    def add(self, a: float, b: float) -> float:
        \"\"\"Adds two numbers.\"\"\"
        return a + b

    def subtract(self, a: float, b: float) -> float:
        \"\"\"Subtracts the second number from the first.\"\"\"
        return a - b

    def multiply(self, a: float, b: float) -> float:
        \"\"\"Multiplies two numbers.\"\"\"
        return a * b

    def divide(self, a: float, b: float) -> float:
        \"\"\"Divides the first number by the second. Raises ValueError if division by zero occurs.\"\"\"
        if b == 0:
            raise ValueError("Cannot divide by zero.")
        return a / b

### tests/test_calculator.py
import unittest
from calculator import Calculator

class TestCalculator(unittest.TestCase):
    \"\"\"Unit tests for the Calculator class.\"\"\"

    def setUp(self):
        \"\"\"Set up a new Calculator instance before each test.\"\"\"
        self.calc = Calculator()

    def test_add(self):
        self.assertEqual(self.calc.add(5, 3), 8)
        self.assertEqual(self.calc.add(-1, 1), 0)
        self.assertEqual(self.calc.add(2.5, 1.5), 4.0)

    def test_subtract(self):
        self.assertEqual(self.calc.subtract(10, 5), 5)
        self.assertEqual(self.calc.subtract(5, 10), -5)
        self.assertEqual(self.calc.subtract(-2, 2), -4)

    def test_multiply(self):
        self.assertEqual(self.calc.multiply(4, 3), 12)
        self.assertEqual(self.calc.multiply(-2, 5), -10)
        self.assertEqual(self.calc.multiply(0, 100), 0)

    def test_divide_success(self):
        self.assertEqual(self.calc.divide(10, 2), 5)
        self.assertAlmostEqual(self.calc.divide(7, 3), 2.3333333333333335) # Test float precision

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError) as context:
            self.calc.divide(10, 0)
        self.assertTrue('Cannot divide by zero' in str(context.exception))


if __name__ == '__main__':
    unittest.main()

### README.md
# AlphaPilot Calculator Module

A simple and robust command-line calculator module built for basic arithmetic operations (addition, subtraction, multiplication, division).

## 🚀 Features

*   **Basic Arithmetic**: Supports +, -, *, /.
*   **Error Handling**: Includes specific handling for division by zero.
*   **Modular Design**: Easy to integrate into larger applications.

## 📦 Installation

The module is self-contained and requires no external dependencies beyond standard Python libraries.

```bash
# If you are using a virtual environment:
python -m venv venv
source venv/bin/activate  # On Linux/macOS
venv\\Scripts\\activate   # On Windows
```

## 🛠 Usage

The core logic resides in `calculator.py`. You can instantiate the `Calculator` class and call its methods.

### Example Python Script (`main.py`)

```python
from calculator import Calculator

if __name__ == "__main__":
    calc = Calculator()

    # Addition
    print(f"10 + 5 = {calc.add(10, 5)}") # Output: 15.0

    # Subtraction
    print(f"20 - 7 = {calc.subtract(20, 7)}") # Output: 13.0

    # Multiplication
    print(f"6 * 8 = {calc.multiply(6, 8)}") # Output: 48.0

    # Division
    try:
        result = calc.divide(100, 5)
        print(f"100 / 5 = {result}") # Output: 20.0
    except ValueError as e:
        print(f"Error: {e}")

    # Division by Zero Test
    try:
        calc.divide(10, 0)
    except ValueError as e:
        print(f"Caught expected error: {e}") # Output: Cannot divide by zero.
```

## 🧪 Testing

To run the unit tests, navigate to the project root and execute:

```bash
python -m unittest tests/test_calculator.py
```
"""
    
    print(f"\n输入文本长度: {len(gemma_output)} 字符")
    print(f"包含 '### calculator.py': {'### calculator.py' in gemma_output}")
    print(f"包含 '### tests/test_calculator.py': {'### tests/test_calculator.py' in gemma_output}")
    print(f"包含 '### README.md': {'### README.md' in gemma_output}")

    print("\n" + "-" * 80)
    print("开始解析...")
    print("-" * 80)
    
    file_ops = parse_files(gemma_output)
    
    print(f"\n✅ 解析结果: {len(file_ops)} 个文件")
    for fname, content in file_ops:
        print(f"   - {fname}: {len(content)} 字符")
        # print(f"     前50字符: {content[:50]}...")
    
    if len(file_ops) == 3:
        print("\n" + "="*80)
        print("🎉 Gemma 4B 真实输出解析测试通过!")
        print("="*80)
        print("\n💡 结论:")
        print("   ✅ 成功解析 3 个文件 (calculator.py, tests/test_calculator.py, README.md)")
        print("   ✅ 能够正确识别 '### filename' 分隔符")
    else:
        print(f"\n❌ 测试失败: 期望 3 个文件,实际解析到 {len(file_ops)} 个")
    
    return file_ops


if __name__ == "__main__":
    try:
        test_gemma_real_output()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
