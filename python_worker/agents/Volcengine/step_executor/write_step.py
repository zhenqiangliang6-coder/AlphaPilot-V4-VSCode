# -*- coding: utf-8 -*-
# step_executor/write_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有代码生成必须在 Worker 内部完成
#    - 前端、Node API、VSCode 插件都不能生成文件
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - write_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - FileOps 必须遵守多文件协议 v3.0
#
# 本模块负责：
# 1. 根据 plan 生成多文件代码
# 2. 解析 # FILE / # TEST / # DOC / # META / # DEPENDS
# 3. 生成 FileOps（action/path/type/content）
# ⭐ 4. 支持流式输出（实时展示代码生成过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .prompts import write_prompt
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3, create_file_op


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（v3.0 多文件协议版本 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - plan 步骤的规划内容
    输出：
        - LLM 输出的多文件协议文本
        - 解析后的 FileOps（供 Node API 执行）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示代码生成过程 (channel=content)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成代码...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 1. 获取 persona / intent（豆包独立实现）=====
    persona_config = None
    intent = "write_code"

    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        intent = meta.get("intent", "write_code")

        # ⭐ 使用豆包自己的人格配置（不依赖 Qwen）
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
        if task_id:
            stream_chunk(task_id, msg, phase="write", channel="reasoning")
        step["output"] = {"text": msg, "code": ""}
        
        # 写入上下文
        context["intermediate_results"].append({
            "type": "write",
            "text": msg,
            "code": "",
            "file_ops": []
        })
        
        # 写入事件流
        events.append(create_event("write_output", {
            "text": msg,
            "code": "",
            "file_ops": []
        }))
        
        # 结束流式输出
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    plan_text = plan_outputs[-1]

    # ===== 3. 调用 LLM（支持流式输出 + 人格配置）=====
    result = ""
    llm_success = False

    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{write_prompt(plan_text)}"
        else:
            full_prompt = write_prompt(plan_text)

        if task_id:
            stream_chunk(task_id, "开始生成代码...\n", phase="write", channel="reasoning")

            # ⭐ 尝试流式调用，如果失败则降级到非流式
            try:
                for chunk in call_doubao_stream(full_prompt):
                    result += chunk
                    stream_chunk(task_id, chunk, phase="write", channel="content")
                
                # 如果流式返回空，降级到非流式
                if not result:
                    print("[WARN] 流式调用返回空，降级到非流式模式")
                    stream_chunk(task_id, "[系统] 切换到非流式模式...\n", phase="write", channel="reasoning")
                    result = call_doubao(full_prompt)
            except Exception as stream_error:
                print(f"[WARN] 流式调用失败，降级到非流式模式: {stream_error}")
                stream_chunk(task_id, f"[系统] 流式失败，切换非流式: {stream_error}\n", phase="write", channel="reasoning")
                result = call_doubao(full_prompt)
        else:
            # 非流式模式（向后兼容）
            result = call_doubao(full_prompt)

        if not result:
            raise ValueError("LLM 返回空字符串")

        llm_success = True

    except Exception as e:
        err = f"# LLM 调用失败: {e}"
        result = err
        if task_id:
            stream_chunk(task_id, err, phase="write", channel="reasoning")

    # ===== 4. 提取代码（单文件降级用）=====
    from .utils import extract_code
    code = extract_code(result)

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
