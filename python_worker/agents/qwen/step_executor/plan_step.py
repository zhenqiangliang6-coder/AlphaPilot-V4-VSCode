# -*- coding: utf-8 -*-
# step_executor/plan_step.py
# ---------------------------------------------------------
# plan 步骤：生成代码结构规划（工业级容错 + 流式输出 + 人格配置版本）
# ---------------------------------------------------------

from ..qwen_api import call_qwen, call_qwen_stream, call_qwen_with_persona
from .prompts import plan_prompt, mentor_plan_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
import re


def run_plan_step(step, context, events, task_id=None):
    """
    plan 步骤（工业级容错 + 流式输出 + 人格配置）：
    - 输入：analyze 步骤的分析结果
    - 输出：代码结构规划（自然语言 + 伪代码）
    
    ⭐ v2.6 新增：人格配置支持
    - 从 context.meta 读取 persona 类型
    - 动态注入 System Prompt
    
    ⭐ 流式输出支持
    - 通过 task_id 发送 stream_chunk 事件
    - 实时展示 AI 思考过程 (channel=reasoning)
    
    容错策略:
    1. 验证 analyze 输出存在且有效
    2. LLM 流式调用保护
    3. 输出保证
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "📋 正在制定计划...", phase="plan")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ v2.6 新增 - 获取人格配置 =====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")  # 默认工程师人格
        
        # 导入人格配置模块
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 plan_step 使用人格: {persona_config['name']} ({persona_config['icon']})")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}, 使用默认配置")
        persona_config = None

    # ===== 第1层防御：获取并验证 analyze 输出 =====
    try:
        analyze_outputs = [
            item.get("analysis", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze" and item.get("analysis")
        ]

        if not analyze_outputs:
            error_msg = "plan：未找到 analyze 步骤的分析结果。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
            step["output"] = {"text": error_msg}
            return

        analysis = analyze_outputs[-1]
        
        if not isinstance(analysis, str) or not analysis.strip():
            error_msg = "plan：analyze 步骤的分析结果无效。"
            if task_id:
                stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
            step["output"] = {"text": error_msg}
            return
            
    except Exception as e:
        error_msg = f"plan：获取分析结果时发生错误：{str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        step["output"] = {"text": error_msg}
        return

    # ===== 第2层防御：流式调用 LLM 生成规划（带人格配置）=====
    result = ""
    llm_success = False
    
    try:
        if context.get("meta", {}).get("intent") == "mentor_explain":
            prompt = mentor_plan_prompt(analysis)
        else:
            prompt = plan_prompt(analysis)
        
        # ⭐ v2.6 关键改动：使用带人格配置的流式调用
        if task_id:
            # ⭐ 使用带人格配置的流式调用
            if persona_config:
                print(f"🚀 使用人格配置进行流式调用: {persona_config['name']}")
                for chunk in call_qwen_with_persona(prompt, persona_config, use_stream=True):
                    result += chunk
                    # 实时发送到前端 (channel=reasoning)
                    stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
            else:
                # 降级到普通流式调用
                for chunk in call_qwen_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="plan", channel="reasoning")
        else:
            # 非流式模式（向后兼容）
            if persona_config:
                result = call_qwen_with_persona(prompt, persona_config, use_stream=False)
            else:
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
        error_msg = f"# LLM 调用超时\n无法生成规划"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        result = error_msg
    except Exception as e:
        error_msg = f"# LLM 调用失败: {str(e)}"
        if task_id:
            stream_chunk(task_id, error_msg, phase="plan", channel="reasoning")
        result = error_msg

    # ===== 第3层防御：写入输出 =====
    step["output"] = {"text": result or "规划生成失败"}
    command_match = re.search(
        r"(?im)^\s*TEST_COMMAND:\s*(.+?)\s*$",
        result or "",
    )
    if command_match and context.get("meta", {}).get("intent") not in {
        "architecture",
        "code_review",
        "mentor_explain",
        "chat",
        "explain_code",
        "delete_files",
    }:
        context.setdefault("meta", {})["proposed_test_command"] = command_match.group(1).strip().strip("`")

    # ===== 第4层防御：写入上下文 =====
    try:
        context["intermediate_results"].append({
            "type": "plan",
            "plan": result or "",
            "llm_success": llm_success
        })
    except Exception as e:
        print(f"[ERROR] Failed to update context: {e}")

    # ===== 第5层防御：写入事件流 =====
    try:
        events.append(create_event("plan_output", {
            "plan": result or "",
            "llm_success": llm_success
        }))
    except Exception as e:
        print(f"[ERROR] Failed to append event: {e}")
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)  # ⭐ v2.7 修复：移除 phase 参数
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
