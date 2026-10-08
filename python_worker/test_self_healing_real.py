# -*- coding: utf-8 -*-
"""
test_self_healing_real.py — 真实环境自愈修复流程测试
============================================================
使用 DASHSCOPE_API_KEY 对 test_v39_project 执行 write → test → fix 流程
对比修复前后的测试成功率
"""

import os
import sys
import json
import shutil
import subprocess
import time
import requests
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from worker_config import DASHSCOPE_API_KEY

# ============================================================
# 直接使用 DashScope API（避免相对导入问题）
# ============================================================
def call_qwen(prompt: str) -> str:
    """调用 Qwen API 进行文本生成（阻塞模式）"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    body = {
        "model": "qwen-max",  # 使用最强模型确保修复质量
        "input": {"messages": [{"role": "user", "content": prompt}]},
        "parameters": {
            "temperature": 0.1,
            "result_format": "message"
        }
    }
    r = requests.post(url, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    data = r.json()
    # 兼容新旧两种响应格式
    text = data.get("output", {}).get("text", "")
    if not text:
        choices = data.get("output", {}).get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise ValueError(f"Unexpected API response: {json.dumps(data, ensure_ascii=False)[:500]}")
    return text


def fix_prompt(path: str, code: str, error_message: str, test_code: str = "") -> str:
    """生成自动修复代码的 prompt — 精准修复版"""
    base_prompt = f"""你是一个 Python 语法修复专家。下面是包含语法错误的代码，请只修复语法错误，其他代码保持原样不变。

文件路径：{path}

【原始代码（含语法错误）】：
```python
{code}
```

【Python 编译器报告的错误】：
{error_message}

⚠️ 严格要求：
1. 只修复编译器明确报告的错误（如缺少冒号、未闭合的字符串引号）
2. 函数参数之间的逗号、函数调用参数之间的逗号都是正确语法，严禁删除
3. 保持原有代码结构和逻辑完全不变
4. 输出完整的修复后代码（使用 ```python 代码块包裹）
"""
    if test_code:
        base_prompt += f"""

【测试代码】（你的修复必须通过以下测试）：
```python
{test_code}
```

请确保修复后的代码与测试代码中的调用方式完全匹配。
"""
    base_prompt += """
只输出 ```python 代码块，不要输出任何解释性文字。"""
    return base_prompt

# ============================================================
# 配置
# ============================================================
PROJECT_DIR = r"D:\test_v39_project"
CANDIDATE_FILE = os.path.join(PROJECT_DIR, "src", "village_vote_system", "models", "candidate.py")
TEST_FILE = os.path.join(PROJECT_DIR, "tests", "test_vote.py")
BACKUP_DIR = os.path.join(PROJECT_DIR, ".self_healing_backup")

# ============================================================
# 颜色输出
# ============================================================
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(title):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")

def print_ok(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_fail(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")

def print_warn(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

# ============================================================
# 步骤 0: 备份原始文件
# ============================================================
def backup_originals():
    print_header("步骤 0: 备份原始文件")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    for src_path in [CANDIDATE_FILE, TEST_FILE]:
        rel = os.path.relpath(src_path, PROJECT_DIR)
        dst = os.path.join(BACKUP_DIR, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src_path, dst)
        print_info(f"已备份: {rel}")
    
    print_ok("备份完成")

# ============================================================
# 步骤 0.5: 恢复原始文件（用于重置环境）
# ============================================================
def restore_originals():
    for src_path in [CANDIDATE_FILE, TEST_FILE]:
        rel = os.path.relpath(src_path, PROJECT_DIR)
        backup = os.path.join(BACKUP_DIR, rel)
        if os.path.exists(backup):
            shutil.copy2(backup, src_path)

# ============================================================
# 步骤 1: 检查初始错误（修复前基线）
# ============================================================
def check_syntax_errors():
    """检查 Python 语法错误并返回详情"""
    print_header("步骤 1: 检查修复前语法错误（基线）")
    
    errors = {}
    for file_path in [CANDIDATE_FILE, TEST_FILE]:
        rel = os.path.relpath(file_path, PROJECT_DIR)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            compile(source, file_path, 'exec')
            print_ok(f"{rel} — 语法正确")
            errors[rel] = None
        except SyntaxError as e:
            print_fail(f"{rel} — 语法错误: {e.msg} (line {e.lineno})")
            errors[rel] = str(e)
    
    return errors

# ============================================================
# 步骤 2: 运行测试（修复前基线）
# ============================================================
def run_tests(label="修复前"):
    """运行 pytest 并返回测试结果统计"""
    print_header(f"步骤: 运行测试 ({label})")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_vote.py", "-v", "--tb=short"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + result.stderr
        print(output[-2000:])  # 打印最后2000字符
        
        # 解析结果
        passed = 0
        failed = 0
        errors = 0
        for line in output.split('\n'):
            if 'PASSED' in line:
                passed += 1
            elif 'FAILED' in line:
                failed += 1
            elif 'ERROR' in line:
                errors += 1
        
        total = passed + failed + errors
        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "success_rate": (passed / total * 100) if total > 0 else 0,
            "output": output
        }
    except subprocess.TimeoutExpired:
        print_fail("测试执行超时")
        return {"passed": 0, "failed": 0, "errors": 0, "total": 0, "success_rate": 0, "output": "TIMEOUT"}
    except Exception as e:
        print_fail(f"测试执行失败: {e}")
        return {"passed": 0, "failed": 0, "errors": 0, "total": 0, "success_rate": 0, "output": str(e)}

# ============================================================
# 步骤 3: 自愈修复 — 使用 LLM 修复语法错误
# ============================================================
def fix_file_with_llm(file_path, error_info, test_code=""):
    """使用 LLM 修复单个文件中的错误"""
    rel = os.path.relpath(file_path, PROJECT_DIR)
    print(f"\n{Colors.BOLD}🔧 正在修复: {rel}{Colors.RESET}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        original_code = f.read()
    
    if error_info:
        print_info(f"错误信息: {error_info[:200]}")
    if test_code:
        print_info(f"测试代码: {test_code[:200]}...")
    
    # 构建修复 prompt
    prompt = fix_prompt(rel, original_code, error_info, test_code)
    
    print_info("调用 Qwen API (qwen-turbo)...")
    try:
        response = call_qwen(prompt)
        print_info(f"LLM 响应长度: {len(response)} 字符")
        
        # 提取代码块
        code = extract_code_from_response(response)
        if code:
            # 验证语法
            try:
                compile(code, file_path, 'exec')
                print_ok("生成的代码语法正确，应用修复")
                
                # 应用修复
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                return True, code
            except SyntaxError as e:
                print_fail(f"生成的代码仍有语法错误: {e}")
                return False, code
        else:
            print_fail("未能从 LLM 响应中提取代码")
            return False, response
    except Exception as e:
        print_fail(f"LLM 调用失败: {e}")
        return False, str(e)

def extract_code_from_response(response):
    """从 LLM 响应中提取 Python 代码"""
    # 尝试提取 ```python 代码块
    if "```python" in response:
        parts = response.split("```python", 1)
        if len(parts) > 1:
            code_parts = parts[1].split("```", 1)
            if len(code_parts) > 1:
                return code_parts[0].strip()
    
    # 尝试提取 ``` 代码块
    if "```" in response:
        parts = response.split("```", 1)
        if len(parts) > 1:
            code_parts = parts[1].split("```", 1)
            if len(code_parts) > 1:
                return code_parts[0].strip()
    
    # 如果包含 # FILE: 格式，尝试提取
    if "# FILE:" in response:
        lines = response.split('\n')
        code_lines = []
        in_file = False
        for line in lines:
            if line.startswith('# FILE:'):
                in_file = True
                continue
            if in_file and line.startswith('```'):
                break
            if in_file:
                code_lines.append(line)
        if code_lines:
            return '\n'.join(code_lines).strip()
    
    return response.strip()

# ============================================================
# 步骤 4: 如果测试失败，使用 fix_step（测试驱动的自愈）
# ============================================================
def fix_with_test_context(file_path, test_code, error_info):
    """使用测试代码作为上下文进行修复（测试驱动修复）"""
    rel = os.path.relpath(file_path, PROJECT_DIR)
    print(f"\n{Colors.BOLD}🔧 测试驱动修复: {rel}{Colors.RESET}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        original_code = f.read()
    
    prompt = fix_prompt(rel, original_code, error_info, test_code)
    
    print_info("调用 Qwen API (qwen-turbo) — 带测试上下文...")
    try:
        response = call_qwen(prompt)
        code = extract_code_from_response(response)
        
        if code:
            try:
                compile(code, file_path, 'exec')
                print_ok("修复后的代码语法正确")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                return True, code
            except SyntaxError as e:
                print_fail(f"修复后仍有语法错误: {e}")
                return False, code
        return False, response
    except Exception as e:
        print_fail(f"LLM 调用失败: {e}")
        return False, str(e)

# ============================================================
# 主流程
# ============================================================
def main():
    print_header("🚀 AlphaPilot 自愈修复 — 真实环境测试")
    print_info(f"项目路径: {PROJECT_DIR}")
    print_info(f"API Key: {os.getenv('DASHSCOPE_API_KEY', 'NOT SET')[:12]}...")
    
    # ---- Round 0: 备份 & 基线 ----
    backup_originals()
    
    # 检查初始语法错误
    initial_errors = check_syntax_errors()
    
    # 修复前运行测试
    before_result = run_tests("修复前（原始错误代码）")
    
    # ---- Round 1: 修复语法错误 ----
    print_header("🔄 Round 1: 语法错误修复")
    
    # 读取所有需要修复的文件
    files_to_fix = []
    for rel, error in initial_errors.items():
        if error:
            file_path = os.path.join(PROJECT_DIR, rel)
            files_to_fix.append((file_path, error))
    
    fixes_applied = []
    for file_path, error in files_to_fix:
        success, fixed_code = fix_file_with_llm(file_path, error)
        fixes_applied.append({
            "file": os.path.relpath(file_path, PROJECT_DIR),
            "success": success,
            "error_was": error[:100]
        })
    
    # 验证修复结果
    remaining_errors = check_syntax_errors()
    
    # 修复后运行测试（中间结果）
    mid_result = run_tests("Round 1 语法修复后")
    
    # ---- Round 2: 测试驱动修复（自愈核心） ----
    if mid_result["failed"] > 0 or mid_result["errors"] > 0:
        print_header("🔄 Round 2: 测试驱动修复（自愈核心）")
        
        # 读取测试代码
        with open(TEST_FILE, 'r', encoding='utf-8') as f:
            test_code = f.read()
        
        # 读取当前源代码
        with open(CANDIDATE_FILE, 'r', encoding='utf-8') as f:
            candidate_code = f.read()
        
        # 构建错误信息
        error_info = mid_result.get("output", "")
        if len(error_info) > 2000:
            error_info = error_info[-2000:]  # 取最后的错误信息
        
        # 修复源代码
        success, fixed_code = fix_with_test_context(CANDIDATE_FILE, test_code, error_info)
        fixes_applied.append({
            "file": os.path.relpath(CANDIDATE_FILE, PROJECT_DIR),
            "success": success,
            "round": "test_driven_fix"
        })
        
        # 也检查是否需要修复测试文件
        test_has_error = False
        for rel, error in remaining_errors.items():
            if "test_vote.py" in rel and error:
                test_has_error = True
                break
        
        if test_has_error:
            success, fixed_code = fix_file_with_llm(TEST_FILE, remaining_errors.get("tests/test_vote.py", "SyntaxError"))
            fixes_applied.append({
                "file": "tests/test_vote.py",
                "success": success,
                "round": "test_file_fix"
            })
    
    # ---- 最终测试 ----
    after_result = run_tests("最终（修复后）")
    
    # ---- 汇总报告 ----
    print_header("📊 自愈修复报告")
    
    print(f"\n{Colors.BOLD}修复前基线:{Colors.RESET}")
    print(f"  语法错误文件: {sum(1 for e in initial_errors.values() if e)} 个")
    print(f"  测试通过率: {before_result['success_rate']:.0f}% ({before_result['passed']}/{before_result['total']})")
    
    print(f"\n{Colors.BOLD}修复后结果:{Colors.RESET}")
    print(f"  语法错误文件: {sum(1 for e in remaining_errors.values() if e)} 个")
    print(f"  测试通过率: {after_result['success_rate']:.0f}% ({after_result['passed']}/{after_result['total']})")
    
    print(f"\n{Colors.BOLD}修复详情:{Colors.RESET}")
    for fix in fixes_applied:
        status = "✅ 成功" if fix["success"] else "❌ 失败"
        print(f"  {fix['file']}: {status}")
    
    # 计算改善
    improvement = after_result['success_rate'] - before_result['success_rate']
    print(f"\n{Colors.BOLD}{Colors.CYAN}自愈效果: {improvement:+.0f}% 改善{Colors.RESET}")
    
    if after_result['success_rate'] == 100:
        print_ok("🎉 所有测试通过！自愈修复成功！")
    elif after_result['success_rate'] > before_result['success_rate']:
        print_ok(f"📈 测试通过率提升了 {improvement:.0f}%")
    else:
        print_warn("自愈修复未能改善测试结果，可能需要人工介入")
    
    # ---- 清理：恢复原始文件（可选） ----
    print(f"\n{Colors.YELLOW}原始文件已备份到: {BACKUP_DIR}{Colors.RESET}")
    print(f"{Colors.YELLOW}如需恢复，请运行: restore_originals(){Colors.RESET}")
    
    return {
        "before": before_result,
        "after": after_result,
        "improvement": improvement,
        "fixes": fixes_applied
    }

if __name__ == "__main__":
    result = main()
    print(f"\n{Colors.CYAN}返回数据: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}{Colors.RESET}")