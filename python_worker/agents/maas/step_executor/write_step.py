# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（v3.0 多文件协议版本）
# ---------------------------------------------------------

import re
from ..maas_api import call_maas, call_maas_stream
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3, create_file_op


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（v3.0）：
    - 支持多文件协议 (# FILE: / # TEST: / # DOC: / # META: / # DEPENDS:)
    - 自动生成 file_ops
    - 自动写入 context
    - 支持 persona / intent
    - 支持流式输出
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成代码...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 1. 获取 persona / intent =====
    persona_config = None
    intent = "write_code"

    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        intent = meta.get("intent", "write_code")

        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)

        print(f"🎨 write_step 使用人格: {persona_config['name']}")
        print(f"🧠 意图: {intent}")

    except Exception as e:
        print(f"[WARN] 获取人格失败: {e}")
        persona_config = None

    # ===== 2. 获取 plan 输出 =====
    plan_outputs = [
        item.get("plan", "")
        for item in context.get("intermediate_results", [])
        if item.get("type") == "plan"
    ]

    if not plan_outputs:
        msg = "write：未找到 plan 步骤的规划内容。"
        step["output"] = {"text": msg, "code": ""}
        return

    plan_text = plan_outputs[-1]

    # ===== 3. 调用 LLM（支持流式输出）=====
    result = ""
    llm_success = False

    try:
        prompt = write_prompt(plan_text)

        if task_id:
            stream_chunk(task_id, "开始生成代码...\n", phase="write", channel="reasoning")

            if persona_config:
                for chunk in call_maas_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="write", channel="content")
            else:
                for chunk in call_maas_stream(prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="write", channel="content")
        else:
            if persona_config:
                result = call_maas(prompt)
            else:
                result = call_maas(prompt)

        if not result:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        result = err
        if task_id:
            stream_chunk(task_id, err, phase="write", channel="reasoning")

    # ===== 4. 提取代码（单文件降级用）=====
    code = extract_code(result, fallback_strategies=True)

    # ===== 5. 解析多文件协议（核心）=====
    try:
        file_ops = parse_fileops_v3(result)

        if not file_ops:
            print("[WARN] 未检测到多文件协议，降级为单文件模式")

            file_op = create_file_op(
                action="create",
                path="main.py",
                content=code,
                file_type="file",
                language="python",
                reason="单文件降级模式",
                from_step="write",
                intent=intent
            )
            file_ops = [file_op]

        print(f"✅ write_step 生成 {len(file_ops)} 个 FileOp")

        # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
        if "final_file_ops" not in context:
            context["final_file_ops"] = []
        
        # 追加而非覆盖
        context["final_file_ops"].extend(file_ops)
        
        # 向后兼容：仍然保留 file_ops 字段
        context["file_ops"] = context["final_file_ops"]

    except Exception as e:
        print(f"[ERROR] 解析 FileOps 失败: {e}")
        file_ops = []

    # ===== 6. 写入输出 =====
    step["output"] = {
        "text": result,
        "code": code,
        "llm_success": llm_success,
        "file_ops_count": len(file_ops),
        "file_ops": file_ops
    }

    # ===== 7. 写入上下文 =====
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "code": code,
        "file_ops": file_ops
    })

    # ===== 8. 写入事件流 =====
    events.append(create_event("write_output", {
        "text": result,
        "code": code,
        "file_ops": file_ops
    }))

    # ===== 9. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
