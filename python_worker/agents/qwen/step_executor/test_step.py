# step_executor/test_step.py
# ---------------------------------------------------------
# v3.3 真实 pytest 执行
# - 移除 FAKE_PYTEST，接入真实 pytest 子进程
# - 结构化测试结果：passed / exit_code / stdout / stderr / timed_out
# - 处理 pytest 未安装、收集失败、超时等异常路径
# ---------------------------------------------------------

import os
import sys
import time
import subprocess
import uuid
from pathlib import Path

from .utils import extract_code
from .prompts import test_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ..qwen_api import call_qwen_stream, call_qwen


_PYTEST_TIMEOUT = 120


def run_test_step(
    step, 
    context, 
    events, 
    task_id=None,
    llm_client=None,
    code_executor=None,  # 保留兼容旧签名，v3.3 中不再使用
):
    """
    执行 test 步骤（v3.3 真实 pytest）：
    - 从 write 步骤获取代码
    - 流式生成 pytest 风格测试代码
    - 写入临时测试文件
    - 通过 subprocess 运行真实 pytest
    - 结构化输出：{passed, exit_code, stdout, stderr, timed_out}
    """

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
                test_code_text = call_qwen(prompt)
        
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
#  真实 pytest 执行器
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