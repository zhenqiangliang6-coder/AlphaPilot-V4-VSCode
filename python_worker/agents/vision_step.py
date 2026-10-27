# -*- coding: utf-8 -*-
# agents/vision_step.py
# ---------------------------------------------------------
# vision_analysis — 一等公民执行步骤（宪法合规版）
# - 与 analyze/plan/write 平级，通过 STEP_DISPATCHER 路由
# - 负责：读图 → 标准化 → 调用多模态 API → 写入 context
# - 输出注入到下游 step，TaskModel_v2 全程可追溯
# ---------------------------------------------------------

import os
import time
from typing import List, Dict

from .vision_api import call_vision, read_images_from_workspace
from ..worker_config import stream_start, stream_chunk


def run_vision_step(
    step: dict,
    context: dict,
    events: list,
    task_id: str = None,
):
    """
    vision_analysis 步骤（一等公民 step，宪法合规）

    流程:
    1. 从 step.input 提取 prompt + images 引用
    2. 从 workspace 读取标准化后的图片文件
    3. 调用 call_vision 统一多模态 API
    4. 将分析结果写入 context["_vision_result"]
    5. TaskModel_v2 通过 step_start/step_finished 全程记录
    """

    prompt = step.get("input", {}).get("prompt", "")
    image_refs = step.get("input", {}).get("images", [])
    workspace_path = context.get("workspace_path") or context.get("meta", {}).get("workspace_path") or os.getcwd()

    if not image_refs:
        step["output"] = {"text": "vision_analysis: 无图片引用，跳过"}
        events.append({
            "event": "vision_skipped",
            "task_id": task_id,
            "reason": "no_images"
        })
        return

    if task_id:
        try:
            stream_start(task_id, f"📷 正在分析 {len(image_refs)} 张图片...", phase="vision")
        except Exception:
            pass

    t0 = time.time()

    try:
        images = read_images_from_workspace(image_refs, workspace_path)
    except Exception as e:
        step["output"] = {"text": f"vision_analysis: 图片读取失败: {e}"}
        if task_id:
            stream_chunk(task_id, f"图片读取失败: {e}\n", phase="vision")
        raise

    if not images:
        step["output"] = {"text": "vision_analysis: 图片加载为空"}
        if task_id:
            stream_chunk(task_id, "图片加载为空，跳过视觉分析。\n", phase="vision")
        return

    prompt = prompt or "请详细分析这张图片的内容"
    model_type = step.get("input", {}).get("model_type", "qwen")

    try:
        vision_result = call_vision(prompt, images, model_type)
    except Exception as e:
        step["output"] = {"text": f"vision_analysis: 多模态 API 调用失败: {e}"}
        if task_id:
            stream_chunk(task_id, f"视觉分析失败: {e}\n", phase="vision")
        raise

    elapsed_ms = int((time.time() - t0) * 1000)

    step["output"] = {
        "text": vision_result,
        "image_count": len(images),
        "elapsed_ms": elapsed_ms
    }

    context["_vision_result"] = vision_result

    if task_id:
        stream_chunk(task_id, f"图片分析完成（{elapsed_ms}ms）。\n", phase="vision", channel="reasoning")