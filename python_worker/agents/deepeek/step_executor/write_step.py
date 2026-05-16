# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# write 步骤：根据 plan 生成代码（v3.0 流式输出版）
# - 支持多文件协议 v3.0（FILE/TEST/DOC/META/DEPENDS）
# - 流式输出到前端
# - 使用 DeepSeek 独立的人格配置
# ---------------------------------------------------------

from ..deepseek_api import call_deepseek, call_deepseek_stream
from .utils import extract_code
from .prompts import write_prompt
from ....worker_config import create_event, stream_start, stream_chunk, stream_end
import re


def parse_fileops_v3(text: str) -> list:
    """
    解析多文件协议 v3.0
    
    支持的协议格式：
    # FILE: path/to/file.py
    # TEST: path/to/test_file.py
    # DOC: path/to/doc.md
    # META: key=value
    # DEPENDS: file1.py,file2.py
    ```language
    code content
    ```
    """
    file_ops = []
    
    # 匹配文件块
    pattern = r'# (FILE|TEST|DOC): (.+?)\n```(\w+)?\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for op_type, path, lang, content in matches:
        file_op = {
            "op": "create",
            "path": path.strip(),
            "type": "file",
            "content": content.strip(),
            "language": lang or "python",
            "from_step": "write"
        }
        
        # 标记测试文件和文档文件
        if op_type == "TEST":
            file_op["reason"] = "测试文件"
        elif op_type == "DOC":
            file_op["reason"] = "文档文件"
        else:
            file_op["reason"] = "源代码文件"
        
        file_ops.append(file_op)
    
    return file_ops


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤：
    - 输入：plan 步骤的规划
    - 输出：生成的 Python 代码（支持多文件协议 v3.0）
    
    ⭐ v3.0 新增：
        - 支持流式输出（stream_start/stream_chunk/stream_end）
        - 使用 DeepSeek 独立的人格配置
        - 解析多文件协议 v3.0
        - 更新 context["final_file_ops"]（唯一真相源）
        - 统一签名：task_id 参数
    
    参数:
        task_id: 任务 ID，用于流式输出
    """

    # ===== 第0.5层：⭐ 获取人格配置（DeepSeek独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 write_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # 1) 获取 plan 步骤的输出
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if not plan_outputs:
        step["output"] = {"text": "write：未找到 plan 步骤的规划内容。"}
        return

    plan_text = plan_outputs[-1]

    # 2) 构建完整 prompt（含人格配置）
    full_prompt = write_prompt(plan_text)
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "✍️ 正在生成代码...", phase="write")

    # 4) 调用 LLM 生成代码（流式）
    try:
        if task_id:
            # 流式调用
            stream_chunk(task_id, "开始生成代码...\n", phase="write", channel="reasoning")
            for chunk in call_deepseek_stream(full_prompt):
                result += chunk
                stream_chunk(task_id, chunk, phase="write", channel="content")
        else:
            # 非流式调用（向后兼容）
            result = call_deepseek(full_prompt)
    except Exception as e:
        step["output"] = {"text": f"write：LLM 调用失败：{e}"}
        if task_id:
            stream_end(task_id)
        return

    # 5) 结束流式输出
    if task_id:
        stream_end(task_id)

    # 6) 提取代码块（向后兼容）
    code = extract_code(result)

    # 7) 解析多文件协议 v3.0
    file_ops = parse_fileops_v3(result)
    
    # ⭐ 更新 final_file_ops（唯一真相源）
    if "final_file_ops" not in context:
        context["final_file_ops"] = []
    
    context["final_file_ops"].extend(file_ops)
    context["file_ops"] = context["final_file_ops"]  # 向后兼容别名

    # 8) 写入输出
    step["output"] = {
        "text": result,
        "code": code,
        "file_ops": file_ops
    }

    # 9) 写入上下文（供 refine/test/fix/profile/doc 使用）
    context["intermediate_results"].append({
        "type": "write",
        "text": result,
        "code": code,
        "file_ops": file_ops
    })

    # 10) 写入事件流（供 VSCode 实时展示）
    events.append(create_event("write_output", {
        "text": result,
        "code": code,
        "file_ops": file_ops
    }))
