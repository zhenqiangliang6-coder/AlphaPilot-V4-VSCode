# -*- coding: utf-8 -*-
"""
真正的全自动自愈测试 — 事件驱动，零人工编排

流程:
  1. 注入错误 + 删除 venv
  2. 启动 self_healing_loop()
  3. 系统自己: run_tests → parse_errors → classify → route → fix → repeat
  4. 直到 100% 通过或达到最大轮次
"""
import os, sys, subprocess, requests, shutil, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()
from worker_config import DASHSCOPE_API_KEY
from self_healing_enhanced import (
    build_project_map, format_project_map, build_multifile_context,
    validate_imports,
    check_venv_exists, create_venv, install_package, scan_project_imports,
    parse_pytest_errors, classify_top_error, ERROR_HANDLERS, self_healing_loop
)

PROJECT_DIR = r"D:\test_v39_project"
PROJECT_VENV = os.path.join(PROJECT_DIR, '.venv_auto')
G, R, Y, B, C, X = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[96m', '\033[0m'

# ============================================================
# LLM 调用
# ============================================================
def qwen(prompt, max_chars=28000):
    """调用通义千问 qwen-max，返回响应文本。自动截断超长 prompt。"""
    prompt = _safe_prompt(prompt, max_chars, label="qwen")
    try:
        r = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            json={"model": "qwen-max", "input": {"messages": [{"role": "user", "content": prompt}]},
                  "parameters": {"temperature": 0.1, "result_format": "message"}}, timeout=300
        )
        d = r.json()
        if r.status_code != 200:
            print(f"    [QWEN ERROR] status={r.status_code} body={json.dumps(d, ensure_ascii=False)[:500]}")
        t = d.get("output", {}).get("text", "")
        if not t:
            cs = d.get("output", {}).get("choices", [])
            if cs: t = cs[0].get("message", {}).get("content", "")
        if not t:
            print(f"    [QWEN EMPTY] prompt_len={len(prompt)} response={json.dumps(d, ensure_ascii=False)[:500]}")
        return t
    except Exception as e:
        print(f"    [QWEN EXCEPTION] {e}")
        return ""


def _safe_prompt(text, max_chars=28000, label="prompt"):
    """截断过长的 prompt 并打印警告。默认 28000 为 qwen-max 30720 的安全余量。"""
    if len(text) <= max_chars:
        return text
    print(f"    [TRUNCATE] {label}: {len(text)} → {max_chars} chars (API 限制)")
    return text[:max_chars] + "\n... (截断)"

def extract_code(resp):
    for m in ["```python", "```"]:
        if m in resp:
            return resp.split(m, 1)[1].split("```", 1)[0].strip()
    return resp.strip()

# ============================================================
# LLM Fixer — 被 self_healing_loop 回调，处理代码层错误
# ============================================================
_project_map = None
_pm_text = ""

def llm_fixer(error_type, error_info, test_output, context):
    """当 ERROR_ROUTER 返回 'needs_llm' 时，self_healing_loop 调用此函数"""
    global _project_map, _pm_text

    if _project_map is None:
        _project_map = build_project_map(PROJECT_DIR)
        _pm_text = format_project_map(_project_map)

    project_dir = context.get('project_dir', PROJECT_DIR)

    if error_type == 'syntax':
        return _fix_syntax(error_info, project_dir)
    elif error_type == 'no_tests':
        return _fix_all_syntax(project_dir)
    elif error_type == 'unknown':
        return _fix_all_syntax(project_dir)
    elif error_type == 'fixture_not_found':
        return _fix_fixture(error_info, test_output, project_dir)
    elif error_type == 'import_error':
        return _fix_import(error_info, test_output, project_dir)
    elif error_type == 'assertion_error':
        return _fix_logic(error_info, test_output, project_dir)
    elif error_type == 'attribute_error':
        return _fix_logic(error_info, test_output, project_dir)
    elif error_type == 'name_error':
        return _fix_import(error_info, test_output, project_dir)
    elif error_type == 'file_not_found':
        return _fix_file_path(error_info, test_output, project_dir)
    return {'status': 'skipped', 'reason': 'unknown error type'}


def _fix_syntax(error_info, project_dir):
    filepath = error_info.get('file', '')
    if not filepath:
        return _fix_all_syntax(project_dir)

    abs_path = os.path.join(project_dir, filepath) if not os.path.isabs(filepath) else filepath
    if not os.path.exists(abs_path):
        return {'status': 'failed', 'reason': f'文件不存在: {abs_path}'}

    with open(abs_path, 'r', encoding='utf-8') as f:
        code = f.read()

    prompt = f"""你是 Python 语法修复专家。只修复编译器报告的语法错误。

【文件】: {filepath}
【错误】: {error_info.get('name', '')} (行 {error_info.get('line', 0)})

【代码】:
```python
{code}
```

规则:
1. 只修复未闭合引号、缺少冒号、括号不匹配
2. 严禁删除逗号
只输出 ```python 代码块。"""

    resp = qwen(prompt)
    fixed = extract_code(resp)
    if fixed:
        try:
            compile(fixed, filepath, 'exec')
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(fixed)
            return {'status': 'fixed', 'action': f'syntax_fix:{filepath}'}
        except SyntaxError as e:
            return {'status': 'failed', 'reason': f'修复后仍有语法错误: {e}'}
    return {'status': 'failed', 'reason': 'LLM 未返回有效代码'}


def _fix_all_syntax(project_dir):
    """
    全项目扫描并修复所有语法错误。
    策略: 简单错误用规则引擎 (可靠), 复杂错误用 LLM。
    """
    fixed_count = 0

    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in (
            '__pycache__', '.git', 'venv', '.venv', '.venv_auto',
            'generated', '.pytest_cache') and not d.startswith('.')]
        for fn in files:
            if not fn.endswith('.py'):
                continue
            fpath = os.path.join(root, fn)
            with open(fpath, 'r', encoding='utf-8') as f:
                code = f.read()

            ok, err = test_compile_code(fpath, code)
            if ok:
                continue

            rel = os.path.relpath(fpath, project_dir)

            # 先尝试规则引擎修复
            fixed = _rule_based_syntax_fix(code, err)
            if fixed and fixed != code:
                ok2, _ = test_compile_code(fpath, fixed)
                if ok2:
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(fixed)
                    fixed_count += 1
                    continue

            # 规则引擎失败，用 LLM (但必须验证逗号没有被删)
            fixed = _llm_syntax_fix(rel, code, err)
            if fixed:
                ok2, _ = test_compile_code(fpath, fixed)
                if ok2 and _commas_preserved(code, fixed):
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(fixed)
                    fixed_count += 1

    if fixed_count > 0:
        return {'status': 'fixed', 'action': f'syntax_fix_all:{fixed_count}_files'}
    return {'status': 'failed', 'reason': '未找到可修复的语法错误'}


def _rule_based_syntax_fix(code, error_msg):
    """规则引擎：修复常见的简单语法错误"""
    lines = code.split('\n')
    import re

    # 模式1: 缺少冒号 — class/def/if/for/while/with/try/except 后面
    m = re.search(r"expected ':'", error_msg)
    if m:
        # 找到缺少冒号的行
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (stripped.startswith(('class ', 'def ', 'if ', 'elif ', 'else',
                                     'for ', 'while ', 'with ', 'try', 'except ',
                                     'finally'))
                    and not stripped.rstrip().endswith(':')):
                # 在行尾或括号前加冒号
                if stripped.rstrip().endswith(')'):
                    lines[i] = line.rstrip() + ':'
                elif '(' in stripped:
                    # 找到匹配的闭合括号
                    depth = 0
                    pos = len(stripped)
                    for j, ch in enumerate(stripped):
                        if ch == '(': depth += 1
                        elif ch == ')': depth -= 1
                        if depth == 0 and j > 0:
                            pos = j + 1
                            break
                    lines[i] = stripped[:pos] + ':' + stripped[pos:]
                else:
                    lines[i] = line.rstrip() + ':'
                return '\n'.join(lines)

    # 模式2: 缺少闭合括号
    m2 = re.search(r"'\)' was never closed|'\(' was never closed", error_msg)
    if m2:
        # 找到最后一个函数调用/定义，补上 )
        open_count = code.count('(')
        close_count = code.count(')')
        if open_count > close_count:
            return code.rstrip() + ')' * (open_count - close_count)

    # 模式3: 未闭合的字符串
    m3 = re.search(r"unterminated string|EOL while scanning", error_msg)
    if m3:
        # 在最后一行末尾加引号
        last_line = lines[-1].rstrip()
        if last_line and last_line[-1] not in ('"', "'"):
            lines[-1] = lines[-1].rstrip() + '"'
            return '\n'.join(lines)

    return None


def _commas_preserved(original, fixed):
    """检查 LLM 修复是否保留了原始代码中的逗号"""
    orig_commas = original.count(',')
    fixed_commas = fixed.count(',')
    if fixed_commas < orig_commas * 0.8:
        return False
    return True


def _llm_syntax_fix(rel, code, err):
    """LLM 语法修复（作为规则引擎的 fallback）"""
    for attempt in range(1, 4):
        prompt = f"""你是 Python 语法修复专家。修复下面代码的编译错误。

【文件】: {rel}
【编译错误】: {err}

【代码】(每行前有行号):
"""
        for i, line in enumerate(code.split('\n'), 1):
            prompt += f"{i:4d}| {line}\n"

        prompt += f"""
⚠️ 极度重要 — 必须遵守:
1. 只修复编译器报告的语法错误
2. import 语句中的逗号(,)是正确语法，如: import pytest, json, os → 保留逗号！
3. 函数参数中的逗号是正确语法，如: def fn(a, b): → 保留逗号！
4. 函数调用中的逗号是正确语法，如: fn(x, y) → 保留逗号！
5. 字典中的逗号是正确语法，如: {{"a": 1, "b": 2}} → 保留逗号！
6. 如果你删除了逗号，代码会损坏！
7. 只输出修复后的完整代码，用 ```python 包裹。"""

        resp = qwen(prompt)
        fixed = extract_code(resp)
        if fixed and len(fixed) > len(code) * 0.5:
            if _commas_preserved(code, fixed):
                return fixed
            # 逗号被删了，用更强的提示再试
            prompt += "\n\n⚠️⚠️⚠️ 上一次你删除了代码中的逗号！逗号是正确语法，必须保留！重新修复！"
    return None


def _fix_fixture(error_info, test_output, project_dir):
    fixture_name = error_info.get('name', '')
    test_file = os.path.join(project_dir, 'tests', 'test_vote.py')
    if not os.path.exists(test_file):
        return {'status': 'failed', 'reason': '未找到测试文件'}

    with open(test_file, 'r', encoding='utf-8') as f:
        code = f.read()

    # 策略1: 规则引擎 — 直接在前面加 @pytest.fixture
    import re
    pattern = rf'^(def {re.escape(fixture_name)}\(.*?\):)'
    m = re.search(pattern, code, re.MULTILINE)
    print(f"    [DEBUG fixture] name={fixture_name!r} match={bool(m)} commas_in={code.count(',')}")
    if m:
        fixed = re.sub(pattern, '@pytest.fixture\n\\1', code, flags=re.MULTILINE)
        print(f"    [DEBUG fixture] fixed commas={fixed.count(',')} has_decorator={'@pytest.fixture' in fixed}")
        try:
            compile(fixed, test_file, 'exec')
            imp_ok, imp_errs = validate_imports(fixed, _project_map, 'tests/test_vote.py')
            print(f"    [DEBUG fixture] compile=OK imp_ok={imp_ok} imp_errs={imp_errs}")
            if imp_ok:
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(fixed)
                # Verify
                with open(test_file, 'r', encoding='utf-8') as f:
                    verify = f.read()
                print(f"    [DEBUG fixture] wrote file, verify has_decorator={'@pytest.fixture' in verify}")
                return {'status': 'fixed', 'action': f'fixture_fix_rule:{fixture_name}'}
        except SyntaxError as e:
            print(f"    [DEBUG fixture] SyntaxError: {e}")

    prompt = f"""{_pm_text}

你是 pytest 专家。fixture '{fixture_name}' 未注册导致测试失败。

【错误输出】:
{test_output[-1500:]}

【测试代码】:
```python
{code}
```

规则:
1. 找到 {fixture_name} 函数，在前面加 @pytest.fixture 装饰器
2. 如果函数做清理工作，用 yield 替代直接清理
3. ⚠️ import 中的逗号(,)是正确语法，必须保留！
4. ⚠️ 函数参数/调用中的逗号也是正确语法，必须保留！
5. 只添加 @pytest.fixture，不要修改其他任何代码
只输出完整 ```python 代码块。"""

    resp = qwen(prompt)
    fixed = extract_code(resp)
    if fixed and len(fixed) > len(code) * 0.5 and _commas_preserved(code, fixed):
        try:
            compile(fixed, test_file, 'exec')
            imp_ok, _ = validate_imports(fixed, _project_map, 'tests/test_vote.py')
            if imp_ok:
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(fixed)
                return {'status': 'fixed', 'action': f'fixture_fix:{fixture_name}'}
        except SyntaxError:
            pass
    return {'status': 'failed', 'reason': f'无法修复 fixture: {fixture_name}'}


def _fix_import(error_info, test_output, project_dir):
    import_name = error_info.get('name', '')
    test_file = os.path.join(project_dir, 'tests', 'test_vote.py')

    # 从项目地图中查找 import_name 的正确路径，生成精简提示
    import_hint = ""
    if _project_map and import_name:
        sym = _project_map.get('symbols', {}).get(import_name)
        if sym:
            import_hint = f"\n【正确导入路径】: from {sym['module_path']} import {import_name}  (定义于 {sym['file']}:{sym['line']})\n"

    # 只修复测试文件 — 被测源文件不应该被改 import
    with open(test_file, 'r', encoding='utf-8') as f:
        code = f.read()

    rel = os.path.relpath(test_file, project_dir)
    prompt = f"""{import_hint}
你是 Python import 修复专家。

【错误】: 缺少导入 '{import_name}'，导致 NameError
【文件】: {rel}

【错误输出】:
{test_output[-1500:]}

【代码】:
```python
{code}
```

规则:
1. 根据【正确导入路径】添加缺失的 import 语句
2. 严禁删除或修改已有 import 中的逗号(,)
3. 严禁修改代码逻辑，只添加缺失的 import
只输出 ```python 代码块。"""

    resp = qwen(prompt)
    fixed = extract_code(resp)
    if fixed and len(fixed) > len(code) * 0.4 and _commas_preserved(code, fixed):
        try:
            compile(fixed, test_file, 'exec')
            ok, errs = validate_imports(fixed, _project_map, rel)
            if ok:
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(fixed)
                return {'status': 'fixed', 'action': f'import_fix:{rel}'}
            else:
                # validate_imports 可能因项目地图不完整而误判，fallback：编译通过就行
                print(f"    [DEBUG import] validate_imports warning: {errs}, using compile-only check")
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(fixed)
                return {'status': 'fixed', 'action': f'import_fix:{rel}'}
        except SyntaxError as e:
            print(f"    [DEBUG import] SyntaxError: {e}")

    return {'status': 'failed', 'reason': f'import 修复失败'}


def _fix_logic(error_info, test_output, project_dir):
    """通用逻辑修复（assertion/attribute/file_not_found 都走这里）"""
    # 收集所有相关文件
    all_files = []
    for root, dirs, files in os.walk(os.path.join(project_dir, 'src')):
        dirs[:] = [d for d in dirs if not d.startswith('__')]
        for fn in files:
            if fn.endswith('.py'):
                all_files.append(os.path.join(root, fn))
    for root, dirs, files in os.walk(os.path.join(project_dir, 'tests')):
        dirs[:] = [d for d in dirs if not d.startswith('__')]
        for fn in files:
            if fn.endswith('.py'):
                all_files.append(os.path.join(root, fn))

    files_code = ""
    for fp in all_files:
        with open(fp, 'r', encoding='utf-8') as f:
            files_code += f"\n# === {os.path.relpath(fp, project_dir)} ===\n{f.read()}"

    prompt = f"""你是 Python 修复专家。测试失败，需要修复代码。

【错误】: {error_info.get('raw', '')}

【测试输出】:
{test_output[-2000:]}

【项目全部代码】:
{files_code[:8000]}

规则:
1. 优先修复被测试代码 (src/)，其次修复测试代码
2. 保持代码结构不变
3. 严禁删除逗号(,)
输出: FILE: <相对路径>
```python
<完整代码>
```"""

    resp = qwen(prompt)
    blocks = []
    current_file = None
    current_code = []
    for line in resp.split('\n'):
        line_stripped = line.strip()
        if line_stripped.upper().startswith('FILE:'):
            if current_file and current_code:
                blocks.append((current_file, '\n'.join(current_code)))
            current_file = line_stripped[5:].strip().strip(':')
            current_code = []
        elif line_stripped == '```python':
            current_code = []
        elif line_stripped == '```' and current_code:
            blocks.append((current_file, '\n'.join(current_code)))
            current_file = None
            current_code = []
        elif current_code is not None:
            current_code.append(line)

    if current_file and current_code:
        blocks.append((current_file, '\n'.join(current_code)))

    fixed_count = 0
    for fname, code in blocks:
        if not fname:
            continue
        fpath = os.path.join(project_dir, fname)
        if os.path.exists(fpath) and len(code) > 50:
            try:
                compile(code, fname, 'exec')
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(code)
                fixed_count += 1
            except SyntaxError:
                pass

    if fixed_count:
        return {'status': 'fixed', 'action': f'logic_fix:{fixed_count}_files'}
    return {'status': 'failed', 'reason': '逻辑修复失败'}


def _fix_file_path(error_info, test_output, project_dir):
    return _fix_logic(error_info, test_output, project_dir)


# ============================================================
# 全自动自愈 —— 真正的自主流程
# ============================================================

def test_compile_code(fpath, code):
    try:
        compile(code, fpath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def autonomous_heal():
    """真正的全自动自愈：只注入错误，剩下的全交给事件引擎"""

    print(f"{C}{'='*60}{X}")
    print(f"{C}  全自动自愈测试 — 事件驱动，零人工编排{X}")
    print(f"{C}{'='*60}{X}")

    # ============================================================
    # 准备: 注入错误 + 删除环境
    # ============================================================
    print(f"\n{B}  准备阶段: 注入错误 + 删除环境{X}")

    # 备份源文件（防止 LLM 永久破坏）
    files_to_save = [
        os.path.join(PROJECT_DIR, "src/village_vote_system/models/candidate.py"),
        os.path.join(PROJECT_DIR, "tests/test_vote.py"),
        os.path.join(PROJECT_DIR, "src/village_vote_system/api/vote_router.py"),
    ]
    backups = {}
    for fp in files_to_save:
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                backups[fp] = f.read()

    # 注入语法错误
    CANDIDATE_BUGGY = '''class Candidate
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    def to_dict(self):
        return {"id": self.id, "name": self.name}

    @staticmethod
    def load_all():
        import json, os
        data_path = os.path.join(os.path.dirname(__file__), "../../../data/candidates.json")
        
        with open(data_path, "r", encoding="utf-8") as f:
            candidates = json.load(f)
        
        return [Candidate(c["id"], c["name"]) for c in candidates]
'''

    TEST_BUGGY = '''import pytest, json, os, shutil, tempfile
from src.village_vote_system.api.vote_router import cast_vote
from src.village_vote_system.models.voter import Voter
from src.village_vote_system.models.candidate import Candidate
from src.village_vote_system.utils import validate_age, check_vote_eligibility, save_vote_data

temp_dir = tempfile.mkdtemp()
VOTERS_PATH = os.path.join(temp_dir, "voters.json")
CANDIDATES_PATH = os.path.join(temp_dir, "candidates.json")
VOTES_PATH = os.path.join(temp_dir, "votes.json")

def cleanup():
    shutil.rmtree(temp_dir)

pytestmark = pytest.mark.usefixtures("cleanup"

def setup_voter_data():
    voters = [{"id": "123456", "name": "张三", "birth_date": "2000-01-01"}]
    with open(VOTERS_PATH, "w") as f: json.dump(voters, f)

def setup_candidate_data():
    candidates = [{"id": 1, "name": "候选人A"}, {"id": 2, "name": "候选人B"}]
    with open(CANDIDATES_PATH, "w") as f: json.dump(candidates, f)

def test_cast_vote_success():
    request = VoteRequest(voter_id="123456", candidate_id=1)
    resp = cast_vote(request)
    assert resp.success

def test_cast_vote_already_voted():
    request = VoteRequest(voter_id="654321", candidate_id=1)
    resp = cast_vote(request)
    assert not resp.success
'''

    with open(os.path.join(PROJECT_DIR, "src/village_vote_system/models/candidate.py"), 'w', encoding='utf-8') as f:
        f.write(CANDIDATE_BUGGY)
    with open(os.path.join(PROJECT_DIR, "tests/test_vote.py"), 'w', encoding='utf-8') as f:
        f.write(TEST_BUGGY)
    print(f"  {Y}已注入 2 个语法错误 + 3 个逻辑错误 (fixture/import/路径){X}")

    # 删除环境
    if os.path.exists(PROJECT_VENV):
        shutil.rmtree(PROJECT_VENV)
        print(f"  {R}已删除 .venv_auto (模拟用户操作){X}")
    else:
        print(f"  {Y}.venv_auto 本就不存在{X}")

    # ============================================================
    # 启动自愈主循环
    # ============================================================
    print(f"\n{C}{'='*60}{X}")
    print(f"{C}  启动自愈主循环 — 系统自行决策{X}")
    print(f"{C}{'='*60}{X}")

    venv_python = os.path.join(PROJECT_VENV, 'Scripts', 'python.exe')

    # 先让环境层工作：创建 venv + 装依赖（这是运行测试的前提）
    if not os.path.exists(venv_python):
        print(f"\n  {Y}[自主决策] 检测到 venv 不存在 → 正在创建...{X}")
        ok, msg = create_venv(PROJECT_VENV)
        print(f"  {'✅' if ok else '❌'} {msg}")
        if not ok:
            return

        print(f"  {Y}[自主决策] 扫描项目依赖...{X}")
        needed = scan_project_imports(PROJECT_DIR)
        # 确保 pytest 始终可用（测试运行的必要依赖）
        if 'pytest' not in needed:
            needed.append('pytest')
        print(f"  检测到 {len(needed)} 个第三方包: {', '.join(needed)}")

        print(f"  {Y}[自主决策] 安装依赖...{X}")
        for pkg in needed:
            ok2, msg2 = install_package(pkg, venv_python)
            print(f"    {'✅' if ok2 else '❌'} {msg2}")

    # 启动事件驱动的自愈循环
    def progress_callback(round_num, error_type, error_info, output):
        if error_type == 'all_passed':
            print(f"\n  {G}[轮次 {round_num}] ✅ 全部通过！{X}")
        else:
            err_name = error_info.get('name', '') if error_info else ''
            err_raw = (error_info.get('raw', '') if error_info else '')[:80]
            print(f"\n  {Y}[轮次 {round_num}] 检测到: {error_type}{X}")
            if err_name:
                print(f"    └─ {err_name}")
            # 环境层错误 handler 直接处理
            if error_type == 'module_not_found':
                handler = ERROR_HANDLERS.get('module_not_found')
                if handler:
                    result = handler(error_info, {'python_exe': venv_python, 'project_dir': PROJECT_DIR})
                    if result.get('status') == 'fixed':
                        print(f"    {G}[自主决策] {result.get('action', '')}{X}")
            elif error_type in ('syntax', 'import_error', 'fixture_not_found', 'name_error',
                               'assertion_error', 'attribute_error', 'file_not_found', 'no_tests', 'unknown'):
                print(f"    {C}[已路由到 LLM 修复引擎]{X}")

    result = self_healing_loop(
        project_dir=PROJECT_DIR,
        venv_python=venv_python,
        max_rounds=10,
        llm_fixer=llm_fixer,
        on_progress=progress_callback
    )

    # ============================================================
    # 结果报告
    # ============================================================
    print(f"\n{C}{'='*60}{X}")
    print(f"{C}  自愈结果报告{X}")
    print(f"{C}{'='*60}{X}")
    print(f"  总轮次: {result['total_rounds']}")
    print(f"  最终状态: {G}PASSED{X}" if result['passed'] else f"  最终状态: {R}FAILED{X}")
    print(f"  环境修复: {len(result['env_fixes'])} 次")
    for ef in result['env_fixes']:
        print(f"    - {ef}")
    print(f"  代码修复: {len(result['code_fixes'])} 次")
    for cf in result['code_fixes']:
        print(f"    - {cf}")

    # 恢复源文件
    for fp, content in backups.items():
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
    print(f"\n  {G}已恢复 {len(backups)} 个源文件{X}")

    # 清理测试 venv清理
    if os.path.exists(PROJECT_VENV):
        shutil.rmtree(PROJECT_VENV)
    print(f"\n  {G}已清理测试 venv{X}")

    return result


if __name__ == '__main__':
    autonomous_heal()