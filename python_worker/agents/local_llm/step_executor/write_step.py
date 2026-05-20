# -*- coding: utf-8 -*-
# step_executor/write_step.py
# ---------------------------------------------------------
# Local LLM Worker v3.1 — write 步骤（本地模型 + 多文件协议）
# - 使用 local_api.call_local_llm 作为默认 LLM 调用
# - 支持 FileOps 多文件协议 v3.0
# - 支持流式（通过 context["_custom_api_func"] 注入）
# ---------------------------------------------------------

import re
from ..local_api import call_local_llm
from .utils import extract_code
from .prompts import write_prompt
from worker_config import create_event, stream_chunk, stream_start, stream_end

# ⭐ 尝试导入 file_ops，如果失败则使用空实现（用于测试环境）
try:
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

    def parse_fileops_v3(text):
        return []

    def create_file_op(**kwargs):
        return {}


def extract_ascii_tree(text: str) -> str:
    """
    从 LLM 输出中提取 ASCII 文件树
    
    参数:
        text: LLM 完整输出文本
    
    返回:
        str: ASCII 文件树字符串，如果未找到则返回空字符串
    
    示例:
        >>> extract_ascii_tree("### FILE_TREE\nproject/\n├── file.py")
        "project/\n├── file.py"
    """
    if not text:
        return ""

    # 查找 ### FILE_TREE 分隔符
    pattern = r'###\s*FILE_TREE\s*\n(.*?)(?:\n###|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        tree_content = match.group(1).strip()
        print(f"[INFO] 成功提取 ASCII 文件树 ({len(tree_content)} 字符)")
        return tree_content
    
    # 降级方案：尝试匹配常见的 ASCII 树格式（如果没有显式标记）
    tree_pattern = re.compile(
        r"(?:^|\n)"          # 开始或换行
        r"("                 # 捕获组
        r"(?:[\w./\-]+\s*\n)??" # 可选的根目录名称
        r"(?:(?:[│├└─\s]+[\w.\-]+\s*\n?)+)" # 树状结构主体
        r")",                # 结束捕获组
        re.MULTILINE
    )
    
    match = tree_pattern.search(text)
    if match:
        tree_content = match.group(1).strip()
        # 简单验证：至少包含一个树状连接符
        if any(char in tree_content for char in ['├', '└', '│']):
            print(f"[INFO] 成功提取 ASCII 文件树 (自动检测格式, {len(tree_content)} 字符)")
            return tree_content

    print("[WARN] 未找到 ASCII 文件树")
    return ""


def parse_nl_fileops_enhanced(text: str) -> list:
    """增强版自然语言多文件解析器（模块级别函数）。

    支持格式（优先级从高到低）：
    1. ### <filename> 分隔符格式（Gemma 4B 擅长）
    2. 文件名 + fenced code block
    3. 文件名 + 内容块
    4. Markdown 标题/序号 + fenced code block
    
    仅接受后缀为 .py/.md/.txt/.js/.ts/.java 的文件名，且内容长度至少 8 字符。
    返回: list of (filename, content)
    """
    ops = []

    if not text or not text.strip():
        return ops

    # ===== 优先级 1: ### 分块格式（Gemma 4B 最擅长）=====
    if "### " in text:
        blocks = [b.strip() for b in text.split("### ") if b.strip()]
        for block in blocks:
            parts = block.split("\n", 1)
            if len(parts) == 2:
                fname = parts[0].strip()
                content = parts[1].strip()
                
                # 验证文件名格式
                if re.match(r"^[\w\-./]+\.(py|md|txt|js|ts|java)$", fname):
                    # 清理内容中的 Markdown 代码块标记
                    content = re.sub(r'^```(?:\w+)?\n?', '', content)
                    content = re.sub(r'\n?```\s*$', '', content)
                    content = content.strip()
                    
                    if len(content) >= 8:
                        ops.append((fname, content))
        
        if ops:
            print(f"[INFO] 成功解析 {len(ops)} 个文件 (### 分隔符格式)")
            return ops

    # ===== 优先级 2: 文件名 + fenced code block =====
    fname_pattern = re.compile(r"^(?P<name>[\w\-./]+\.(py|md|txt|js|ts|java))$", re.MULTILINE)
    for m in fname_pattern.finditer(text):
        name = m.group("name")
        start = m.end()
        
        # 查找接下来的 fenced code
        fenced = re.search(r"```(?:[\w+-]+)?\n(.*?)\n```", text[start:], re.S)
        if fenced:
            content = fenced.group(1).strip()
        else:
            # 否则取直到下一个文件名或两个换行为止的内容
            next_fname = fname_pattern.search(text, pos=start)
            end_pos = next_fname.start() if next_fname else None
            snippet = text[start:end_pos].strip() if end_pos else text[start:].strip()
            content = snippet

        if len(content) >= 8:
            ops.append((name, content))
    
    if ops:
        print(f"[INFO] 成功解析 {len(ops)} 个文件 (文件名 + fenced code block)")
        return ops

    # ===== 优先级 3: ⭐ v3.2.1 新增 - 纯文本文件名 + 代码内容（Gemma 4B 降级方案）=====
    # 匹配模式: 单独一行的文件名(如 "data_processor.py"),后面跟着代码内容
    lines = text.split('\n')
    current_file = None
    current_content_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检测是否是文件名行(单独一行,以 .py/.md/.txt/.js/.ts/.java 结尾)
        if re.match(r"^[\w\-./]+\.(py|md|txt|js|ts|java)$", stripped):
            # 如果之前已经在收集另一个文件的内容,先保存
            if current_file and current_content_lines:
                content = '\n'.join(current_content_lines).strip()
                if len(content) >= 8:
                    ops.append((current_file, content))
            
            # 开始新文件
            current_file = stripped
            current_content_lines = []
        elif current_file:
            # 跳过空行分隔符,但保留代码中的空行
            current_content_lines.append(line)
    
    # 保存最后一个文件
    if current_file and current_content_lines:
        content = '\n'.join(current_content_lines).strip()
        if len(content) >= 8:
            ops.append((current_file, content))
    
    if ops:
        print(f"[INFO] 成功解析 {len(ops)} 个文件 (纯文本文件名格式)")
        return ops

    # ===== 优先级 4: ⭐⭐⭐⭐ v3.2.2 新增 - Markdown 标题/序号 + fenced code block（Gemma 4B 真实格式）=====
    # 匹配模式: "1. calculator.py" 或 "### calculator.py" 等 Markdown 格式,后面跟着 ```python ... ```
    # 使用更宽松的正则:允许前面有数字、标点、Markdown 标记,后面可以有任意文本
    markdown_fname_pattern = re.compile(r"(?:^|\n)(?:\d+\.?\s*|#{1,6}\s*|\*\s*)?(?P<name>[\w\-./]+\.(py|md|txt|js|ts|java))(?:\s|$)", re.MULTILINE)
    
    for m in markdown_fname_pattern.finditer(text):
        name = m.group("name")
        start = m.end()
        
        # 查找接下来的 fenced code block
        fenced = re.search(r"```(?:python|````|``````)?\n(.*?)```", text[start:], re.S)
        if fenced:
            content = fenced.group(1).strip()
            
            # 验证内容长度
            if len(content) >= 8:
                ops.append((name, content))
    
    if ops:
        print(f"[INFO] 成功解析 {len(ops)} 个文件 (Markdown 标题格式 - Gemma 4B 真实输出)")
        return ops

    print("[WARN] 无法解析任何文件格式,返回空数组")
    return []


def run_write_step(step, context, events, task_id=None):
    """
    write 步骤（v3.1）：
    - 模式 1（工程任务）：根据 plan 生成代码，并生成 FileOps
    - 模式 2（对话任务）：直接返回 analyze 的结果或调用 LLM 生成回复
    - ⭐ 支持流式输出（通过 task_id 参数）
    - ⭐ 支持多文件协议和 FileOps 生成
    """

    # ===== 0. 流式输出开始 =====
    if task_id:
        try:
            stream_start(task_id, "✍️ 正在生成代码...", phase="write")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ⭐ 默认使用本地 LLM，如果 context 中注入了 _custom_api_func，则优先使用注入的
    api_func = context.get("_custom_api_func", call_local_llm)

    # 1) 检查是否有 plan 步骤（工程任务模式）
    plan_outputs = [
        item["plan"]
        for item in context["intermediate_results"]
        if item["type"] == "plan"
    ]

    if plan_outputs:
        # === 模式 1：工程任务（有 plan）===
        plan_text = plan_outputs[-1]

        # ⭐ v3.2.1 关键修复：从 context.meta 读取 persona_config 并注入到 prompt
        persona_system_prompt = ""
        try:
            meta = context.get("meta", {})
            persona_config = meta.get("persona_config", {})
            if persona_config:
                persona_system_prompt = persona_config.get("system_prompt", "")
                print(f"[INFO] write_step 已加载 persona system_prompt (长度: {len(persona_system_prompt)} 字符)")
        except Exception as e:
            print(f"[WARN] 获取 persona_config 失败: {e}, 将不使用 system_prompt")

        # 调用 LLM 生成代码（⭐ 支持流式输出 + persona 注入）
        result = ""
        llm_success = False

        try:
            base_prompt = write_prompt(plan_text)
            
            # ⭐ 关键：如果存在 persona system_prompt,将其拼接到 prompt 前面
            if persona_system_prompt:
                prompt = f"{persona_system_prompt}\n\n---\n\n{base_prompt}"
                print("[INFO] 已将 persona system_prompt 注入到 write prompt")
            else:
                prompt = base_prompt

            if task_id:
                # ⭐ 流式输出模式（local_worker_v3 会注入带 stream 的 wrapper）
                stream_chunk(task_id, "开始生成代码...\n", phase="write", channel="reasoning")
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
        file_ops = []
        try:
            if HAS_FILE_OPS:
                file_ops = parse_fileops_v3(result)
            else:
                file_ops = []

            if not file_ops:
                # ⭐ v3.2.1 增强：优先尝试解析自然语言多文件格式（支持 ### 分隔符）
                file_ops_raw = parse_nl_fileops_enhanced(result)
                print(f"[DEBUG] parse_nl_fileops_enhanced 返回: {len(file_ops_raw) if file_ops_raw else 0} 个文件")
                if file_ops_raw:
                    for fname, content in file_ops_raw:
                        print(f"  - {fname}: {len(content)} 字符")
                    
                    file_ops = []
                    for fname, content in file_ops_raw:
                        try:
                            op = create_file_op(
                                action="create",
                                path=fname,
                                content=content
                            )
                            file_ops.append(op)
                        except Exception as e:
                            print(f"[WARN] 创建 FileOp 失败 {fname}: {e}")
        except Exception as e:
            print(f"[ERROR] 解析多文件协议失败 (模式1): {e}")
        
        # 如果解析到 FileOps，更新 context["final_file_ops"]
        if file_ops:
            context["final_file_ops"] = file_ops

        # ⭐ v3.2.1 关键修复：如果解析到 FileOps，更新 context["final_file_ops"]（唯一真相源）
        if file_ops:
            context["final_file_ops"] = file_ops
            print(f"[SUCCESS] write_step 生成 {len(file_ops)} 个 FileOps")
            
            # ⭐ v3.2.3 新增：解析并展示 ASCII 文件树
            ascii_tree = extract_ascii_tree(result)
            if ascii_tree:
                print("\n 生成的文件结构:")
                print(ascii_tree)
                print()
                
                # 将 ASCII 树添加到 events 中，供前端展示
                if task_id:
                    try:
                        event = create_event(
                            "file_tree",
                            {"ascii_tree": ascii_tree, "file_count": len(file_ops)}
                        )
                        events.append(event)
                    except Exception as e:
                        print(f"[WARN] 创建 file_tree 事件失败: {e}")
        else:
            # 降级：单文件模式
            if code:
                context["current_code"] = code
                print("[INFO] write_step 使用单文件降级模式")
            else:
                context["current_code"] = result
                print("[WARN] write_step 未提取到代码块，保存原始输出")

        # 记录事件
        if task_id:
            try:
                event_data = {"text": result}
                if file_ops:
                    event_data["file_count"] = len(file_ops)
                elif code:
                    event_data["code_length"] = len(code)
                
                event = create_event("write_output", event_data)
                events.append(event)
            except Exception as e:
                print(f"[WARN] 创建事件失败: {e}")

        # ===== 流式输出结束 =====
        if task_id:
            try:
                stream_end(task_id)  # ⭐ 修复: stream_end 只接受 task_id 参数
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        
        return {
            "type": "write",
            "status": "completed",
            "output": {"text": result},
        }

    else:
        # === 模式 2：对话任务（无 plan）===
        # ⭐ v3.2.2 关键修复：Local Worker 直接使用用户原始 prompt 作为工程任务
        meta = context.get("meta", {})
        execution_chain = meta.get("execution_chain", [])
        
        # 检测是否为 Local Worker 的工程任务(只有 write 步骤)
        is_local_engineering_task = (
            len(execution_chain) == 1 and 
            execution_chain[0] == "write"
        )
        
        if is_local_engineering_task:
            # Local Worker 工程任务模式：直接使用用户原始 prompt
            user_query = context.get("user_query", "")
            
            if not user_query:
                # 尝试从 task payload 获取
                try:
                    # context 中可能存储了原始任务信息
                    user_query = "请根据需求生成代码。"
                except:
                    user_query = "请根据需求生成代码。"
            
            # 使用工程任务的 prompt
            base_prompt = write_prompt(user_query)
            print(f"[INFO] Local Worker 工程任务模式，使用用户 prompt: {user_query[:50]}...")
        else:
            # 普通对话任务模式
            user_query = context.get("user_query", "")
            
            if not user_query:
                # 尝试从 intermediate_results 获取 analyze 的结果
                analyze_outputs = [
                    item["analysis"]
                    for item in context["intermediate_results"]
                    if item["type"] == "analyze"
                ]
                if analyze_outputs:
                    user_query = analyze_outputs[-1]
                else:
                    user_query = "请帮我解答这个问题。"

            # 调用 LLM
            base_prompt = f"你是一个专业的编程助手。请回答以下问题：\n\n{user_query}"

        # ⭐ 注入 persona system_prompt
        persona_config = meta.get("persona_config", {})
        if persona_config:
            persona_system_prompt = persona_config.get("system_prompt", "")
            if persona_system_prompt:
                prompt = f"{persona_system_prompt}\n\n---\n\n{base_prompt}"
            else:
                prompt = base_prompt
        else:
            prompt = base_prompt

        # 调用 LLM
        try:
            if task_id:
                stream_chunk(task_id, "正在思考...\n", phase="write", channel="reasoning")
                result = api_func(prompt)
                stream_chunk(task_id, result, phase="write", channel="content")
            else:
                result = api_func(prompt)

            if not result:
                result = "# LLM 返回空字符串"

        except Exception as e:
            result = f"# LLM 调用失败: {e}"

        context["current_code"] = result
        
        # ⭐ v3.2.2 关键修复：即使是模式 2（对话任务），也需要尝试解析 FileOps
        file_ops = []
        try:
            file_ops_raw = parse_nl_fileops_enhanced(result)
            print(f"[DEBUG] parse_nl_fileops_enhanced 返回: {len(file_ops_raw) if file_ops_raw else 0} 个文件")
            if file_ops_raw:
                for fname, content in file_ops_raw:
                    print(f"  - {fname}: {len(content)} 字符")
                
                for fname, content in file_ops_raw:
                    try:
                        op = create_file_op(
                            action="create",
                            path=fname,
                            content=content
                        )
                        file_ops.append(op)
                    except Exception as e:
                        print(f"[WARN] 创建 FileOp 失败 {fname}: {e}")
        except Exception as e:
            print(f"[ERROR] 解析多文件协议失败 (模式2): {e}")
        
        # 如果解析到 FileOps，更新 context["final_file_ops"]
        if file_ops:
            context["final_file_ops"] = file_ops
            print(f"[SUCCESS] write_step 生成 {len(file_ops)} 个 FileOps")
            
            # ⭐ v3.2.3 新增：解析并展示 ASCII 文件树
            ascii_tree = extract_ascii_tree(result)
            if ascii_tree:
                print("\n 生成的文件结构:")
                print(ascii_tree)
                print()
                
                # 将 ASCII 树添加到 events 中，供前端展示
                if task_id:
                    try:
                        event = create_event(
                            "file_tree",
                            {"ascii_tree": ascii_tree, "file_count": len(file_ops)}
                        )
                        events.append(event)
                    except Exception as e:
                        print(f"[WARN] 创建 file_tree 事件失败: {e}")
            
            if task_id:
                event = create_event(
                    "write_output",
                    {"text": result, "file_count": len(file_ops)}
                )
                events.append(event)
        else:
            # 降级：单文件模式
            print("[INFO] write_step 使用单文件降级模式")
            
            if task_id:
                event = create_event(
                    "write_output",
                    {"text": result}
                )
                events.append(event)

    # ===== 流式输出结束 =====
    if task_id:
        try:
            stream_end(task_id)  # ⭐ 修复: stream_end 只接受 task_id 参数
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")

    return {
        "type": "write",
        "status": "completed",
        "output": {"text": result},
    }
