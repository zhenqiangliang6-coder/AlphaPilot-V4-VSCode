# -*- coding: utf-8 -*-
"""完整自愈修复流程 v2 — 多轮迭代修复"""
import os
import sys
import json
import subprocess
import requests
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from worker_config import DASHSCOPE_API_KEY

PROJECT_DIR = r"D:\test_v39_project"
TEST_FILE = os.path.join(PROJECT_DIR, "tests", "test_vote.py")
CANDIDATE_FILE = os.path.join(PROJECT_DIR, "src", "village_vote_system", "models", "candidate.py")
BACKUP_DIR = os.path.join(PROJECT_DIR, ".self_healing_backup")
VENV_PYTHON = r"D:\Copilot_Alphapilot\.venv_worker\Scripts\python.exe"

# ============================================================
# Colors
# ============================================================
G, R, Y, B, C, X = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[96m', '\033[0m'

def call_qwen(prompt):
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    r = requests.post(url,
        headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        json={"model": "qwen-max", "input": {"messages": [{"role": "user", "content": prompt}]},
              "parameters": {"temperature": 0.1, "result_format": "message"}},
        timeout=300)
    data = r.json()
    text = data.get("output", {}).get("text", "")
    if not text:
        choices = data.get("output", {}).get("choices", [])
        if choices: text = choices[0].get("message", {}).get("content", "")
    return text

def extract_code(response):
    for marker in ["```python", "```"]:
        if marker in response:
            parts = response.split(marker, 1)[1].split("```", 1)
            return parts[0].strip()
    return response.strip()

def run_tests():
    result = subprocess.run([VENV_PYTHON, "-m", "pytest", "tests/test_vote.py", "-v", "--tb=short"],
                          cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr

def test_compile(filepath, code):
    try:
        compile(code, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, str(e)

def count_test_results(output):
    passed = output.count("PASSED")
    failed = output.count("FAILED")
    errors = output.count("ERROR")
    return passed, failed, errors

# ============================================================
# 备份/恢复
# ============================================================
def backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for f in [CANDIDATE_FILE, TEST_FILE]:
        dst = os.path.join(BACKUP_DIR, os.path.relpath(f, PROJECT_DIR))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(f, dst)
    print(f"{G}已备份原始文件{X}")

def restore():
    for f in [CANDIDATE_FILE, TEST_FILE]:
        src = os.path.join(BACKUP_DIR, os.path.relpath(f, PROJECT_DIR))
        if os.path.exists(src):
            shutil.copy2(src, f)
    print(f"{G}已恢复原始文件{X}")
    # 显示原始错误
    for f in [CANDIDATE_FILE, TEST_FILE]:
        with open(f, 'r', encoding='utf-8') as fh:
            ok, err = test_compile(f, fh.read())
            if not ok:
                print(f"  {R}{os.path.basename(f)}: {err}{X}")

# ============================================================
# 单次修复尝试
# ============================================================
def fix_file(filepath, prompt_template, max_attempts=3):
    """尝试修复文件，最多 max_attempts 次"""
    rel = os.path.relpath(filepath, PROJECT_DIR)
    
    for attempt in range(1, max_attempts + 1):
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        
        print(f"\n  {C}--- 尝试 {attempt}/{max_attempts} 修复 {rel} ---{X}")
        
        prompt = prompt_template.format(code=code)
        response = call_qwen(prompt)
        fixed = extract_code(response)
        
        if not fixed:
            print(f"  {R}未能提取代码{X}")
            continue
        
        ok, err = test_compile(filepath, fixed)
        if ok:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed)
            print(f"  {G}✅ 语法正确，已应用修复{X}")
            return True
        else:
            print(f"  {R}仍有语法错误: {err[:150]}{X}")
            # 即使语法错误也应用（LLM 可能在逐步修复）
            # 但如果明显更差则跳过
            if len(fixed) < len(code) * 0.5:
                print(f"  {Y}代码长度异常缩短，跳过{X}")
                continue
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed)
    
    return False

# ============================================================
# 主流程
# ============================================================
print(f"{C}{'='*60}{X}")
print(f"{C}  AlphaPilot 自愈修复 — 完整流程{X}")
print(f"{C}{'='*60}{X}")

# Step 0: 备份
backup()

# Step 1: 修复前基线
print(f"\n{B}═══ Phase 1: 修复前基线 ═══{X}")
print(f"\n{Y}语法错误检查:{X}")
for f in [CANDIDATE_FILE, TEST_FILE]:
    with open(f, 'r', encoding='utf-8') as fh:
        ok, err = test_compile(f, fh.read())
        status = f"{G}OK{X}" if ok else f"{R}{err[:100]}{X}"
        print(f"  {os.path.basename(f)}: {status}")

print(f"\n{Y}测试运行 (修复前):{X}")
before_output = run_tests()
bp, bf, be = count_test_results(before_output)
print(before_output[-1500:])
print(f"  {R}通过: {bp}, 失败: {bf}, 错误: {be}{X}")

# Step 2: Round 1 — 修复语法错误
print(f"\n{B}═══ Phase 2: 语法错误修复 (write step) ═══{X}")

# Fix candidate.py syntax
candidate_prompt = """你是一个 Python 语法修复专家。下面是包含语法错误的代码，请只修复 Python 编译器报告的错误。

【当前代码】：
```python
{code}
```

⚠️ 严格规则：
1. 只修复：缺少冒号(:)、未闭合的字符串引号("或')、括号不匹配
2. 严禁删除或修改函数参数间的逗号 — 逗号是正确语法
3. 严禁删除 import 语句中的逗号
4. 保持原有代码结构和逻辑100%不变
5. 如果你的修复引入了新的编译错误，你就失败了

输出格式：只输出 ```python 代码块，不要任何解释。"""

fix_file(CANDIDATE_FILE, candidate_prompt)

# Fix test_vote.py syntax
test_syntax_prompt = """你是一个 Python 语法修复专家。只修复编译错误。

【当前代码】：
```python
{code}
```

⚠️ 严格规则：
1. 只修复未闭合的字符串引号、缺少冒号、括号不匹配
2. 严禁删除函数参数/import 语句中的逗号
3. 保持原有代码结构和逻辑不变

输出格式：只输出 ```python 代码块。"""

fix_file(TEST_FILE, test_syntax_prompt)

# Step 3: 中间测试
print(f"\n{B}═══ Phase 3: 语法修复后测试 ═══{X}")
mid_output = run_tests()
mp, mf, me = count_test_results(mid_output)
print(mid_output[-1500:])
print(f"  通过: {mp}, 失败: {mf}, 错误: {me}")

# Step 4: Round 2 — 测试驱动修复（自愈核心）
if mf > 0 or me > 0:
    print(f"\n{B}═══ Phase 4: 测试驱动修复 (fix step) ═══{X}")
    
    for round_num in range(1, 4):
        with open(TEST_FILE, 'r', encoding='utf-8') as f:
            test_code = f.read()
        with open(CANDIDATE_FILE, 'r', encoding='utf-8') as f:
            candidate_code = f.read()
        
        test_output = run_tests()
        tp, tf, te = count_test_results(test_output)
        print(f"\n  {C}--- 自愈轮次 {round_num} (当前: {tp} passed, {tf} failed, {te} errors) ---{X}")
        
        if tf == 0 and te == 0:
            print(f"  {G}🎉 所有测试通过！{X}")
            break
        
        # 修复测试文件
        fix_test_prompt = f"""你是 pytest 专家。下面是一个测试文件，运行报错。请修复所有运行时错误。

【当前测试代码】：
```python
{{code}}
```

【pytest 错误输出】：
{test_output[-2500:]}

请修复所有问题！常见修复：
1. cleanup 函数需要 @pytest.fixture 装饰器
2. VoteRequest 需要从正确的模块导入（在 api/vote_router.py 中定义）
3. 不要删除 import 或函数参数中的逗号

⚠️ 输出完整的修复后代码（```python 代码块）。"""

        fix_file(TEST_FILE, fix_test_prompt, max_attempts=2)
        
        # 同时也修复源代码
        fix_source_prompt = f"""你是 Python 专家。根据测试错误修复源代码。

【当前源代码 (candidate.py)】：
```python
{{code}}
```

【测试错误】：
{test_output[-2000:]}

输出修复后的完整代码（```python 代码块），保持逗号不动。"""

        fix_file(CANDIDATE_FILE, fix_source_prompt, max_attempts=2)

# Step 5: 最终测试
print(f"\n{B}═══ Phase 5: 最终测试结果 ═══{X}")
after_output = run_tests()
ap, af, ae = count_test_results(after_output)
print(after_output[-1500:])

# 汇总
print(f"\n{C}{'='*60}{X}")
print(f"{C}  📊 自愈修复报告{X}")
print(f"{C}{'='*60}{X}")
total_before = bp + bf + be
total_after = ap + af + ae
rate_before = (bp / total_before * 100) if total_before > 0 else 0
rate_after = (ap / total_after * 100) if total_after > 0 else 0
improvement = rate_after - rate_before

print(f"""
  修复前: {bp}/{total_before} 通过 ({rate_before:.0f}%)  |  {R}{'█' * int(rate_before/10)}{'░' * (10-int(rate_before/10))}{X}
  修复后: {ap}/{total_after} 通过 ({rate_after:.0f}%)  |  {G}{'█' * int(rate_after/10)}{'░' * (10-int(rate_after/10))}{X}
  
  自愈改善: {improvement:+.0f}%
""")

if ap == total_after:
    print(f"{G}🎉 自愈修复完全成功！所有测试通过！{X}")
elif improvement > 0:
    print(f"{G}📈 测试通过率提升了 {improvement:.0f}%{X}")
else:
    print(f"{Y}自愈修复未能完全解决所有问题{X}")

print(f"\n{Y}备份目录: {BACKUP_DIR}{X}")
print(f"{Y}运行 restore() 可恢复原始文件{X}")