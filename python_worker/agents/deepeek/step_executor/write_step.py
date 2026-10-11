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
from .prompts import write_prompt, creative_write_prompt
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

    # 1) 获取 plan 步骤的输出（若无 plan 则回退到 analyze 输出 + 用户请求）
    user_request = meta.get("user_request", "")

    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if not plan_outputs:
        analyze_outputs = [
            item.get("analysis", "") or item.get("text", "")
            for item in context.get("intermediate_results", [])
            if item.get("type") == "analyze"
        ]
        if analyze_outputs:
            plan_text = f"# 任务分析\n{analyze_outputs[-1]}\n\n# 用户原始请求\n{user_request}"
            print(f"[INFO] write_step 未找到 plan，回退使用 analyze 输出 + 用户请求")
        else:
            plan_text = user_request or "请根据上下文生成内容"
            print(f"[INFO] write_step 未找到 plan 和 analyze，回退使用用户请求")
    else:
        plan_text = plan_outputs[-1]

    # 2) 构建完整 prompt（含人格配置，创意意图跳过 FileOps 格式）
    _creative_intents = {"creative_writing", "translate", "summarization", "chat", "mentor_explain"}
    intent = meta.get("intent", "write_code")

    if intent in _creative_intents:
        base_prompt = creative_write_prompt(plan_text, user_request, intent)
        stream_label = "开始生成内容...\n"
    else:
        base_prompt = write_prompt(plan_text)
        stream_label = "开始生成代码...\n"

    full_prompt = base_prompt
    if persona_config:
        full_prompt = f"{persona_config['system_prompt']}\n\n{full_prompt}"

    # 3) 启动流式输出
    result = ""
    if task_id:
        stream_start(task_id, "✍️ 正在生成内容...", phase="write")

    # 4) 调用 LLM 生成（流式）
    try:
        if task_id:
            stream_chunk(task_id, stream_label, phase="write", channel="reasoning")
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

    # 7) 解析多文件协议 v3.0（创意/对话类意图跳过 FileOps）
    if intent in _creative_intents:
        print(f"[INFO] 创意/对话类意图 ({intent})，跳过 FileOps 解析，直接输出文本")
        file_ops = []
    else:
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