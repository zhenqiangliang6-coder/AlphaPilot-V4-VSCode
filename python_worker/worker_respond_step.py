"""Provider-neutral final response step for read-only and mentor requests."""

from .worker_config import create_event, stream_chunk, stream_end, stream_start


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

    prompt = (
        "请将以下计划整理成面向用户的最终答复。保持项目事实准确，不要声称执行过任何操作，"
        "不要生成文件或代码。\n\n用户请求：\n"
        f"{request}\n\n计划：\n{plans[-1]}"
    )
    provider_call = context.get("_respond_call")
    if not callable(provider_call):
        raise RuntimeError("当前 Worker 未配置最终响应模型适配器")

    result = ""
    if task_id:
        stream_start(task_id, "正在整理最终说明...", phase="respond")
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
            stream_end(task_id)

    step["output"] = {"text": result}
    context.setdefault("intermediate_results", []).append(
        {"type": "respond", "text": result}
    )
    events.append(create_event("respond_output", {"text": result}))
