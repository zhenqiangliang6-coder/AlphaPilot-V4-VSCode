"""Produce a user-facing explanation without creating FileOps."""

from ..qwen_api import call_qwen_with_persona, call_llm_with_persona
from ....worker_config import create_event, stream_chunk, stream_end, stream_start, extract_and_emit_artifacts


def _close_unclosed_blocks(text: str) -> str:
    """补全流式输出中可能未闭合的 Markdown/Mermaid 代码块"""
    result = text
    # 补全未闭合的 ```mermaid 块
    mermaid_open = result.count("```mermaid")
    mermaid_close = result.count("```")
    # 减去 mermaid 开始的 ``` 后得到真正的闭合数
    if mermaid_open > 0:
        total_opens = result.count("```") - mermaid_open
        total_closes = result.count("```") - mermaid_open
        if total_opens > total_closes:
            result += "\n```"
    # 通用：奇数个 ``` 表示有未闭合的代码块
    backtick_groups = result.count("```")
    if backtick_groups % 2 != 0:
        result += "\n```"
    return result


def run_respond_step(step, context, events, task_id=None):
    meta = context.get("meta", {})
    request = meta.get("user_request", "")
    intent = meta.get("intent", "")

    plans = [
        item.get("plan", "")
        for item in context.get("intermediate_results", [])
        if item.get("type") == "plan" and item.get("plan")
    ]

    # 如果 plan 步骤未产生结果，尝试回退使用 analyze 结果
    if not plans:
        analyze_items = [
            item.get("analysis", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze" and item.get("analysis")
        ]
        if analyze_items:
            plans = [analyze_items[-1]]

    if not request:
        step["output"] = {"text": "无法生成说明：缺少用户请求。"}
        return

    if not plans:
        step["output"] = {"text": "无法生成说明：缺少分析/计划结果。请重试或提供更多上下文。"}
        return

    # 构建增强的 respond prompt，要求输出 Mermaid 结构图
    base_prompt = (
        "请将以下计划整理成面向用户的最终答复。保持项目事实准确，不要声称执行过任何操作，"
        "不要生成文件或代码。"
    )
    if intent == "mentor_explain":
        base_prompt += (
            "\n\n输出格式要求：\n"
            "1. 使用清晰的标题分层（## 一级标题, ### 二级标题）\n"
            "2. 对于项目架构、执行流程、数据流转等复杂关系，使用 ```mermaid 代码块生成可视化图表\n"
            "   - 优先使用 flowchart TD（自上而下）或 flowchart LR（自左而右）\n"
            "   - 节点标签使用双引号包裹，如 A[\"标签名\"]\n"
            "   - 避免在节点标签中使用方括号 []，改用圆括号 ()或直接文字\n"
            "3. 对于对比信息，使用 Markdown 表格\n"
            "4. 使用步骤编号（1. 2. 3.）表示序列化操作"
        )

    prompt = f"{base_prompt}\n\n用户请求：\n{request}\n\n计划：\n{plans[-1]}"
    persona_config = meta.get("persona_config")
    result = ""

    try:
        if task_id:
            stream_start(task_id, "正在整理项目说明...", phase="respond")
            for chunk in call_llm_with_persona(prompt, persona_config, use_stream=True):
                result += chunk
                stream_chunk(task_id, chunk, phase="respond", channel="content")
        else:
            result = call_llm_with_persona(prompt, persona_config, use_stream=False)
        if not result:
            raise ValueError("Qwen 返回空说明")

        # 补全可能因截断而缺失的闭合标签
        result = _close_unclosed_blocks(result)

    except Exception as error:
        result = f"说明生成失败：{error}"
    finally:
        if task_id:
            # P2：在 stream_end 之前提取并发射 Mermaid 产物
            # 与 worker_respond_step.py 保持一致：产物发送失败不阻塞响应流程
            try:
                count = extract_and_emit_artifacts(result, task_id)
                if count > 0:
                    print(f"[P2] respond_step 提取到 {count} 个 Mermaid 产物, task={task_id}")
            except Exception as e:
                print(f"[P2] respond_step 产物提取失败: {e}")
            stream_end(task_id)

    step["output"] = {"text": result}
    context.setdefault("intermediate_results", []).append({"type": "respond", "text": result})
    events.append(create_event("respond_output", {"text": result}))