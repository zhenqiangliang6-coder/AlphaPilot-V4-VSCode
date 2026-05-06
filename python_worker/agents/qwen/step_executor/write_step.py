# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（工业级容错 + 流式输出版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen, call_qwen_stream
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（工业级容错 + 流式输出）：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码 / 诗歌 / 文档等
    
    ⭐ 新增：流式输出支持
    - 通过 task_id 发送 stream_chunk 事件
    - 实时展示 AI 思考过程 (channel=reasoning)
    - 实时展示最终产出 (channel=content)
    
    容错策略:
    1. 验证 plan 输出存在且有效
    2. LLM 流式调用保护
    3. 代码提取保护（多策略降级）
    4. 输出保证（即使失败也返回有意义结果）
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成内容...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第1层防御：获取并验证 plan 输出 =====
    try:
        plan_outputs = [
            item.get("plan", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "plan" and item.get("plan")
        ]

        if not plan_outputs:
            error_msg = "write：未找到 plan 步骤的规划内容。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="write", channel="reasoning")
            step["output"] = {
                "text": error_msg,
                "code": ""
            }
            return

        plan_text = plan_outputs[-1]
        
        # 验证规划文本有效性
        if not isinstance(plan_text, str) or not plan_text.strip():
            error_msg = "write：plan 步骤的规划内容无效。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="write", channel="reasoning")
            step["output"] = {
                "text": error_msg,
                "code": ""
            }
            return
            
    except Exception as e:
        error_msg = f"write：获取规划时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="write", channel="reasoning")
        step["output"] = {
            "text": error_msg,
            "code": ""
        }
        return

    # ===== 第2层防御：流式调用 LLM 生成内容 =====
    result = ""
    llm_success = False
    
    try:
        prompt = write_prompt(plan_text)
        
        # ⭐ 关键改动：使用流式调用而非阻塞调用
        if task_id:
            # 先发送思考过程
            reasoning = "让我开始生成内容...\n"
            stream_chunk(task_id, reasoning, phase="write", channel="reasoning")
            
            # 流式模式：逐块接收并转发
            for chunk in call_qwen_stream(prompt):
                result += chunk
                # 实时发送到前端 (channel=content)
                stream_chunk(task_id, chunk, phase="write", channel="content")
        else:
            # 非流式模式（向后兼容）
            result = call_qwen(prompt)
        
        # 验证返回值
        if not result:
            raise ValueError("LLM 返回空字符串")
        
        if not isinstance(result, str):
            try:
                result = str(result)
            except:
                raise TypeError(f"LLM 返回非字符串类型: {type(result)}")
        
        llm_success = True
        
    except TimeoutError:
        error_msg = "# LLM 调用超时\n# 无法生成内容"
        if task_id:
            stream_chunk(task_id, error_msg, phase="write", channel="reasoning")
        result = error_msg
    except Exception as e:
        error_msg = f"# LLM 调用失败: {str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="write", channel="reasoning")
        result = error_msg

    # ===== 第3层防御：提取代码块（多策略）=====
    code = ""
    
    try:
        if llm_success and result:
            code = extract_code(result, fallback_strategies=True)
            
            # 如果提取失败，但文本看起来像代码
            if not code and result:
                if any(kw in result for kw in ['def ', 'class ', 'import ']):
                    code = result.strip()
                    print("[INFO] Using full text as code (extraction failed)")
                    
    except Exception as e:
        print(f"[ERROR] Code extraction failed: {e}")
        code = ""

    # 最终保障
    if not code and result:
        code = "# 内容提取失败"

    # ===== 第4层防御：写入输出 =====
    step["output"] = {
        "text": result or "生成失败",
        "code": code,
        "llm_success": llm_success
    }

    # ===== 第5层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "write",
            "text": result or "",
            "code": code,
            "llm_success": llm_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第6层防御：写入事件流 =====
    try:
        events.append(create_event("write_output", {
            "text": result or "",
            "code": code,
            "llm_success": llm_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id, phase="write")
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
