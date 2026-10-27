"""Provider-neutral final response step for read-only and mentor requests."""

from .worker_config import create_event, stream_chunk, stream_end, stream_start, extract_and_emit_artifacts


def run_respond_step(step, context, events, task_id=None):
    meta = context.get("meta", {})
    request = meta.get("user_request", "")
    plans = [
        item.get("plan", "")
        for item in context.get("intermediate_results", [])
        if item.get("type") == "plan" and item.get("plan")
    ]
    if not request or not plans:
        step["output"] = {"text": "无法生成说明：缺少用户请求或计划结果。"}
        return

    # 检测是否为结构/架构类请求，动态注入 Mermaid 指令
    structure_indicators = [
        "结构图", "架构图", "流程图", "依赖图", "模块图", "关系图",
        "架构", "结构", "流程", "依赖关系", "模块划分",
        "architecture", "structure", "diagram", "flow", "mermaid",
    ]
    needs_diagram = any(ind in request.lower() for ind in structure_indicators)

    mermaid_instruction = ""
    if needs_diagram:
        mermaid_instruction = (
            "\n【重要：必须使用 Mermaid 图表】\n"
            "如果涉及架构/结构/流程，必须输出 Mermaid 代码块（```mermaid...```）呈现图表。"
            "Mermaid 是唯一批准的图表格式，禁止使用 ASCII 字符画。\n"
            "示例格式：\n"
            "```mermaid\n"
            "graph TD\n"
            "    A[模块A] --> B[模块B]\n"
            "    B --> C[模块C]\n"
            "```\n"
        )

    prompt = (
        "请将以下计划整理成面向用户的最终答复。保持项目事实准确，不要声称执行过任何操作，"
        "不要生成可执行的应用程序代码或写入文件系统。"
        f"{mermaid_instruction}\n\n用户请求：\n"
        f"{request}\n\n计划：\n{plans[-1]}"
    )
    provider_call = context.get("_respond_call")
    if not callable(provider_call):
        raise RuntimeError("当前 Worker 未配置最终响应模型适配器")

    result = ""
    if task_id:
        stream_start(task_id, "正在整理最终说明...", phase="respond")
        # P1：注入思考摘要到 reasoning 通道 → 前端显示 "💭 AI 思考过程"
        workspace_summary = meta.get("workspace_summary", "")
        intent_str = meta.get("intent", "unknown")
        persona_str = meta.get("persona", "default")
        reasoning_summary = (
            f"已完成前序步骤：\n"
            f"1. 意图识别 → {intent_str}（{persona_str} 人格）\n"
            f"2. 项目扫描 → {workspace_summary or '完成'}\n"
            f"3. 执行计划 → 共 {len(plans)} 个方案\n\n"
            f"正在基于以上分析生成最终答复..."
        )
        stream_chunk(task_id, reasoning_summary, phase="respond", channel="reasoning")
    try:
        output = provider_call(prompt, meta.get("persona_config"), task_id)
        if isinstance(output, str):
            result = output
        else:
            for chunk in output:
                result += chunk
                if task_id:
                    stream_chunk(task_id, chunk, phase="respond", channel="content")
        if not result:
            raise ValueError("模型返回空说明")
    finally:
        if task_id:
            # P1：在 stream_end 之前提取并发射产物事件
            # emit_artifact 是 awaitable HTTP 调用，必须在 stream_end 之前完成
            # 产物发送失败不阻塞响应流程，仅记录告警
            try:
                count = extract_and_emit_artifacts(result, task_id)
                if count > 0:
                    print(f"[P1] respond_step 提取到 {count} 个产物")
            except Exception as e:
                print(f"[P1] respond_step 产物提取失败: {e}")
            stream_end(task_id)

    step["output"] = {"text": result}
    context.setdefault("intermediate_results", []).append(
        {"type": "respond", "text": result}
    )
    events.append(create_event("respond_output", {"text": result}))