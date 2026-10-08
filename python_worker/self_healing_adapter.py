# -*- coding: utf-8 -*-
"""
self_healing_adapter.py — 自愈引擎适配器

将 test_autonomous.py 中验证过的自愈能力（停滞检测、规则引擎优先、
精简上下文、prompt 截断保护）织入实际 fix_step 流水线。

使用方式（在各 agent 的 fix_step.py 中）:
    from python_worker.self_healing_adapter import run_healing_fix
    run_healing_fix(step, context, source_files, error_info, llm_call_fn, project_dir)
"""

import re, os, subprocess, importlib.util, ast, sys, hashlib


# ================================================================
#  规则引擎 — 在调 LLM 之前先尝试本地修复
# ================================================================

def _rule_based_syntax_fix(code, error_info):
    """
    规则引擎修复常见语法错误，返回 (fixed_code, is_fixed)。
    只处理可靠的模式，不修复不明确的错误。
    """
    raw = error_info.get('raw', '').lower() if isinstance(error_info, dict) else str(error_info)

    # 缺少冒号
    if "expected ':'" in raw:
        pattern = r'^\s*(class |def |if |elif |else|for |while |with |try |except |finally)\s+.+[^:]\s*$'
        fixed = re.sub(pattern,
            lambda m: m.group(0).rstrip() + ':',
            code, flags=re.MULTILINE)
        if fixed != code:
            try:
                compile(fixed, '<fix>', 'exec')
                return fixed, True
            except SyntaxError:
                pass

    # 括号未闭合
    if "was never closed" in raw or "unexpected eof" in raw:
        # 简单策略：统计开括号数，补闭括号
        open_count = code.count('(') - code.count(')')
        if open_count > 0:
            fixed = code.rstrip() + ')' * open_count
            try:
                compile(fixed, '<fix>', 'exec')
                return fixed, True
            except SyntaxError:
                pass

    return code, False


def _rule_based_fixture_fix(code, fixture_name):
    """规则引擎：在函数定义前添加 @pytest.fixture 装饰器"""
    pattern = rf'^(def {re.escape(fixture_name)}\(.*?\):)'
    m = re.search(pattern, code, re.MULTILINE)
    if m:
        fixed = re.sub(pattern, '@pytest.fixture\n\\1', code, flags=re.MULTILINE)
        try:
            compile(fixed, '<fix>', 'exec')
            return fixed, True
        except SyntaxError:
            pass
    return code, False


def _commas_preserved(original, fixed):
    """检查修复后逗号数是否保留 >= 80%"""
    oc = original.count(',')
    fc = fixed.count(',')
    if oc == 0:
        return True
    return fc >= oc * 0.8


# ================================================================
#  ContractStubGenerator — 从 AST 提取纯契约签名
#  抹除实现细节，只保留类型注解和参数签名
# ================================================================

_DANGEROUS_DEFAULTS = {'lambda', 'open(', 'os.', 'Path(', 'pathlib', '__import__',
                       'eval(', 'exec(', 'compile(', 'getattr(', 'setattr('}
_MAGIC_METHODS = {'__init__', '__call__', '__eq__', '__hash__', '__repr__',
                  '__str__', '__len__', '__iter__', '__next__', '__enter__',
                  '__exit__', '__getitem__', '__setitem__', '__contains__'}


class ContractStubGenerator(ast.NodeVisitor):
    """从源码 AST 中提取纯契约签名，抹除所有实现细节"""

    def __init__(self, source_code):
        self.source = source_code
        self.stubs = []

    def extract(self):
        tree = ast.parse(self.source)
        self.visit(tree)
        return "\n".join(self.stubs)

    def visit_FunctionDef(self, node):
        self._emit_function(node, 'def')

    def visit_AsyncFunctionDef(self, node):
        self._emit_function(node, 'async def')

    def _emit_function(self, node, prefix):
        # 1. 装饰器 — 仅保留影响契约的类型
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id in (
                'property', 'abstractmethod', 'staticmethod', 'classmethod',
                'pytest.fixture',
            ):
                decorators.append(f"@{dec.id}")
            elif isinstance(dec, ast.Attribute) and dec.attr in ('validator', 'field', 'setter'):
                decorators.append(f"@...{dec.attr}")

        # 2. 参数签名
        args = []
        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, arg in enumerate(node.args.args):
            ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            default_idx = i - defaults_offset
            if default_idx >= 0:
                raw_default = ast.unparse(node.args.defaults[default_idx])
                if len(raw_default) > 20 or any(kw in raw_default for kw in _DANGEROUS_DEFAULTS):
                    safe_default = "..."
                else:
                    safe_default = raw_default
                args.append(f"{arg.arg}{ann}={safe_default}")
            else:
                args.append(f"{arg.arg}{ann}")

        # *args
        if node.args.vararg:
            a = node.args.vararg
            ann = f": {ast.unparse(a.annotation)}" if a.annotation else ""
            args.append(f"*{a.arg}{ann}")

        # keyword-only
        if node.args.kwonlyargs:
            if not node.args.vararg:
                args.append("*")
            for kw_arg, kw_def in zip(node.args.kwonlyargs, node.args.kw_defaults):
                ann = f": {ast.unparse(kw_arg.annotation)}" if kw_arg.annotation else ""
                default = f"={ast.unparse(kw_def)}" if kw_def else ""
                args.append(f"{kw_arg.arg}{ann}{default}")

        # **kwargs
        if node.args.kwarg:
            a = node.args.kwarg
            ann = f": {ast.unparse(a.annotation)}" if a.annotation else ""
            args.append(f"**{a.arg}{ann}")

        # 3. 返回值
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""

        # 4. 组装
        dec_line = "\n".join(decorators) + "\n" if decorators else ""
        sig = f"{dec_line}{prefix} {node.name}({', '.join(args)}){returns}: ..."
        self.stubs.append(sig)

    def visit_ClassDef(self, node):
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 公开方法 或 魔术方法
                if not item.name.startswith('_') or item.name in _MAGIC_METHODS:
                    self.visit(item)


def _build_contract_stubs(source_files):
    """为所有源文件生成契约签名 stub，返回 {symbol_name: {stub, hash, file}}"""
    contracts = {}
    for fp, code in source_files.items():
        if 'tests' in fp:
            continue
        try:
            gen = ContractStubGenerator(code)
            stubs_text = gen.extract()
            if not stubs_text:
                continue
            for line in stubs_text.split('\n'):
                if not line.strip() or line.strip().startswith('@'):
                    continue
                m = re.match(r'(?:async\s+)?def\s+(\w+)\(', line)
                if m:
                    name = m.group(1)
                    contracts[name] = {
                        'stub': line.strip(),
                        'hash': hashlib.md5(line.strip().encode()).hexdigest()[:8],
                        'file': fp,
                    }
        except SyntaxError:
            pass
    return contracts


def _format_contracts_for_prompt(contracts):
    """格式化契约为 LLM prompt 注入文本"""
    if not contracts:
        return ""
    lines = ["## FROZEN CONTRACTS (DO NOT MODIFY THESE SIGNATURES)",
             "The following interfaces are frozen by passing unit tests.",
             "Your fix MUST conform to these signatures exactly.",
             "To change a contract: fix its unit test first, then update the stub.",
             "",
             "```python"]
    for name, c in sorted(contracts.items()):
        lines.append(f"# {c['file']}")
        lines.append(c['stub'])
    lines.append("```")
    return "\n".join(lines)


# ================================================================
#  错误分类
# ================================================================

ERROR_PATTERNS = [
    (r"E\s+SyntaxError.*?expected ':'", 'syntax'),
    (r"E\s+SyntaxError.*?was never closed", 'syntax'),
    (r"SyntaxError.*?unterminated string", 'syntax'),
    (r"ERROR collecting.*?SyntaxError", 'syntax'),
    (r"ModuleNotFoundError:\s*No module named '([^']+)'", 'module_not_found'),
    (r"ImportError:\s*cannot import name '([^']+)'", 'import_error'),
    (r"NameError:\s*name '([^']+)' is not defined", 'name_error'),
    (r"fixture '([^']+)' not found", 'fixture_not_found'),
    (r"AssertionError", 'assertion_error'),
    (r"AttributeError:\s*'([^']+)' object has no attribute", 'attribute_error'),
    (r"FileNotFoundError:.*'([^']+)'", 'file_not_found'),
]

PRIORITY = {
    'module_not_found': 10,
    'no_tests': 9,
    'syntax': 8,
    'import_error': 7,
    'fixture_not_found': 6,
    'file_not_found': 5,
    'name_error': 4,
    'attribute_error': 3,
    'assertion_error': 3,
    'unknown': 1,
}


def classify_top_error(test_output):
    """从测试输出中提取最优先的错误"""
    best = ('unknown', {})
    best_prio = 0
    for pattern, etype in ERROR_PATTERNS:
        m = re.search(pattern, test_output, re.IGNORECASE)
        if m:
            name = m.group(1) if m.lastindex and m.lastindex >= 1 else ''
            info = {'name': name, 'raw': m.group(0)}
            prio = PRIORITY.get(etype, 0)
            if prio > best_prio:
                best = (etype, info)
                best_prio = prio
    if best_prio == 0:
        return ('all_passed', {})
    return best


# ================================================================
#  自愈主入口 — 被 fix_step 调用
# ================================================================

def run_healing_fix(source_files, error_info, test_output, project_dir,
                    llm_call_fn, max_rounds=5):
    """
    事件驱动的多轮自愈修复。

    参数:
        source_files: dict — {文件路径: 代码内容}
        error_info: str — 错误信息文本
        test_output: str — 完整测试输出
        project_dir: str — 项目根目录
        llm_call_fn: callable(prompt) -> str — LLM 调用函数
        max_rounds: int — 最大修复轮次

    返回:
        dict — {
            'fixed_files': {路径: 修复后代码},
            'fixes': [修复描述],
            'rounds': int,
            'passed': bool
        }
    """
    fixed_files = {}
    fixes = []
    last_error_key = None
    same_error_count = 0
    last_fix_count = 0
    STAGNATION_LIMIT = 3

    # 构建项目符号索引（用于 import 修复）
    symbol_index = _build_symbol_index(source_files, project_dir)

    for round_num in range(1, max_rounds + 1):
        # 1. 检查是否有新错误（我们需要重新运行测试来获取最新错误）
        # 在 adapter 场景中，我们依赖调用方传入的 error_info/test_output
        # 实际生产环境应该重新运行 pytest
        error_type, parsed_info = classify_top_error(test_output)

        if error_type == 'all_passed':
            return {
                'fixed_files': fixed_files,
                'fixes': fixes,
                'rounds': round_num,
                'passed': True
            }

        # 2. 停滞检测
        err_name = parsed_info.get('name', '')
        error_key = f"{error_type}:{err_name}"
        if error_key == last_error_key:
            same_error_count += 1
        else:
            last_error_key = error_key
            same_error_count = 1
            last_fix_count = len(fixes)

        if same_error_count >= STAGNATION_LIMIT and len(fixes) == last_fix_count:
            break

        # 3. 按类型路由修复
        result = _route_fix(error_type, parsed_info, source_files, test_output,
                           project_dir, llm_call_fn, symbol_index)

        if result.get('status') == 'fixed':
            action = result.get('action', '')
            fixes.append(action)
            # 更新 source_files 以反映修复结果
            for fp, content in result.get('updated_files', {}).items():
                source_files[fp] = content
                fixed_files[fp] = content

    return {
        'fixed_files': fixed_files,
        'fixes': fixes,
        'rounds': max_rounds,
        'passed': False
    }


def _build_symbol_index(source_files, project_dir):
    """从 source_files 构建精简符号索引（仅顶层类/函数）+ 契约签名"""
    index = {}
    contracts = _build_contract_stubs(source_files)
    for fp, code in source_files.items():
        try:
            tree = ast.parse(code)
            module_path = _file_to_module(fp, project_dir)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    entry = {
                        'module_path': module_path,
                        'file': fp,
                        'type': 'class',
                        'line': node.lineno,
                        'methods': methods,
                    }
                    if node.name in contracts:
                        entry['signature_stub'] = contracts[node.name]['stub']
                        entry['signature_hash'] = contracts[node.name]['hash']
                    index[node.name] = entry
                elif isinstance(node, ast.FunctionDef):
                    entry = {
                        'module_path': module_path,
                        'file': fp,
                        'type': 'function',
                        'line': node.lineno,
                        'args': [a.arg for a in node.args.args],
                    }
                    if node.name in contracts:
                        entry['signature_stub'] = contracts[node.name]['stub']
                        entry['signature_hash'] = contracts[node.name]['hash']
                    index[node.name] = entry
        except SyntaxError:
            pass
    return index


def _file_to_module(fp, project_dir):
    """文件路径 → Python 模块路径"""
    rel = os.path.relpath(fp, project_dir).replace('\\', '/')
    if rel.endswith('__init__.py'):
        rel = os.path.dirname(rel).replace('/', '.')
    elif rel.endswith('.py'):
        rel = rel[:-3].replace('/', '.')
    if rel.startswith('tests.'):
        return None  # 测试文件不作为导入源
    return rel


def _route_fix(error_type, error_info, source_files, test_output,
               project_dir, llm_call_fn, symbol_index):
    """根据错误类型路由到对应修复函数"""

    if error_type == 'syntax':
        return _fix_syntax_enhanced(error_info, source_files)

    elif error_type == 'fixture_not_found':
        return _fix_fixture_enhanced(error_info, source_files)

    elif error_type in ('name_error', 'import_error'):
        return _fix_import_enhanced(error_info, source_files, test_output,
                                    project_dir, llm_call_fn, symbol_index)

    elif error_type in ('assertion_error', 'attribute_error'):
        contracts_text = _format_contracts_for_prompt(
            _build_contract_stubs(source_files)
        )
        return _fix_logic_enhanced(error_info, source_files, test_output,
                                   llm_call_fn, contracts_text)

    return {'status': 'skipped'}


# ================================================================
#  语法修复（规则引擎优先 + LLM fallback）
# ================================================================

def _fix_syntax_enhanced(error_info, source_files):
    for fp, code in source_files.items():
        # 1. 先尝试规则引擎
        fixed, ok = _rule_based_syntax_fix(code, error_info)
        if ok:
            return {
                'status': 'fixed',
                'action': f'syntax_fix_rule:{fp}',
                'updated_files': {fp: fixed}
            }

    return {'status': 'failed', 'reason': 'syntax fix failed'}


# ================================================================
#  Fixture 修复（规则引擎）
# ================================================================

def _fix_fixture_enhanced(error_info, source_files):
    fixture_name = error_info.get('name', '')
    for fp, code in source_files.items():
        if fp.endswith('test_vote.py') or 'tests' in fp:
            fixed, ok = _rule_based_fixture_fix(code, fixture_name)
            if ok:
                return {
                    'status': 'fixed',
                    'action': f'fixture_fix:{fixture_name}',
                    'updated_files': {fp: fixed}
                }
    return {'status': 'failed', 'reason': f'fixture {fixture_name} fix failed'}


# ================================================================
#  Import 修复（精简上下文 + LLM）
# ================================================================

def _fix_import_enhanced(error_info, source_files, test_output,
                        project_dir, llm_call_fn, symbol_index):
    import_name = error_info.get('name', '')

    # 从符号索引找正确导入路径
    import_hint = ""
    sym = symbol_index.get(import_name)
    if sym:
        import_hint = (
            f"\n【正确导入路径】: from {sym['module_path']} import {import_name}"
            f"  (定义于 {sym['file']}:{sym['line']})\n"
        )

    for fp, code in source_files.items():
        if 'tests' not in fp:
            continue  # 只修测试文件
        rel = os.path.relpath(fp, project_dir)

        prompt = f"""{import_hint}
你是 Python import 修复专家。

【错误】: 缺少导入 '{import_name}'，导致 NameError
【文件】: {rel}

【错误输出】:
{test_output[-1000:]}

【代码】:
```python
{code}
```

规则:
1. 根据【正确导入路径】添加缺失的 import 语句
2. 严禁删除或修改已有 import 中的逗号(,)
3. 严禁修改代码逻辑，只添加缺失的 import
只输出 ```python 代码块。"""

        try:
            resp = llm_call_fn(prompt)
            fixed = _extract_code(resp)
            if fixed and len(fixed) > len(code) * 0.4 and _commas_preserved(code, fixed):
                try:
                    compile(fixed, fp, 'exec')
                    return {
                        'status': 'fixed',
                        'action': f'import_fix:{rel}',
                        'updated_files': {fp: fixed}
                    }
                except SyntaxError:
                    pass
        except Exception:
            pass

    return {'status': 'failed', 'reason': f'import {import_name} fix failed'}


# ================================================================
#  逻辑修复（多文件上下文 + LLM）
# ================================================================

def _fix_logic_enhanced(error_info, source_files, test_output, llm_call_fn, contracts_text=""):
    files_code = ""
    for fp, code in source_files.items():
        files_code += f"\n# === {fp} ===\n{code}"

    contract_block = ("\n" + contracts_text + "\n") if contracts_text else ""

    prompt = f"""你是 Python 修复专家。测试失败，需要修复代码。
{contract_block}
【错误】: {error_info.get('raw', '')}

【测试输出】:
{test_output[-1500:]}

【项目代码】:
{files_code[:8000]}

规则:
1. 优先修复被测试代码，其次修复测试代码
2. 保持代码结构不变
3. 严禁删除逗号(,)
4. 如有 FROZEN CONTRACTS，严禁修改其中的函数签名、参数类型和返回值类型
5. 如需改契约 → 同时修改对应的单元测试，并输出说明
输出: FILE: <文件路径>
```python
<完整代码>
```"""

    try:
        resp = llm_call_fn(prompt)
        blocks = _parse_file_blocks(resp)
        if blocks:
            # 接入点 3: 契约验证 — 检查 LLM 是否偷偷改了非目标函数签名
            clean_blocks, contract_warnings = _verify_contracts(source_files, blocks, error_info)
            action = f'logic_fix:{",".join(clean_blocks.keys())}'
            if contract_warnings:
                action += ' | ' + '; '.join(contract_warnings)
            return {
                'status': 'fixed',
                'action': action,
                'updated_files': clean_blocks,
                'warnings': contract_warnings,
            }
    except Exception:
        pass

    return {'status': 'failed', 'reason': 'logic fix failed'}


# ================================================================
#  契约验证 — LLM 修复后检查签名是否被破坏
# ================================================================

def _verify_contracts(source_files, fixed_blocks, error_info):
    """
    LLM 修复后验证非目标函数签名是否被修改。
    如果 LLM 偷偷改了契约 → 该文件的修复被拒绝，保持原文件。

    返回: (clean_blocks, warnings)
    """
    if not fixed_blocks:
        return fixed_blocks, []

    pre_contracts = _build_contract_stubs(source_files)
    if not pre_contracts:
        return fixed_blocks, []

    error_text = (error_info.get('raw', '') + ' ' + error_info.get('name', '')).lower()
    warnings = []
    clean_blocks = {}

    for fp, fixed_code in fixed_blocks.items():
        # 测试文件不参与契约验证
        if 'tests' in fp or fp not in source_files:
            clean_blocks[fp] = fixed_code
            continue

        post_contracts = _build_contract_stubs({fp: fixed_code})

        violated = []
        for name, pre_c in pre_contracts.items():
            if pre_c['file'] != fp:
                continue
            post_c = post_contracts.get(name)
            if not post_c:
                continue
            if post_c['hash'] != pre_c['hash']:
                if name.lower() in error_text:
                    continue
                violated.append(name)

        if violated:
            warnings.append(f"CONTRACT VIOLATION {fp}: {', '.join(violated)} reverted")
        else:
            clean_blocks[fp] = fixed_code

    return clean_blocks, warnings


# ================================================================
#  工具函数
# ================================================================

def _extract_code(resp):
    for marker in ["```python", "```"]:
        if marker in resp:
            return resp.split(marker, 1)[1].split("```", 1)[0].strip()
    return resp.strip()


def _parse_file_blocks(resp):
    blocks = {}
    current_file = None
    current_code = []
    for line in resp.split('\n'):
        s = line.strip()
        if s.upper().startswith('FILE:'):
            if current_file and current_code:
                blocks[current_file] = '\n'.join(current_code)
            current_file = s[5:].strip().strip(':')
            current_code = []
        elif s == '```python':
            current_code = []
        elif s == '```' and current_code:
            if current_file:
                blocks[current_file] = '\n'.join(current_code)
            current_file = None
            current_code = []
        elif current_file is not None:
            current_code.append(line)
    return blocks