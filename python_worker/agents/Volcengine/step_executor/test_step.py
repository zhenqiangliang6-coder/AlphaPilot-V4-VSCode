# -*- coding: utf-8 -*-
# step_executor/test_step.py — AlphaPilot OS v3.0
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - 所有测试生成必须在 Worker 内部完成
#    - 前端、Node API、VSCode 插件都不能生成测试文件
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - test_step 必须输出 FileOps（唯一合法的文件操作方式）
#    - 测试文件必须使用多文件协议 v3.0（# TEST:）
#
# 本模块负责：
# 1. 根据 write_step 的代码自动生成 pytest 风格测试
# 2. 自动注入 fake pytest（支持 assert / raises）
# 3. 输出测试文件的 FileOps（tests/test_xxx.py）
# ⭐ 4. 支持流式输出（实时展示测试生成过程）
# ⭐ 5. 支持人格配置（从 context.meta 读取）
# ---------------------------------------------------------

from ..doubao_api import call_doubao, call_doubao_stream
from .utils import extract_code, FAKE_PYTEST
from .prompts import test_prompt
from ....code_executor import run_python
from ....worker_config import create_event, stream_chunk, stream_start, stream_end
from ....file_ops import parse_fileops_v3


def run_test_step(step, context, events, task_id=None):
    """
    test 步骤（官方 + 智能增强版 + 流式输出 + 人格配置）
    ---------------------------------------------------------
    输入：
        - write_step 的多文件协议文本
    输出：
        - 自动生成的 pytest 测试文件（# TEST:）
        - FileOps（用于 Node API 写入 tests/ 目录）
    
    ⭐ 流式输出支持：
        - 通过 task_id 发送 stream_chunk 事件
        - 实时展示 AI 测试生成过程 (channel=reasoning)
    
    ⭐ 人格配置支持：
        - 从 context.meta 读取 persona 类型
        - 动态注入 System Prompt
    """

    # ===== 第0层：启动流式输出 =====
    if task_id:
        try:
            stream_start(task_id, "🧪 正在生成测试...", phase="test")
        except Exception as e:
            print(f"[WARN] stream_start 失败: {e}")

    # ===== 第0.5层：⭐ 获取人格配置（豆包独立实现）=====
    persona_config = None
    try:
        meta = context.get("meta", {})
        persona_type = meta.get("persona", "engineer")
        
        from ..personas import get_persona_config
        persona_config = get_persona_config(persona_type)
        
        print(f"🎨 test_step 使用人格: {persona_config['name']}")
    except Exception as e:
        print(f"[WARN] 获取人格配置失败: {e}")
        persona_config = None

    # =========================================================
    # ① 获取 write_step 的多文件协议文本
    # =========================================================
    write_outputs = [
        item["text"]
        for item in context["intermediate_results"]
        if item["type"] == "write"
    ]

    if not write_outputs:
        msg = "test：未找到 write 步骤的代码，无法生成测试用例。"
        if task_id:
            stream_chunk(task_id, msg, phase="test", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    write_text = write_outputs[-1]

    # =========================================================
    # ② 提取 write_step 中的"主代码块"
    #    - test_prompt 需要单文件代码作为输入
    #    - 所以我们提取第一个 ```python 代码块
    # =========================================================
    code = extract_code(write_text)

    if not code:
        msg = "test：write 步骤未提供可解析的代码块。"
        if task_id:
            stream_chunk(task_id, msg, phase="test", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # =========================================================
    # ③ 调用 LLM 生成 pytest 风格测试代码（流式输出）
    # =========================================================
    test_code_text = ""
    llm_success = False
    
    try:
        # ⭐ 构建完整 prompt（含人格配置）
        if persona_config:
            system_prompt = persona_config.get("system_prompt", "")
            full_prompt = f"{system_prompt}\n\n---\n\n用户请求:\n{test_prompt(code)}"
        else:
            full_prompt = test_prompt(code)

        # ⭐ 使用流式调用
        if task_id:
            for chunk in call_doubao_stream(full_prompt):
                test_code_text += chunk
                stream_chunk(task_id, chunk, phase="test", channel="reasoning")
        else:
            # 非流式模式（向后兼容）
            test_code_text = call_doubao(full_prompt)

        llm_success = True

    except Exception as e:
        error_msg = f"test：LLM 调用失败：{e}"
        test_code_text = error_msg
        
        if task_id:
            stream_chunk(task_id, error_msg, phase="test", channel="reasoning")

    test_code = extract_code(test_code_text)

    if not test_code:
        msg = "test：未能从 LLM 输出中提取到有效的测试代码。"
        if task_id:
            stream_chunk(task_id, msg, phase="test", channel="reasoning")
        step["output"] = {"text": msg}
        
        if task_id:
            try:
                stream_end(task_id)
            except Exception as e:
                print(f"[WARN] stream_end 失败: {e}")
        return

    # =========================================================
    # ④ 组合执行 fake pytest + 用户代码 + 测试代码
    # =========================================================
    full_code = FAKE_PYTEST + "\n\n" + code + "\n\n" + test_code
    exec_result = run_python(full_code)

    exec_summary = (
        f"stdout:\n{exec_result['stdout']}\n\n"
        f"stderr:\n{exec_result['stderr']}\n\n"
        f"error:\n{exec_result['error']}"
    )

    # =========================================================
    # ⑤ 将测试代码包装成多文件协议 v3.0（# TEST:）
    # =========================================================
    test_protocol = f"# TEST: tests/test_generated.py\n{test_code}"

    # 解析成 FileOps
    test_file_ops = []
    try:
        test_file_ops = parse_fileops_v3(test_protocol)
        print(f"✅ test_step 生成 {len(test_file_ops)} 个 FileOp")
        
        # ⭐ 写入 context（使用 final_file_ops 作为唯一真相源）
        if "final_file_ops" not in context:
            context["final_file_ops"] = []
        
        # 追加而非覆盖
        context["final_file_ops"].extend(test_file_ops)
        
        # 向后兼容：仍然保留 file_ops 字段
        context["file_ops"] = context["final_file_ops"]
        
    except Exception as e:
        print(f"[ERROR] 解析 FileOps 失败: {e}")

    # =========================================================
    # ⑥ 写入输出
    # =========================================================
    step["output"] = {
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    }

    # =========================================================
    # ⑦ 写入上下文（供 refine_step 使用）
    # =========================================================
    context["intermediate_results"].append({
        "type": "test",
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary,
        "llm_success": llm_success
    })

    # =========================================================
    # ⑧ 写入事件流（供 VSCode 实时展示）
    # =========================================================
    events.append(create_event("test_output", {
        "text": test_protocol,
        "test_code": test_code,
        "file_ops": test_file_ops,
        "exec_summary": exec_summary
    }))
    
    # ⭐ 结束流式输出
    if task_id:
        try:
            stream_end(task_id)
        except Exception as e:
            print(f"[WARN] stream_end 失败: {e}")
