# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.0 — write 步骤（v3.1 多文件协议版本）
# - ⭐ v3.0：支持流式输出（task_id 参数）
# - ⭐ v3.1：支持 FileOps 多文件协议生成
# - ⭐ 与 Qwen Worker v2 完全对齐
# ---------------------------------------------------------

import re
from .qwen_api import call_qwen
from .utils import extract_code
from .prompts import write_prompt
from worker_config import create_event, stream_chunk, stream_start, stream_end

# ⭐ 尝试导入 file_ops，如果失败则使用空实现（用于测试环境）
try:
    # 从项目根目录导入（绝对路径方式）
    import sys
    import os
    python_worker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if python_worker_dir not in sys.path:
        sys.path.insert(0, python_worker_dir)
    
    from file_ops import parse_fileops_v3, create_file_op
    HAS_FILE_OPS = True
except ImportError as e:
    HAS_FILE_OPS = False
    print(f"[WARN] file_ops 模块不可用: {e}")
    
    # 提供空实现
    def parse_fileops_v3(text):
        return []
    
    def create_file_op(**kwargs):
        return {}


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（v3.1）：
    - 模式 1（工程任务）：根据 plan 生成代码，并生成 FileOps
    - 模式 2（对话任务）：直接返回 analyze 的结果或调用 LLM 生成回复
    - ⭐ v3.0：支持流式输出（通过 task_id 参数）
    - ⭐ v3.1：支持多文件协议和 FileOps 生成
    
    参数:
        step: 步骤定义
        context: 上下文对象
        events: 事件列表
        task_id: 任务 ID（可选，用于流式输出）
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成代码...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ⭐ v3.0：选择 API 调用函数（优先使用自定义的，否则用默认）
    api_func = context.get("_custom_api_func", call_qwen)

    # 1) 检查是否有 plan 步骤（工程任务模式）
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if plan_outputs:
        # === 模式 1：工程任务（有 plan）===
        plan_text = plan_outputs[-1]

        # 调用 LLM 生成代码（⭐ 支持流式输出）
        result = ""
        llm_success = False

        try:
            prompt = write_prompt(plan_text)

            if task_id:
                # ⭐ 流式输出模式
                stream_chunk(task_id, "开始生成代码...\n", phase="write", channel="reasoning")
                
                # 注意：Local LLM 的 call_qwen 目前不支持流式，这里先同步调用
                # TODO: 后续需要为 Local LLM 实现流式 API 调用
                result = api_func(prompt)
                stream_chunk(task_id, result, phase="write", channel="content")
            else:
                # 同步调用模式
                result = api_func(prompt)

            if not result:
                raise ValueError("LLM 返回空字符串")

            llm_success = True

        except Exception as e:
            err = f"# LLM 调用失败: {e}"
            result = err
            if task_id:
                stream_chunk(task_id, err, phase="write", channel="reasoning")

        # 提取代码块（单文件降级用）
        code = extract_code(result)

        # ⭐ v3.1：解析多文件协议（核心）
        try:
            file_ops = parse_fileops_v3(result)

            if not file_ops:
                print("[WARN] Local LLM: 未检测到多文件协议，降级为单文件模式")

                # 尝试从结果中推断文件类型
                language = "python"
                if "```javascript" in result or "```js" in result:
                    language = "javascript"
                elif "```typescript" in result or "```ts" in result:
                    language = "typescript"
                elif "```java" in result:
                    language = "java"
                elif "```cpp" in result or "```c++" in result:
                    language = "cpp"

                file_op = create_file_op(
                    action="create",
                    path="main.py" if language == "python" else f"main.{language[:2]}",
                    content=code,
                    file_type="file",
                    language=language,
                    reason="单文件降级模式",
                    from_step="write",
                    intent="write_code"
                )
                file_ops = [file_op]

            print(f"✅ Local LLM write_step 生成 {len(file_ops)} 个 FileOp")
            for op in file_ops:
                print(f"   - {op.get('action')}: {op.get('path')} ({op.get('file_type')})")

            # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
            if "final_file_ops" not in context:
                context["final_file_ops"] = []
            
            # 追加而非覆盖
            context["final_file_ops"].extend(file_ops)
            
            # 向后兼容：仍然保留 file_ops 字段
            context["file_ops"] = context["final_file_ops"]

        except Exception as e:
            print(f"[ERROR] Local LLM 解析 FileOps 失败: {e}")
            import traceback
            traceback.print_exc()
            file_ops = []

        # 写入输出
        step["output"] = {
            "text": result,
            "code": code,
            "llm_success": llm_success,
            "file_ops_count": len(file_ops),
            "file_ops": file_ops
        }

        # 写入上下文（供 refine/test/fix/profile/doc 使用）
        context["intermediate_results"].append({
            "type": "write",
            "text": result,
            "code": code,
            "file_ops": file_ops
        })

        # 写入事件流（供 VSCode 实时展示）
        events.append(create_event("write_output", {
            "text": result,
            "code": code,
            "file_ops": file_ops
        }))
    else:
        # === 模式 2：对话任务（无 plan，直接使用 analyze 或调用 LLM）===
        
        # 检查是否有 analyze 步骤
        analyze_outputs = [
            item["analysis"]
            for item in context["intermediate_results"]
            if item["type"] == "analyze"
        ]

        if analyze_outputs:
            # 如果有 analyze，直接返回其结果（对话任务通常已经在 analyze 中完成）
            analysis_text = analyze_outputs[-1]
            
            # ⭐ 优化：如果 analyze 输出过长（超过 500 字符），调用 LLM 生成简洁回复
            if len(analysis_text) > 500:
                try:
                    # 调用 LLM 基于分析结果生成最终回复
                    result = api_func(f"请基于以下分析结果，用友好、自然的语言直接回答用户的问题：\n\n{analysis_text}")
                except Exception as e:
                    # 如果 LLM 调用失败，降级使用 analyze 的结果
                    result = analysis_text
            else:
                # analyze 输出较短，直接使用
                result = analysis_text
        else:
            # 既没有 plan 也没有 analyze，直接调用 LLM 生成回复
            user_input = step["input"].get("prompt", "")
            try:
                result = api_func(user_input)
            except Exception as e:
                step["output"] = {"text": f"write：LLM 调用失败：{e}"}
                return

        # 写入输出（对话任务不提取代码）
        step["output"] = {
            "text": result
        }

        # 写入上下文
        context["intermediate_results"].append({
            "type": "write",
            "text": result
        })

        # 写入事件流
        events.append(create_event("write_output", {
            "text": result
        }))

    # ===== 9. 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
