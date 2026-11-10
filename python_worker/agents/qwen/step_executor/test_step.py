# step_executor/test_step.py
# ---------------------------------------------------------
# v3.3 真实 pytest 执行
# - 移除 FAKE_PYTEST，接入真实 pytest 子进程
# - 结构化测试结果：passed / exit_code / stdout / stderr / timed_out
# - 处理 pytest 未安装、收集失败、超时等异常路径
#
# P1 (2026-11-03): 确定性测试命令发现 + 依赖安装 + TDD 闭环
# - _discover_project_test_commands(): 扫描项目配置文件，不依赖 LLM
# - _install_deps_for_tests(): 测试前自动检查/安装缺失依赖
# - run_test_step() 支持 run_tests intent 分支
# ---------------------------------------------------------

import json
import os
import re
import sys
import time
import subprocess
import uuid
from pathlib import Path

from .utils import extract_code
from .prompts import test_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ..qwen_api import call_qwen_stream, call_llm


_PYTEST_TIMEOUT = 120


# ================================================================
#  P1: 确定性测试命令发现（不依赖 LLM）
# ================================================================

_TEST_COMMAND_SOURCES = [
    # (检查条件函数, 提取命令函数, 语言标签)
]


def discover_project_test_commands(workspace_path: str) -> list:
    """确定性扫描项目配置文件，发现可执行的测试命令。
    
    扫描顺序: package.json → pyproject.toml → Makefile → 测试配置文件
    返回: [{command: str, source: str, language: str}, ...]
    """
    discovered = []
    root = Path(workspace_path)

    # 1. package.json (JavaScript/TypeScript)
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                cmd = scripts["test"]
                discovered.append({
                    "command": cmd,
                    "source": "package.json#scripts.test",
                    "language": _detect_js_flavor(root, pkg),
                })
        except (json.JSONDecodeError, OSError):
            pass

    # 2. pyproject.toml / setup.cfg (Python)
    pyproj = root / "pyproject.toml"
    if pyproj.is_file():
        try:
            discovered.append({
                "command": "python -m pytest -v --tb=short",
                "source": "pyproject.toml",
                "language": "python",
            })
        except Exception:
            pass
    elif (root / "setup.cfg").is_file() or (root / "setup.py").is_file():
        discovered.append({
            "command": "python -m pytest -v --tb=short",
            "source": "setup.cfg / setup.py",
            "language": "python",
        })

    # 3. pytest.ini / tox.ini (Python)
    if (root / "pytest.ini").is_file() or (root / "tox.ini").is_file():
        if not any(d["language"] == "python" for d in discovered):
            discovered.append({
                "command": "python -m pytest -v --tb=short",
                "source": "pytest.ini / tox.ini",
                "language": "python",
            })

    # 4. Makefile / justfile
    for makefile in ["Makefile", "makefile", "justfile"]:
        mf = root / makefile
        if mf.is_file():
            try:
                content = mf.read_text(encoding="utf-8")
                if re.search(r"^\s*test\s*:", content, re.MULTILINE):
                    discovered.append({
                        "command": "make test",
                        "source": makefile,
                        "language": _guess_make_lang(root),
                    })
                    break
            except (OSError, UnicodeDecodeError):
                pass

    # 5. 测试配置文件兜底检测
    for cfg, lang, cmd in _TEST_CONFIG_DETECTORS:
        if (root / cfg).is_file():
            if not any(d["command"] == cmd for d in discovered):
                discovered.append({
                    "command": cmd,
                    "source": cfg,
                    "language": lang,
                })

    # 6. 若项目有测试目录但无配置，按语言兜底
    if not discovered:
        tests_dir = root / "tests"
        if tests_dir.is_dir():
            py_files = list(tests_dir.glob("test_*.py")) + list(tests_dir.glob("*_test.py"))
            ts_files = list(tests_dir.glob("*.test.ts")) + list(tests_dir.glob("*.spec.ts"))
            if py_files:
                discovered.append({
                    "command": "python -m pytest tests/ -v --tb=short",
                    "source": "tests/ directory (test_*.py detected)",
                    "language": "python",
                })
            elif ts_files:
                discovered.append({
                    "command": "npx jest --verbose --forceExit",
                    "source": "tests/ directory (*.test.ts detected)",
                    "language": "typescript",
                })

    return discovered


_TEST_CONFIG_DETECTORS = [
    ("jest.config.js", "javascript", "npx jest --verbose --forceExit"),
    ("jest.config.ts", "typescript", "npx jest --verbose --forceExit"),
    ("jest.config.mjs", "javascript", "npx jest --verbose --forceExit"),
    ("vitest.config.ts", "typescript", "npx vitest run"),
    ("vitest.config.js", "javascript", "npx vitest run"),
    ("vitest.config.mjs", "javascript", "npx vitest run"),
    ("ava.config.js", "javascript", "npx ava"),
    ("mocha.opts", "javascript", "npx mocha --reporter spec"),
    (".mocharc.json", "javascript", "npx mocha --reporter spec"),
    ("cypress.config.ts", "typescript", "npx cypress run"),
    ("cypress.config.js", "javascript", "npx cypress run"),
    ("playwright.config.ts", "typescript", "npx playwright test"),
    ("playwright.config.js", "javascript", "npx playwright test"),
]


def _detect_js_flavor(root: Path, pkg: dict) -> str:
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if any(k in deps for k in ("typescript", "ts-jest", "vitest")):
        return "typescript"
    if (root / "tsconfig.json").is_file():
        return "typescript"
    return "javascript"


def _guess_make_lang(root: Path) -> str:
    if (root / "package.json").is_file():
        return "node"
    if (root / "pyproject.toml").is_file() or list(root.glob("*.py")):
        return "python"
    if (root / "Cargo.toml").is_file():
        return "rust"
    return "unknown"


def _install_deps_for_tests(workspace_path: str, language: str, task_id: str = None) -> dict:
    """测试前自动检查并安装缺失依赖。
    
    返回: {installed: bool, command: str, output: str}
    """
    root = Path(workspace_path)
    
    if language in ("python",):
        # 检查 pytest 是否可用
        try:
            subprocess.run(
                [sys.executable, "-m", "pytest", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return {"installed": False, "command": "", "output": "pytest 已安装"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            msg = "正在安装 pytest..."
            if task_id:
                stream_chunk(task_id, msg)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "pytest"],
                    capture_output=True, text=True, timeout=60, cwd=workspace_path,
                )
                return {
                    "installed": True,
                    "command": "pip install pytest",
                    "output": result.stdout[-500:] if result.stdout else result.stderr[:500],
                }
            except Exception as e:
                return {"installed": False, "command": "pip install pytest", "output": f"安装失败: {e}"}

    if language in ("javascript", "typescript", "node"):
        # 检查 node_modules 是否存在
        if (root / "node_modules").is_dir():
            return {"installed": False, "command": "", "output": "node_modules 已存在"}
        
        msg = "正在安装 npm 依赖..."
        if task_id:
            stream_chunk(task_id, msg)
        
        pm = "npm"
        if (root / "pnpm-lock.yaml").is_file():
            pm = "pnpm"
        elif (root / "yarn.lock").is_file():
            pm = "yarn"
        
        try:
            result = subprocess.run(
                [pm, "install", "--no-audit", "--no-fund"],
                capture_output=True, text=True, timeout=120, cwd=workspace_path,
            )
            return {
                "installed": True,
                "command": f"{pm} install",
                "output": result.stdout[-500:] if result.stdout else "",
            }
        except Exception as e:
            return {"installed": False, "command": f"{pm} install", "output": f"安装失败: {e}"}

    return {"installed": False, "command": "", "output": f"不支持的语言类型: {language}"}


# ================================================================
#  P1: run_test_step 入口
# ================================================================


def run_test_step(
    step, 
    context, 
    events, 
    task_id=None,
    llm_client=None,
    code_executor=None,  # 保留兼容旧签名，v3.3 中不再使用
):
    """
    执行 test 步骤（v3.3 / P1 增强）：
    
    [run_tests 意图] — 运行项目已有测试
    - 使用确定性发现的测试命令（不依赖 LLM）
    - 测试前自动检测安装缺失依赖
    - 返回结构化结果
    
    [write_code 意图] — 为生成的代码创建并运行测试
    - 从 write 步骤获取代码 → LLM 生成 pytest → 运行
    """

    meta = context.get("meta", {}) if context else {}
    intent = meta.get("intent", "")
    workspace_path = _get_workspace_path(context)

    # P1: run_tests 意图分支 — 运行项目已有测试
    if intent == "run_tests":
        if task_id:
            try:
                stream_start(task_id, "🧪 准备运行项目测试...")
            except Exception:
                pass

        run_test_step_for_intent(step, context, events, task_id, workspace_path)
        return

    # 以下是原有 write_code 意图的 test 流程（LLM 生成测试代码 + pytest）
    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🧪 正在生成测试用例...")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第1层防御：获取并验证 write 步骤的代码 =====
    try:
        write_outputs = [
            item.get("text", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "write" and item.get("text")
        ]

        if not write_outputs:
            error_msg = "test：未找到 write 步骤的代码，无法生成测试用例。"
            if task_id:
                stream_chunk(task_id, error_msg)
            step["output"] = {"text": error_msg}
            return

        write_text = write_outputs[-1]
        
    except Exception as e:
        error_msg = f"test：获取代码时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg)
        step["output"] = {"text": error_msg}
        return

    # ===== 第2层防御：提取用户代码 =====
    code = ""
    
    try:
        if isinstance(write_text, str):
            code = extract_code(write_text, fallback_strategies=True)
            if not code and write_text:
                if any(kw in write_text for kw in ['def ', 'class ', 'import ']):
                    code = write_text.strip()
        else:
            print(f"[WARN] write_text is not a string: {type(write_text)}")
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        code = ""

    if not code:
        error_msg = "test：write 步骤未提供可解析的代码块。"
        if task_id:
            stream_chunk(task_id, error_msg)
        step["output"] = {"text": error_msg}
        return

    # ===== 第3层防御：流式调用 LLM 生成测试代码 =====
    test_code_text = ""
    llm_success = False
    
    try:
        prompt = test_prompt(code)
        
        if llm_client is not None:
            if task_id and hasattr(llm_client, 'call_stream'):
                for chunk in llm_client.call_stream(prompt):
                    test_code_text += chunk
                    stream_chunk(task_id, chunk)
            else:
                test_code_text = llm_client.call(prompt)
        else:
            if task_id:
                for chunk in call_qwen_stream(prompt):
                    test_code_text += chunk
                    stream_chunk(task_id, chunk)
            else:
                test_code_text = call_llm(prompt)
        
        if not test_code_text:
            raise ValueError("LLM 返回空字符串")
        if not isinstance(test_code_text, str):
            test_code_text = str(test_code_text)
        
        llm_success = True
        
    except TimeoutError:
        error_msg = "# LLM 调用超时\n# 无法生成测试"
        if task_id:
            stream_chunk(task_id, error_msg)
        test_code_text = error_msg
    except Exception as e:
        error_msg = f"# LLM 调用失败: {str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg)
        test_code_text = error_msg

    # ===== 第4层防御：提取测试代码 =====
    test_code = ""
    
    try:
        if llm_success and test_code_text:
            test_code = extract_code(test_code_text, fallback_strategies=True)
            if not test_code and test_code_text:
                if any(kw in test_code_text for kw in ['def test_', 'assert ', 'pytest.raises']):
                    test_code = test_code_text.strip()
    except Exception as e:
        print(f"[ERROR] Test code extraction failed: {e}")
        test_code = ""

    if not test_code:
        error_msg = "test：未能从 LLM 输出中提取到有效的测试代码。"
        if task_id:
            stream_chunk(task_id, "\n\n" + error_msg)
        step["output"] = {
            "text": test_code_text if test_code_text else error_msg,
            "llm_success": llm_success
        }
        if task_id:
            stream_end(task_id)
        return

    # ===== 第5层：写入测试文件并运行真实 pytest =====
    test_result = {}
    exec_success = False
    workspace_path = _get_workspace_path(context)
    test_file_path = None

    try:
        if task_id:
            stream_chunk(task_id, "\n🔬 运行真实 pytest...\n")

        test_result = _run_pytest(workspace_path, code, test_code)
        test_file_path = test_result.get("test_path")
        exec_success = test_result.get("passed", False)

    except Exception as e:
        test_result = {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"Test execution error: {str(e)}",
            "duration_seconds": 0,
            "timed_out": False,
        }
        exec_success = False

    # ===== v3.4: 全量工作区验证门控 =====
    # LLM 生成的测试只覆盖隔离文件（test_ap_generated_XXXX.py），
    # 无法检测其他文件中的语法错误或导入错误（如 write_step 生成
    # 的 test_orders.py 末尾混入 Markdown，或 orders.py 中
    # Session = None 导致 FastAPI 崩溃）。
    # 此门控在 LLM 测试之后运行全量 pytest，确保所有文件都被收集，
    # 任何语法/导入错误都会触发 step_runner 的自愈修复循环。
    if workspace_path and test_result.get("passed", False):
        try:
            full_test = _run_full_workspace_pytest(workspace_path)
            if not full_test.get("passed", False):
                if task_id:
                    stream_chunk(
                        task_id,
                        "\n⚠️  全量工作区测试发现隐藏错误，将交由自愈引擎修复...\n",
                    )
                exec_success = False
                test_result = full_test
        except Exception as full_e:
            print(f"[WARN] Full workspace pytest error: {full_e}")

    # ===== 第6层防御：构建测试结果摘要 =====
    try:
        stdout = test_result.get("stdout", "")
        stderr = test_result.get("stderr", "")
        exit_code = test_result.get("exit_code")

        test_summary = (
            f"\n\n## 🧪 生成的测试代码\n"
            f"```python\n{test_code}\n```\n\n"
            f"## 📊 pytest 结果 (exit_code={exit_code})\n"
        )

        if test_result.get("timed_out"):
            test_summary += "\n⏱️  测试超时\n"
        elif exec_success:
            test_summary += "\n✅ 测试全部通过\n"
        else:
            test_summary += f"\n❌ 测试失败\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}\n"

        if task_id:
            stream_chunk(task_id, test_summary)

    except Exception as e:
        test_summary = f"测试结果格式化失败: {str(e)}"
        if task_id:
            stream_chunk(task_id, "\n\n" + test_summary)

    # ===== 第7层防御：写入输出 =====
    step["output"] = {
        "text": (test_code_text if test_code_text else "") + test_summary,
        "test_code": test_code,
        "test_path": test_file_path,
        "test_result": test_result,
        "llm_success": llm_success,
        "exec_success": exec_success,
    }

    if context is not None:
        context.setdefault("intermediate_results", []).append({
            "type": "test",
            "test_code": test_code,
            "test_path": test_file_path,
            "test_result": test_result,
            "exec_success": exec_success,
            "status": "passed" if exec_success else "failed",
        })

    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")


# ================================================================
#  P1: run_tests intent 执行器 — 项目已有测试
# ================================================================

def run_test_step_for_intent(
    step: dict,
    context: dict,
    events: list,
    task_id: str | None,
    workspace_path: str,
) -> None:
    """运行项目已有测试（intent=run_tests）：
    1. 确定性发现测试命令
    2. 安装缺失依赖
    3. 执行测试命令
    4. 结构化返回结果
    """
    meta = context.setdefault("meta", {})

    # Step 1: 发现测试命令
    discovered = discover_project_test_commands(workspace_path)
    
    if not discovered:
        if task_id:
            stream_chunk(
                task_id,
                "未发现可确认的测试命令。请检查项目是否包含测试配置文件或测试目录。",
            )
        step["output"] = {
            "text": "未发现可确认的测试命令。",
            "exec_success": None,
            "discovered_commands": [],
        }
        meta["test_discovery"] = {"found": False}
        if task_id:
            stream_end(task_id)
        return

    # 选第一个发现的测试命令
    selected = discovered[0]
    test_command = selected["command"]
    language = selected["language"]
    source = selected["source"]

    if task_id:
        stream_chunk(
            task_id,
            f"发现测试命令 (来源: {source}):\n"
            f"```bash\n{test_command}\n```\n"
        )

    # 将确定性发现的命令写入 context，供授权流使用
    if not meta.get("proposed_test_command"):
        meta["proposed_test_command"] = test_command
    meta["test_discovery"] = {
        "found": True,
        "command": test_command,
        "language": language,
        "source": source,
        "all_commands": [d["command"] for d in discovered],
    }

    # Step 2/3: 依赖处理 + 执行测试命令
    recovery = None
    if language == "python":
        # P0 运行期环境自愈：Probe → Diagnose → Authorize → Recover → Retry → Degrade → Evidence
        if task_id:
            stream_chunk(task_id, "🔬 执行测试命令（运行期环境自愈已启用）...\n")
        run_result = _run_python_test_with_recovery(workspace_path, context, test_command)
        test_result = run_result["test_result"]
        passed = run_result["exec_success"]
        dep_result = run_result["dep_install"]
        recovery = run_result["recovery"]
    else:
        if task_id:
            stream_chunk(task_id, f"检查 {language} 环境依赖...\n")
        dep_result = _install_deps_for_tests(workspace_path, language, task_id)
        if dep_result.get("installed"):
            if task_id:
                stream_chunk(
                    task_id,
                    f"✅ 依赖已安装: `{dep_result['command']}`\n",
                )
        if task_id:
            stream_chunk(task_id, "🔬 执行测试命令...\n")
        test_result = _run_project_test_command(workspace_path, test_command)
        passed = test_result.get("passed", False)

    # 自愈反馈：安装动作与恢复结果流式反馈
    if recovery:
        if recovery.get("install_actions"):
            if task_id:
                stream_chunk(
                    task_id,
                    f"🔧 环境自愈已执行安装: `{recovery.get('recovery_command') or ''}`\n",
                )
        if recovery.get("status") == "recovered":
            if task_id:
                stream_chunk(task_id, "✅ 环境自愈后测试恢复通过\n")

    # Step 4: 构建结果
    duration = test_result.get("duration_seconds", 0)

    summary = (
        f"\n## 📊 测试结果\n"
        f"命令: `{test_command}`\n"
        f"耗时: {duration:.1f}s\n"
    )
    if passed:
        summary += "✅ 测试全部通过\n"
    elif test_result.get("timed_out"):
        summary += "⏱️ 测试超时\n"
    elif test_result.get("verification_status") == "not_verified":
        summary += "⚠️ 无法验证测试结果（不判定为通过）\n"
    else:
        summary += f"❌ 测试失败 (exit_code={test_result.get('exit_code')})\n"

    if task_id:
        stream_chunk(task_id, summary)
        if test_result.get("stdout"):
            stream_chunk(
                task_id,
                f"\n<details><summary>标准输出</summary>\n\n```\n{test_result['stdout'][:2000]}\n```\n</details>\n"
            )
        if test_result.get("stderr"):
            stream_chunk(
                task_id,
                f"\n<details><summary>错误输出</summary>\n\n```\n{test_result['stderr'][:2000]}\n```\n</details>\n"
            )

    step["output"] = {
        "text": summary,
        "test_command": test_command,
        "test_result": test_result,
        "exec_success": passed,
        "discovered_from": source,
        "language": language,
        "dep_install": dep_result,
    }
    if recovery:
        step["output"]["runtime_recovery"] = recovery

    intermediate_entry = {
        "type": "test",
        "test_command": test_command,
        "test_result": test_result,
        "exec_success": passed,
        "status": "passed" if passed else "failed",
        "language": language,
    }
    if recovery:
        intermediate_entry["runtime_recovery"] = recovery
    context.setdefault("intermediate_results", []).append(intermediate_entry)

    if task_id:
        try:
            stream_end(task_id)
        except Exception:
            pass


def _run_python_test_with_recovery(workspace_path: str, context: dict, test_command: str) -> dict:
    """P0：Python 测试命令运行期环境自愈（7 步闭环）。

    先直接运行测试命令（Probe），失败时调用 recover_test_environment 执行
    Probe→Diagnose→Authorize→Recover→Retry→Degrade→Evidence，并按降级决策表
    映射回 test/fix 状态契约：

    - verification=passed                  → exec_success=True（自愈后验证通过）
    - verification=failed + 断言失败        → exec_success=False + exit_code≠0（进 fix 流程）
    - 其余（无法验证/被拒绝/环境未修复）      → exec_success=False + exit_code=None（验证失败）

    硬性不变式：绝不把「无法验证」判定为「验证通过」。

    返回: {test_result, exec_success, dep_install, recovery}
    """
    from ....runtime_environment_recovery import recover_test_environment

    meta = context.setdefault("meta", {})
    meta["authorized_test_command"] = test_command

    dep_install = {"installed": False, "command": "", "output": ""}

    # Probe：直接运行测试命令
    test_result = _run_project_test_command(workspace_path, test_command)
    if test_result.get("passed"):
        return {
            "test_result": test_result,
            "exec_success": True,
            "dep_install": dep_install,
            "recovery": None,
        }

    # 失败 → 运行期环境自愈
    recovery = recover_test_environment(workspace_path, context)
    verification = recovery.get("verification_status")
    failure_class = recovery.get("failure_class")
    final = recovery.get("final_test_result") or {}

    dep_install = _recovery_to_dep_install(recovery)

    if verification == "passed":
        # 自愈后验证通过
        test_result = {
            "passed": True,
            "exit_code": 0,
            "stdout": final.get("stdout", ""),
            "stderr": final.get("stderr", ""),
            "duration_seconds": test_result.get("duration_seconds", 0),
            "timed_out": False,
            "recovered": True,
        }
        return {
            "test_result": test_result,
            "exec_success": True,
            "dep_install": dep_install,
            "recovery": recovery,
        }

    if verification == "failed" and failure_class == "TEST_ASSERTION_FAILURE":
        # 真实断言失败 → 进 fix 流程；优先用最终测试输出（自愈后可能重新分类）
        if final.get("stderr") or final.get("exit_code") is not None:
            test_result = {
                "passed": False,
                "exit_code": final.get("exit_code", 1),
                "stdout": final.get("stdout", ""),
                "stderr": final.get("stderr", ""),
                "duration_seconds": test_result.get("duration_seconds", 0),
                "timed_out": False,
                "recovered": False,
            }
        return {
            "test_result": test_result,
            "exec_success": False,
            "dep_install": dep_install,
            "recovery": recovery,
        }

    # 其余（无法验证 / 授权拒绝 / 环境未修复）→ 无明确可执行测试失败证据
    test_result = {
        "passed": False,
        "exit_code": None,
        "stdout": test_result.get("stdout", ""),
        "stderr": test_result.get("stderr", ""),
        "duration_seconds": test_result.get("duration_seconds", 0),
        "timed_out": False,
        "verification_status": verification,
        "failure_class": failure_class,
    }
    return {
        "test_result": test_result,
        "exec_success": False,
        "dep_install": dep_install,
        "recovery": recovery,
    }


def _recovery_to_dep_install(recovery: dict | None) -> dict:
    """将 RecoveryResult 映射回现有 dep_install 契约（installed/command/output）。"""
    if not recovery:
        return {"installed": False, "command": "", "output": ""}
    actions = recovery.get("install_actions") or []
    return {
        "installed": len(actions) > 0,
        "command": recovery.get("recovery_command") or "",
        "output": "; ".join(a.get("outcome", "") for a in actions if isinstance(a, dict)),
    }


def _run_project_test_command(workspace_path: str, command: str) -> dict:
    """执行项目原有的测试命令，返回结构化结果。"""
    start = time.monotonic()

    try:
        result = subprocess.run(
            command,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=_PYTEST_TIMEOUT,
            check=False,
            shell=True,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_seconds": _PYTEST_TIMEOUT,
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"命令未找到: {command.split()[0]}",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
        }


# ================================================================
#  内部工具函数
# ================================================================

def _get_workspace_path(context):
    meta = context.get("meta", {}) if context else {}
    return meta.get("workspace_path") or meta.get("workspace_dir") or os.getcwd()


def _run_pytest(workspace_path, code, test_code):
    """
    写入临时测试文件并用 subprocess 运行 pytest。
    
    返回:
        {
            "passed": bool,
            "exit_code": int | None,
            "stdout": str,
            "stderr": str,
            "duration_seconds": float,
            "timed_out": bool,
            "test_path": str,
        }
    """
    test_dir = Path(workspace_path) / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)

    test_id = uuid.uuid4().hex[:8]
    test_path = test_dir / f"test_ap_generated_{test_id}.py"

    combined = code + "\n\n" + test_code
    test_path.write_text(combined, encoding="utf-8")

    command = [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=short"]

    start = time.monotonic()

    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=_PYTEST_TIMEOUT,
            check=False,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
            "test_path": str(test_path),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_seconds": _PYTEST_TIMEOUT,
            "timed_out": True,
            "test_path": str(test_path),
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "pytest is not installed in the current Python environment.",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
            "test_path": str(test_path),
        }


# ================================================================
#  v3.4: 全量工作区 pytest — 自愈闭环的完整性修复
# ================================================================

_FULL_WORKSPACE_PYTEST_TIMEOUT = 180


def _run_full_workspace_pytest(workspace_path: str) -> dict:
    """运行全量工作区 pytest，检测隔离测试无法捕获的错误。

    与 _run_pytest 不同，此函数运行 pytest 在整个工作区上（而非单个
    LLM 生成的测试文件）。这确保：
    - 所有文件的语法错误被检测（Markdown 混入 .py、全角冒号等）
    - 导入错误被检测（FastAPI Session = None → 类型解析崩溃等）
    - 跨文件集成问题被检测

    返回结构与 _run_pytest 一致，供 step_runner 的自愈循环使用。
    """
    start = time.monotonic()
    command = [sys.executable, "-m", "pytest", workspace_path, "-q", "--tb=long"]

    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=_FULL_WORKSPACE_PYTEST_TIMEOUT,
            check=False,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
            "test_path": workspace_path,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": (exc.stdout or "")[:5000],
            "stderr": (exc.stderr or "")[:5000],
            "duration_seconds": _FULL_WORKSPACE_PYTEST_TIMEOUT,
            "timed_out": True,
            "test_path": workspace_path,
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "pytest is not installed in the current Python environment.",
            "duration_seconds": time.monotonic() - start,
            "timed_out": False,
            "test_path": workspace_path,
        }