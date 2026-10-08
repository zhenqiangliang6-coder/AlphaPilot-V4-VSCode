# -*- coding: utf-8 -*-
"""
AlphaPilot 自愈修复增强工具 — 三层自愈引擎

Layer 1: 语法层 (Syntax)     — 括号、引号、冒号、缩进
Layer 2: 逻辑层 (Logic)      — import 路径、函数签名、跨文件数据流
Layer 3: 环境层 (Environment) — venv、Python 解释器、第三方依赖

架构: 事件驱动 — 每轮 run_tests → parse_errors → route_to_handler → fix → repeat
"""

import ast
import os
import re
import subprocess
import sys


# ================================================================
#  改进 1: 项目地图
# ================================================================

def build_project_map(project_dir):
    """
    扫描项目所有 .py 文件，构建符号索引。

    Returns:
        {
            "symbols": {
                "VoteRequest": {
                    "type": "class",
                    "file": "src/village_vote_system/api/vote_router.py",
                    "line": 18,
                    "module_path": "src.village_vote_system.api.vote_router",
                    "parent_class": None
                },
                ...
            },
            "file_imports": {
                "tests/test_vote.py": {
                    "imports": [
                        {"name": "cast_vote", "module": "src.village_vote_system.api.vote_router", "alias": None},
                        ...
                    ],
                    "from_imports": [...]
                }
            }
        }
    """
    symbols = {}
    file_imports = {}

    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'venv', '.venv', 'node_modules')]
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            full_path = os.path.join(root, fn)
            rel_path = os.path.relpath(full_path, project_dir).replace('\\', '/')

            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source, filename=full_path)
            except (SyntaxError, UnicodeDecodeError):
                continue

            module_path = _path_to_module(rel_path)

            # 提取类和函数定义
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols[node.name] = {
                        'type': 'class',
                        'file': rel_path,
                        'line': node.lineno,
                        'module_path': module_path,
                        'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    }
                elif isinstance(node, ast.FunctionDef):
                    # 顶层函数（不在类内）
                    parent = _get_parent_class(node, tree)
                    if parent is None:
                        symbols[node.name] = {
                            'type': 'function',
                            'file': rel_path,
                            'line': node.lineno,
                            'module_path': module_path,
                            'args': [arg.arg for arg in node.args.args]
                        }

            # 提取 import 关系
            imports_list = []
            from_imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports_list.append({
                            'name': alias.name,
                            'alias': alias.asname
                        })
                elif isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    for alias in node.names:
                        from_imports.append({
                            'module': node.module,
                            'name': alias.name,
                            'alias': alias.asname,
                            'level': node.level  # 相对导入层级
                        })

            file_imports[rel_path] = {
                'imports': imports_list,
                'from_imports': from_imports,
                'functions': [k for k, v in symbols.items()
                              if v['file'] == rel_path and v['type'] == 'function'],
                'classes': [k for k, v in symbols.items()
                            if v['file'] == rel_path and v['type'] == 'class']
            }

    return {'symbols': symbols, 'file_imports': file_imports}


def _path_to_module(rel_path):
    """tests/test_vote.py -> tests.test_vote"""
    path_no_ext = rel_path.rsplit('.', 1)[0]
    return path_no_ext.replace('/', '.')


def _get_parent_class(func_node, tree):
    """判断函数是否在类内部"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if child is func_node:
                    return node.name
    return None


def format_project_map(project_map):
    """
    将项目地图格式化为 LLM 可读的文本。

    返回:
        str — 例如:
        【项目符号索引】
        - VoteRequest (class) → src/village_vote_system/api/vote_router.py:18
          导入: from src.village_vote_system.api.vote_router import VoteRequest
        - Candidate (class) → src/village_vote_system/models/candidate.py:3
          导入: from src.village_vote_system.models.candidate import Candidate
    """
    symbols = project_map.get('symbols', {})
    lines = ['【项目符号索引 — 以下符号在项目中的位置】']

    for name, info in sorted(symbols.items()):
        mod = info['module_path']
        file = info['file']
        typ = info['type']
        line = info['line']
        if typ == 'class':
            methods_str = ', '.join(info.get('methods', []))
            lines.append(
                f"- {name} (class) → {file}:{line}  "
                f"导入: from {mod} import {name}  "
                f"方法: [{methods_str}]"
            )
        else:
            args_str = ', '.join(info.get('args', []))
            lines.append(
                f"- {name} (function) → {file}:{line}  "
                f"导入: from {mod} import {name}  "
                f"参数: ({args_str})"
            )

    return '\n'.join(lines)


# ================================================================
#  改进 2: 多文件上下文
# ================================================================

def build_multifile_context(target_file, project_map, project_dir):
    """
    给定一个目标文件，找出它依赖的源文件，读取它们的代码，
    构建多文件上下文字符串供 LLM 使用。

    target_file: 如 "tests/test_vote.py"
    project_map: build_project_map() 的返回值
    project_dir: 项目根目录

    返回:
        str — 例如:
        ### 关联文件: src/village_vote_system/api/vote_router.py
        ```python
        ...完整代码...
        ```
    """
    imports_info = project_map.get('file_imports', {}).get(target_file, {})
    from_imports = imports_info.get('from_imports', [])
    symbols = project_map.get('symbols', {})

    related_files = set()

    # 从 from_imports 找关联文件
    for imp in from_imports:
        module = imp['module']
        name = imp['name']
        level = imp.get('level', 0)

        if level > 0:
            # 相对导入：根据 target_file 的相对路径解析
            target_dir = os.path.dirname(target_file)
            resolved = _resolve_relative_import(module, level, target_dir, project_dir)
            if resolved:
                related_files.add(resolved)
        else:
            # 绝对导入：查符号表找文件
            if name in symbols:
                related_files.add(symbols[name]['file'])
            else:
                # 可能是模块级导入，尝试解析模块路径
                module_file = module.replace('.', '/') + '.py'
                candidate = os.path.join(project_dir, module_file)
                if os.path.exists(candidate):
                    related_files.add(os.path.relpath(candidate, project_dir).replace('\\', '/'))

    # 如果没找到关联文件，尝试读取所有非测试源文件
    if not related_files:
        for file_path, info in project_map.get('file_imports', {}).items():
            if 'test' not in file_path.lower() and file_path != target_file:
                if info.get('functions') or info.get('classes'):
                    related_files.add(file_path)

    # 最多取 5 个关联文件
    blocks = []
    for rf in sorted(related_files)[:5]:
        full_path = os.path.join(project_dir, rf)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                code = f.read()
            blocks.append(f'### 关联文件: {rf}\n```python\n{code}\n```\n')
        except (OSError, UnicodeDecodeError):
            pass

    if blocks:
        return '\n【关联文件代码】\n' + '\n'.join(blocks)
    return ''


def _resolve_relative_import(module, level, target_dir, project_dir):
    """解析相对导入路径"""
    parts = target_dir.replace('\\', '/').split('/')
    if level > len(parts):
        return None
    base = '/'.join(parts[:-level]) if level > 0 else '/'.join(parts)
    if module:
        module_path = module.replace('.', '/') + '.py'
        full_path = os.path.join(project_dir, base, module_path)
    else:
        full_path = os.path.join(project_dir, base, '__init__.py')
    if os.path.exists(full_path):
        return os.path.relpath(full_path, project_dir).replace('\\', '/')
    return None


# ================================================================
#  改进 3: AST 级验证
# ================================================================

def validate_imports(fixed_code, project_map, file_path='<string>'):
    """
    验证修复后的代码中所有 import 目标是否在项目中存在。
    跳过标准库和知名第三方包。

    Args:
        fixed_code: LLM 修复后的代码
        project_map: build_project_map() 的返回值
        file_path: 文件名（用于错误信息）

    Returns:
        (ok: bool, errors: list[str])
    """
    symbols = project_map.get('symbols', {})
    errors = []

    # 已知的标准库和第三方包（不需要在项目符号索引中）
    KNOWN_EXTERNAL = frozenset({
        'os', 'sys', 'json', 're', 'math', 'time', 'datetime', 'typing',
        'collections', 'itertools', 'functools', 'pathlib', 'io', 'shutil',
        'tempfile', 'subprocess', 'logging', 'hashlib', 'uuid', 'random',
        'abc', 'base64', 'copy', 'csv', 'enum', 'glob', 'gzip', 'html',
        'http', 'importlib', 'inspect', 'pickle', 'platform', 'pprint',
        'queue', 'signal', 'socket', 'sqlite3', 'ssl', 'statistics',
        'string', 'struct', 'textwrap', 'threading', 'traceback', 'unittest',
        'urllib', 'warnings', 'weakref', 'xml', 'zipfile', 'contextlib',
        'dataclasses', 'asyncio', 'concurrent', 'configparser', 'secrets',
        'pytest', '_pytest', 'fastapi', 'pydantic', 'uvicorn', 'starlette',
        'requests', 'aiohttp', 'numpy', 'pandas', 'click', 'rich', 'yaml',
        'toml', 'dotenv', 'PIL', 'cv2', 'torch', 'tensorflow', 'jinja2',
        'flask', 'django', 'sqlalchemy', 'alembic', 'pymongo', 'redis',
        'celery', 'pika', 'kafka', 'grpc', 'protobuf',
    })

    try:
        tree = ast.parse(fixed_code, filename=file_path)
    except SyntaxError as e:
        return False, [f'SyntaxError: {e}']

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None or node.level > 0:
                continue  # 相对导入暂不验证
            # 跳过已知的外部包
            top_module = node.module.split('.')[0]
            if top_module in KNOWN_EXTERNAL:
                continue
            for alias in node.names:
                if alias.name == '*':
                    continue
                if alias.name not in symbols:
                    errors.append(
                        f'未知导入: from {node.module} import {alias.name} '
                        f'(行 {node.lineno}) — 项目符号索引中未找到'
                    )

    return len(errors) == 0, errors


def validate_function_signatures(test_code, source_files, project_dir):
    """
    验证测试代码中调用的函数/类是否与源文件定义匹配。

    Args:
        test_code: 测试文件代码
        source_files: dict[str, str] — {相对路径: 源代码}
        project_dir: 项目根目录

    Returns:
        (ok: bool, issues: list[str])
    """
    issues = []

    try:
        test_tree = ast.parse(test_code)
    except SyntaxError as e:
        return False, [f'SyntaxError in test: {e}']

    # 收集测试代码中的函数调用/类实例化
    test_calls = {}
    for node in ast.walk(test_tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                test_calls[node.func.id] = node
            elif isinstance(node.func, ast.Attribute):
                test_calls[node.func.attr] = node

    # 收集源文件中的函数/类定义
    source_defs = {}
    for rel_path, code in source_files.items():
        try:
            src_tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(src_tree):
            if isinstance(node, ast.FunctionDef):
                source_defs[node.name] = {
                    'args': [arg.arg for arg in node.args.args],
                    'file': rel_path,
                    'line': node.lineno
                }
            elif isinstance(node, ast.ClassDef):
                source_defs[node.name] = {
                    'type': 'class',
                    'file': rel_path,
                    'line': node.lineno
                }

    # 交叉验证
    for call_name, call_node in test_calls.items():
        if call_name in ('print', 'len', 'range', 'int', 'str', 'float',
                         'bool', 'list', 'dict', 'set', 'tuple', 'open',
                         'isinstance', 'hasattr', 'getattr', 'setattr',
                         'next', 'iter', 'enumerate', 'zip', 'map', 'filter',
                         'sorted', 'reversed', 'any', 'all', 'max', 'min',
                         'sum', 'abs', 'round', 'type', 'super', 'id',
                         'os', 'json', 'pytest', 'shutil', 'tempfile'):
            continue  # 内置/标准库

        if call_name not in source_defs:
            issues.append(
                f'测试调用了 "{call_name}" (行 {call_node.lineno})，'
                f'但未在源文件中找到其定义'
            )
        else:
            defn = source_defs[call_name]
            if defn.get('type') != 'class':
                expected_args = len(defn.get('args', []))
                actual_args = len(call_node.args) + len(call_node.keywords)
                if expected_args != actual_args:
                    issues.append(
                        f'"{call_name}" 参数不匹配: 定义有 {expected_args} 个参数，'
                        f'测试传了 {actual_args} 个 (行 {call_node.lineno})'
                    )

    return len(issues) == 0, issues


# ================================================================
#  快速诊断（整合三个改进）
# ================================================================

def quick_diagnose(project_dir, target_files):
    """
    对指定文件快速诊断，返回完整的上下文信息。

    Args:
        project_dir: 项目根目录
        target_files: list[str] — 需要诊断的文件路径

    Returns:
        {
            'project_map': ...,
            'project_map_text': str,
            'multi_file_contexts': {file_path: context_str},
            'import_issues': {file_path: [errors]},
            'signature_issues': [issues]
        }
    """
    pm = build_project_map(project_dir)
    pm_text = format_project_map(pm)

    contexts = {}
    import_issues = {}
    all_sig_issues = []

    for tf in target_files:
        rel_tf = os.path.relpath(tf, project_dir).replace('\\', '/') if os.path.isabs(tf) else tf
        contexts[rel_tf] = build_multifile_context(rel_tf, pm, project_dir)

        with open(tf, 'r', encoding='utf-8') as f:
            code = f.read()
        ok, errs = validate_imports(code, pm, rel_tf)
        import_issues[rel_tf] = errs

        # 收集源文件用于签名验证
        related = {}
        for rpath in _get_related_paths(rel_tf, pm, project_dir):
            full = os.path.join(project_dir, rpath)
            if os.path.exists(full):
                with open(full, 'r', encoding='utf-8') as f:
                    related[rpath] = f.read()
        ok, sig_issues = validate_function_signatures(code, related, project_dir)
        all_sig_issues.extend(sig_issues)

    return {
        'project_map': pm,
        'project_map_text': pm_text,
        'multi_file_contexts': contexts,
        'import_issues': import_issues,
        'signature_issues': all_sig_issues
    }


def _get_related_paths(target_file, project_map, project_dir):
    """获取与目标文件关联的所有源文件路径"""
    imports_info = project_map.get('file_imports', {}).get(target_file, {})
    from_imports = imports_info.get('from_imports', [])
    symbols = project_map.get('symbols', {})
    related = set()

    for imp in from_imports:
        module = imp['module']
        name = imp['name']
        level = imp.get('level', 0)
        if level > 0:
            resolved = _resolve_relative_import(module, level,
                                                 os.path.dirname(target_file), project_dir)
            if resolved:
                related.add(resolved)
        else:
            if name in symbols:
                related.add(symbols[name]['file'])
            module_file = module.replace('.', '/') + '.py'
            candidate = os.path.join(project_dir, module_file)
            if os.path.exists(candidate):
                related.add(os.path.relpath(candidate, project_dir).replace('\\', '/'))

    return list(related)


# ================================================================
#  Layer 3: 环境层自愈 (Environment Self-Healing)
# ================================================================

def check_venv_exists(venv_path):
    """检查 venv 是否存在且包含 Python 解释器"""
    if not venv_path:
        return False, "venv 路径未配置"
    python_exe = _get_venv_python(venv_path)
    if not os.path.exists(python_exe):
        return False, f"Python 解释器不存在: {python_exe}"
    # 验证可以执行
    try:
        r = subprocess.run([python_exe, '--version'],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, f"Python 不可执行: {r.stderr.strip()}"
    except Exception as e:
        return False, str(e)


def _get_venv_python(venv_path):
    """获取 venv 中的 Python 可执行文件路径"""
    if sys.platform == 'win32':
        return os.path.join(venv_path, 'Scripts', 'python.exe')
    return os.path.join(venv_path, 'bin', 'python')


def create_venv(venv_path):
    """创建新的虚拟环境"""
    system_python = sys.executable
    try:
        r = subprocess.run([system_python, '-m', 'venv', venv_path],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return False, f"venv 创建失败: {r.stderr.strip()}"
        # 验证创建成功
        ok, msg = check_venv_exists(venv_path)
        return ok, msg
    except Exception as e:
        return False, str(e)


def install_package(package_name, python_exe):
    """安装单个 Python 包"""
    try:
        r = subprocess.run(
            [python_exe, '-m', 'pip', 'install', package_name, '-q'],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            return True, f"{package_name} 安装成功"
        return False, f"{package_name} 安装失败: {r.stderr.strip()[-200:]}"
    except Exception as e:
        return False, str(e)


def scan_project_imports(project_dir):
    """
    扫描项目中所有 .py 文件的 import 语句，
    提取第三方依赖包名（排除标准库和项目内部模块）。

    Returns:
        list[str] — 如 ['fastapi', 'pydantic', 'uvicorn']
    """
    STD_LIB = frozenset({
        'os', 'sys', 'json', 're', 'math', 'time', 'datetime', 'typing',
        'collections', 'itertools', 'functools', 'pathlib', 'io', 'shutil',
        'tempfile', 'subprocess', 'logging', 'hashlib', 'uuid', 'random',
        'abc', 'base64', 'copy', 'csv', 'enum', 'glob', 'gzip', 'html',
        'http', 'importlib', 'inspect', 'pickle', 'platform', 'pprint',
        'queue', 'signal', 'socket', 'sqlite3', 'ssl', 'statistics',
        'string', 'struct', 'textwrap', 'threading', 'traceback', 'unittest',
        'urllib', 'warnings', 'weakref', 'xml', 'zipfile', 'contextlib',
        'dataclasses', 'asyncio', 'concurrent', 'configparser', 'secrets',
        'email', 'ctypes', 'numbers', 'decimal', 'fractions', 'operator',
        'argparse', 'getopt', 'getpass', 'cmd', 'codecs', 'dis', 'gc',
        'atexit', 'calendar', 'heapq', 'bisect', 'array', 'audioop',
        'binascii', 'builtins', 'errno', 'faulthandler', 'mmap', 'msvcrt',
        'readline', 'resource', 'select', 'selectors', 'sysconfig',
        'termios', 'tty', 'winreg', 'zlib', '_thread',
    })

    # 收集项目自身的顶级包名，避免误判为第三方依赖
    project_packages = set()
    for entry in os.listdir(project_dir):
        entry_path = os.path.join(project_dir, entry)
        if os.path.isdir(entry_path):
            init_py = os.path.join(entry_path, '__init__.py')
            if os.path.exists(init_py) or entry in ('src',):
                project_packages.add(entry)
        elif entry.endswith('.py') and entry != '__init__.py':
            project_packages.add(entry[:-3])

    imports = set()
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in (
            '__pycache__', '.git', 'venv', '.venv', '.venv_test',
            'node_modules', 'generated', 'env', 'dist', 'build',
            '*.egg-info', '.pytest_cache', '.mypy_cache', '.tox',
        ) and not d.startswith('.')]
        for fn in files:
            if not fn.endswith('.py'):
                continue
            fpath = os.path.join(root, fn)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top = alias.name.split('.')[0]
                            if top not in STD_LIB and top not in project_packages:
                                imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.level == 0:
                            top = node.module.split('.')[0]
                            if top not in STD_LIB and top not in project_packages:
                                imports.add(node.module.split('.')[0])
            except (SyntaxError, UnicodeDecodeError, RecursionError):
                continue

    return sorted(imports)


def ensure_dependencies(python_exe, required_packages):
    """
    确保所有必需包已安装。

    Args:
        python_exe: venv 中的 python 路径
        required_packages: 需要安装的包名列表

    Returns:
        (success_count, fail_count, details: list[str])
    """
    details = []
    success = 0
    fail = 0

    for pkg in required_packages:
        ok, msg = install_package(pkg, python_exe)
        details.append(msg)
        if ok:
            success += 1
        else:
            fail += 1

    return success, fail, details


def environment_self_healing(project_dir, venv_path=None):
    """
    环境层自愈：检测并修复运行环境问题。

    Args:
        project_dir: 项目根目录
        venv_path: venv 路径（可选，默认查找 project_dir/.venv）

    Returns:
        {
            'venv_ok': bool,
            'venv_message': str,
            'dependencies_installed': [str],
            'dependencies_failed': [str],
            'python_exe': str | None,
            'actions_taken': [str]
        }
    """
    if venv_path is None:
        for candidate in [os.path.join(project_dir, '.venv'),
                          os.path.join(project_dir, 'venv')]:
            if os.path.exists(candidate):
                venv_path = candidate
                break

    result = {
        'venv_ok': False,
        'venv_message': '',
        'dependencies_installed': [],
        'dependencies_failed': [],
        'python_exe': None,
        'actions_taken': []
    }

    # Step 1: Check/Create venv
    if venv_path:
        ok, msg = check_venv_exists(venv_path)
        result['venv_ok'] = ok
        result['venv_message'] = msg
        if not ok:
            ok2, msg2 = create_venv(venv_path)
            result['venv_ok'] = ok2
            result['venv_message'] = msg2
            result['actions_taken'].append(f'创建 venv: {venv_path}')
    else:
        result['venv_message'] = '未指定 venv 路径，使用系统 Python'
        result['venv_ok'] = True

    python_exe = (_get_venv_python(venv_path) if venv_path and os.path.exists(_get_venv_python(venv_path))
                  else sys.executable)
    result['python_exe'] = python_exe

    # Step 2: Scan & Install dependencies
    needed = scan_project_imports(project_dir)
    if needed:
        success, fail, details = ensure_dependencies(python_exe, needed)
        result['dependencies_installed'] = [d for d in details if '成功' in d]
        result['dependencies_failed'] = [d for d in details if '失败' in d]
        result['actions_taken'].extend(
            [f'安装依赖: {n}' for n in needed if any(n in d and '成功' in d for d in details)]
        )

    return result


# ================================================================
#  Error Router: 事件驱动的自愈引擎
# ================================================================

def parse_pytest_errors(output):
    """
    解析 pytest 输出，提取结构化的错误列表。

    Returns:
        list[dict] — 每个 dict 包含:
            type: 'syntax' | 'module_not_found' | 'import_error' |
                  'fixture_not_found' | 'file_not_found' |
                  'attribute_error' | 'assertion_error' | 'unknown'
            raw: 原始错误行
            file: 出错的源文件路径 (如可解析)
            name: 错误涉及的名称 (模块名/fixture名/文件名)
            line: 行号 (如可解析)
    """
    errors = []

    patterns = [
        # 运行时语法错误 (traceback 格式)
        (r"E\s+File \"(.+?)\", line (\d+).*\n.*\nE\s+SyntaxError:\s*(.+)", 'syntax'),
        # 收集阶段语法错误 (pytest 直接输出)
        (r"E\s+SyntaxError:\s*(.+?)(?:\n|$)", 'syntax'),
        # compile 错误格式
        (r"SyntaxError:\s*(.+?)(?:\n|$)", 'syntax'),

        # 模块未找到
        (r"ModuleNotFoundError:\s*No module named '([^']+)'", 'module_not_found'),

        # Import 错误
        (r"ImportError:\s*cannot import name '([^']+)'", 'import_error'),
        (r"ImportError:\s*(.+?)(?:\n|$)", 'import_error'),

        # Fixture 未找到
        (r"fixture '(\w+)' not found", 'fixture_not_found'),

        # 文件未找到
        (r"FileNotFoundError:\s*\[Errno 2\] No such file or directory:\s*'([^']+)'", 'file_not_found'),

        # 属性错误
        (r"AttributeError:\s*(.+?)(?:\n|$)", 'attribute_error'),

        # 名称错误 (NameError)
        (r"NameError:\s*name '([^']+)' is not defined", 'name_error'),

        # 断言错误
        (r"AssertionError:\s*(.+?)(?:\n|$)", 'assertion_error'),
        (r"assert (.+?)(?:\n|$)", 'assertion_error'),
    ]

    for pattern, err_type in patterns:
        for match in re.finditer(pattern, output, re.MULTILINE | re.DOTALL):
            groups = match.groups()
            err_info = {
                'type': err_type,
                'raw': match.group(0).strip()[:200],
            }
            if err_type == 'syntax' and len(groups) >= 3:
                err_info['file'] = groups[0]
                err_info['line'] = int(groups[1])
                err_info['name'] = groups[2].strip()
            elif err_type == 'module_not_found':
                err_info['name'] = groups[0]
            elif err_type == 'import_error':
                err_info['name'] = groups[0]
            elif err_type == 'fixture_not_found':
                err_info['name'] = groups[0]
            elif err_type == 'file_not_found':
                err_info['name'] = groups[0]
            elif err_type == 'name_error':
                err_info['name'] = groups[0]
            errors.append(err_info)

    # 检查 exit code / no tests collected
    if not errors:
        if 'no tests ran' in output.lower() or 'no tests collected' in output.lower():
            errors.append({
                'type': 'no_tests',
                'raw': 'No tests collected — possible syntax or import errors in test modules',
                'name': 'unknown'
            })

    return errors


def classify_top_error(output):
    """
    从 pytest 输出中提取"第一个需要处理的错误"。
    返回错误分类字符串，用于路由。
    """
    errors = parse_pytest_errors(output)
    if not errors:
        # 检查是否完全通过
        if re.search(r'(\d+)\s+passed', output):
            return 'all_passed', None
        return 'unknown', {'raw': output[:500]}

    # 按优先级排序：环境 > 语法 > 导入 > fixture > 文件 > 属性 > 断言
    priority = {
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

    errors.sort(key=lambda e: priority.get(e['type'], 0), reverse=True)
    top = errors[0]
    return top['type'], top


# ================================================================
#  Error Handler Registry (可扩展)
# ================================================================

# 全局 handler 注册表
# key: error_type  string
# value: callable(error_dict, context_dict) -> dict result
ERROR_HANDLERS = {}


def register_handler(error_type):
    """装饰器：注册错误处理器"""
    def decorator(func):
        ERROR_HANDLERS[error_type] = func
        return func
    return decorator


# ---------- 内置 handlers ----------

@register_handler('module_not_found')
def handle_module_not_found(error, context):
    """
    处理 ModuleNotFoundError: pip install 缺失的包
    """
    python_exe = context.get('python_exe', sys.executable)
    package = error.get('name', '')
    if not package:
        return {'status': 'skipped', 'reason': '无法解析缺失的模块名'}

    ok, msg = install_package(package, python_exe)
    return {
        'status': 'fixed' if ok else 'failed',
        'action': f'pip install {package}',
        'message': msg,
        'retry': ok
    }


@register_handler('no_tests')
def handle_no_tests(error, context):
    """
    处理"测试无法收集"——通常是语法错误或 import 错误导致的连锁反应。
    交给 syntax/import_error handlers 处理。
    """
    return {
        'status': 'delegated',
        'message': '测试无法收集，将尝试扫描语法错误和 import 错误',
        'retry': True
    }


@register_handler('fixture_not_found')
def handle_fixture_not_found(error, context):
    """
    Fixture 未注册 — 需要 LLM 修复测试代码
    返回标记让外部 LLM handler 处理
    """
    return {
        'status': 'needs_llm',
        'action': 'fix_fixture',
        'fixture_name': error.get('name', ''),
        'message': f'fixture "{error.get("name", "")}" 需要 LLM 修复',
        'retry': False  # 等待 LLM 修复后再重试
    }


@register_handler('file_not_found')
def handle_file_not_found(error, context):
    """
    文件未找到 — 可能是路径不匹配
    创建必要的目录结构
    """
    filename = error.get('name', '')
    project_dir = context.get('project_dir', '')
    if filename and project_dir:
        target = os.path.join(project_dir, filename)
        parent = os.path.dirname(target)
        if not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
            return {
                'status': 'fixed',
                'action': f'mkdir -p {parent}',
                'message': f'创建目录: {parent}',
                'retry': True
            }
    return {
        'status': 'needs_llm',
        'action': 'fix_path',
        'message': f'路径不匹配: {filename}',
        'retry': False
    }


@register_handler('import_error')
def handle_import_error(error, context):
    """
    ImportError — 需要 LLM 查项目地图修正路径
    """
    return {
        'status': 'needs_llm',
        'action': 'fix_import',
        'import_name': error.get('name', ''),
        'message': f'import 错误: {error.get("name", "")}',
        'retry': False
    }


@register_handler('syntax')
def handle_syntax_error(error, context):
    """
    SyntaxError — 需要 LLM 修复代码
    """
    return {
        'status': 'needs_llm',
        'action': 'fix_syntax',
        'file': error.get('file', ''),
        'line': error.get('line', 0),
        'message': error.get('name', 'SyntaxError'),
        'retry': False
    }


@register_handler('assertion_error')
def handle_assertion_error(error, context):
    """
    AssertionError — 业务逻辑错误，需要 LLM 推理
    """
    return {
        'status': 'needs_llm',
        'action': 'fix_logic',
        'message': error.get('raw', ''),
        'retry': False
    }


@register_handler('attribute_error')
def handle_attribute_error(error, context):
    """
    AttributeError — 对象缺少属性，需要 LLM
    """
    return {
        'status': 'needs_llm',
        'action': 'fix_attribute',
        'message': error.get('raw', ''),
        'retry': False
    }


# ================================================================
#  自愈主循环 (事件驱动)
# ================================================================

def self_healing_loop(project_dir, venv_python, max_rounds=10,
                       llm_fixer=None, on_progress=None):
    """
    事件驱动的自愈主循环。

    每轮:
      1. 运行测试
      2. 解析错误
      3. 按优先级取最紧急的错误
      4. 路由到 handler
      5. 环境层 handler 直接执行；代码层 handler 调用 LLM
      6. 重复直到通过或超过最大轮次

    Args:
        project_dir: 项目根目录
        venv_python: Python 解释器路径 (venv 中的)
        max_rounds: 最大自愈轮次
        llm_fixer: callable(errors, output, context) → 用于代码层修复
        on_progress: callable(round_num, result) → 进度回调

    Returns:
        {
            'total_rounds': int,
            'final_output': str,
            'passed': bool,
            'history': list[dict],
            'env_fixes': list[str],
            'code_fixes': list[str]
        }
    """
    history = []
    env_fixes = []
    code_fixes = []
    last_error_key = None
    same_error_count = 0
    last_code_fix_count = 0
    STAGNATION_LIMIT = 3  # 连续 N 轮同错误且无新修复 → 判定停滞

    context = {
        'project_dir': project_dir,
        'python_exe': venv_python,
    }

    for round_num in range(1, max_rounds + 1):
        # Step 1: Run tests
        try:
            r = subprocess.run(
                [venv_python, '-m', 'pytest', 'tests/', '-v', '--tb=short', '-x'],
                cwd=project_dir, capture_output=True, text=True, timeout=60
            )
            output = r.stdout + r.stderr
            exit_code = r.returncode
        except FileNotFoundError:
            output = f"FAILED: Python 解释器不存在: {venv_python}"
            exit_code = 1
        except subprocess.TimeoutExpired:
            output = "TIMEOUT: 测试运行超过 60 秒"
            exit_code = 1

        history.append({
            'round': round_num,
            'output': output,
            'exit_code': exit_code
        })

        # Step 2: Classify top error
        error_type, error_info = classify_top_error(output)

        if on_progress:
            on_progress(round_num, error_type, error_info, output)

        # Step 3: All passed?
        if error_type == 'all_passed':
            return {
                'total_rounds': round_num,
                'final_output': output,
                'passed': True,
                'history': history,
                'env_fixes': env_fixes,
                'code_fixes': code_fixes
            }

        # Step 3.5: Stagnation detection — 同一错误连续失败，无新修复
        err_name = error_info.get('name', '') if error_info else ''
        error_key = f"{error_type}:{err_name}"
        if error_key == last_error_key:
            same_error_count += 1
        else:
            last_error_key = error_key
            same_error_count = 1
            last_code_fix_count = len(code_fixes)

        if same_error_count >= STAGNATION_LIMIT and len(code_fixes) == last_code_fix_count:
            print(f"  [停滞检测] 连续 {same_error_count} 轮错误 '{error_key}' 无进展，终止重试")
            break

        # Step 4: Route to handler
        handler = ERROR_HANDLERS.get(error_type)
        if not handler:
            if llm_fixer:
                result = llm_fixer(error_type, error_info, output, context)
                if result and result.get('status') == 'fixed':
                    code_fixes.append(result.get('action', 'llm_fix'))
            history[-1]['handled'] = False
            history[-1]['error_type'] = error_type
            continue

        result = handler(error_info, context)

        history[-1]['handled'] = True
        history[-1]['error_type'] = error_type
        history[-1]['handler_result'] = result

        if result.get('status') == 'fixed':
            env_fixes.append(result.get('action', ''))
        elif result.get('status') == 'needs_llm':
            if llm_fixer:
                llm_result = llm_fixer(error_type, error_info, output, context)
                if llm_result and llm_result.get('status') == 'fixed':
                    code_fixes.append(llm_result.get('action', 'llm_fix'))
                history[-1]['llm_result'] = llm_result
        # 其他情况继续重试

    return {
        'total_rounds': max_rounds,
        'final_output': history[-1]['output'] if history else '',
        'passed': False,
        'history': history,
        'env_fixes': env_fixes,
        'code_fixes': code_fixes
    }