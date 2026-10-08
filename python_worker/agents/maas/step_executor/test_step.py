# step_executor/test_step.py
# ---------------------------------------------------------
# 自动生成并运行 pytest 风格单元测试（工业级容错 + 流式输出版本）
# ---------------------------------------------------------

from .utils import extract_code, FAKE_PYTEST
from .prompts import test_prompt
from ....code_executor import run_python
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ..maas_api import call_maas_stream, call_maas


def run_test_step(step, context, events, task_id=None):
    """
    执行 test 步骤（工业级容错 + 流式输出）：
    - 从 write 步骤获取代码
    - 流式生成 pytest 风格测试代码
    - 注入 fake pytest
    - 组合执行
    
    容错策略:
    1. 验证 write 输出存在且有效
    2. LLM 流式调用保护
    3. 代码提取保护（多策略）
    4. 测试执行保护
    5. 输出保证
    
    ⭐ 新增：流式输出支持
    - 通过 task_id 发送 stream_chunk 事件
    - 实时展示 AI 思考过程
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
            
            # 降级策略
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
        
        # ⭐ 关键改动：使用流式调用而非阻塞调用
        if task_id:
            # 流式模式：逐块接收并转发
            for chunk in call_maas_stream(prompt):
                test_code_text += chunk
                # 实时发送到前端
                stream_chunk(task_id, chunk)
        else:
            # 非流式模式（向后兼容）
            test_code_text = call_maas(prompt)
        
        # 验证返回值
        if not test_code_text:
            raise ValueError("LLM 返回空字符串")
        
        if not isinstance(test_code_text, str):
            try:
                test_code_text = str(test_code_text)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(test_code_text)}")
        
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
            
            # 降级策略
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

    # ===== 第5层防御：执行测试代码 =====
    test_result = {}
    exec_success = False
    
    try:
        full_code = FAKE_PYTEST + "\n\n" + code + "\n\n" + test_code
        test_result = run_python(full_code)
        
        # 检查执行结果
        if isinstance(test_result, dict):
            error = test_result.get('error', 'None')
            exception = test_result.get('exception', None)
            exec_success = (error == 'None' or error is None) and not exception
            
    except Exception as e:
        test_result = {"error": f"Test execution failed: {str(e)}"}
        exec_success = False

    # ===== 第6层防御：构建测试结果摘要 =====
    try:
        stdout = test_result.get('stdout', '') if isinstance(test_result, dict) else ''
        stderr = test_result.get('stderr', '') if isinstance(test_result, dict) else ''
        exception = test_result.get('exception', None) if isinstance(test_result, dict) else None
        
        test_summary = (
            f"\n\n## 🧪 生成的测试代码\n"
            f"```python\n{test_code}\n```\n\n"
            f"## 📊 测试结果\n"
            f"stdout:\n{stdout}\n\n"
            f"stderr:\n{stderr}\n\n"
        )
        
        if exception:
            test_summary += f"❌ 测试失败:\n{exception}\n"
        elif exec_success:
            test_summary += "✅ 测试通过\n"
        else:
            test_summary += "⚠️ 测试执行异常\n"
            
        # ⭐ 流式发送测试结果摘要
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
        "test_result": test_result,
        "llm_success": llm_success,
        "exec_success": exec_success
    }
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
