# -*- coding: utf-8 -*-
# doubao_planner.py
# ---------------------------------------------------------
# Doubao 专用任务拆解器（Planner）
# - 输入：用户 prompt
# - 输出：严格符合 Worker v2 的 steps 数组
# - 使用 Doubao API，完全独立于 Qwen
# ---------------------------------------------------------

import json
import re
import time
from .doubao_api import call_doubao


def llm_decompose_task(prompt: str) -> list:
    """
    使用 Doubao 拆解任务，返回严格符合 Worker v2 要求的 steps 数组
    
    Args:
        prompt: 用户任务描述
    
    Returns:
        steps 数组，格式：
        [
          {
            "id": "step-1",
            "type": "analyze",
            "input": { "prompt": "..." },
            "status": "pending"
          },
          ...
        ]
    """

    system_prompt = """
你是一个专业的任务规划器，请把用户任务拆成完整的可执行步骤。

必须严格按照以下 8 步执行链生成步骤：
1. analyze - 分析用户需求
2. plan - 制定执行计划
3. write - 生成代码/内容
4. refine - 优化和改进
5. test - 生成并执行测试
6. fix - 修复发现的问题
7. doc - 生成文档
8. docstring - 为代码添加文档字符串

每个步骤必须严格使用以下 JSON 格式：

{
  "id": "step-1",
  "type": "analyze",
  "input": { "prompt": "..." }
}

要求：
1. 必须输出 JSON 数组
2. 不要输出任何解释文字
3. 每个步骤必须包含 id / type / input
4. type 必须是：analyze / plan / write / refine / test / fix / doc / docstring 之一
5. 必须按顺序生成所有 8 个步骤
"""

    user_prompt = f"用户任务：{prompt}"
    
    # 构建完整的 Prompt
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    # ⭐ 重试机制：最多重试 3 次
    max_retries = 3
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            # 调用 Doubao API
            raw_response = call_doubao(full_prompt)
            
            print(f"📝 Doubao API 原始响应（前500字符）: {raw_response[:500]}")
            
            # ⭐ 关键修复：Doubao Responses API 返回的是完整响应对象，不是纯文本
            # 我们需要从 message.content 中提取实际的步骤规划
            
            # 尝试解析为 JSON
            try:
                response_data = json.loads(raw_response)
                
                # ⭐ 修复：只处理 output 中的 message 项，忽略 reasoning
                if "output" in response_data:
                    outputs = response_data["output"]
                    
                    # 找到第一个 message 类型的输出
                    message_item = None
                    for item in outputs:
                        if item.get("type") == "message":
                            message_item = item
                            break
                    
                    if not message_item:
                        raise ValueError("Doubao 响应中没有 message 类型的输出")
                    
                    # 从 message.content 中提取文本
                    content_list = message_item.get("content", [])
                    actual_text = ""
                    
                    for content_item in content_list:
                        if content_item.get("type") == "output_text":
                            actual_text = content_item.get("text", "")
                            break
                    
                    if not actual_text:
                        raise ValueError("无法从 message.content 中提取文本")
                    
                    print(f"📝 提取到的 LLM 响应文本（前300字符）: {actual_text[:300]}")
                    
                    # 从文本中提取 JSON 数组
                    match = re.search(r"\[.*\]", actual_text, re.S)
                    if not match:
                        raise ValueError(f"LLM 响应中未找到 JSON 数组：{actual_text[:200]}")
                    
                    json_str = match.group(0)
                    steps = _parse_steps_json(json_str)
                    
                    # ⭐ 验证步骤格式
                    fixed_steps = _validate_and_fix_steps(steps, prompt)
                    
                    print(f"✅ Doubao Planner 成功拆解任务（第 {attempt} 次尝试）")
                    return fixed_steps
                
                # 如果没有 output 字段，抛出异常
                raise ValueError(f"无法从 Doubao 响应中提取步骤规划")
                
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 解析失败：{e}")
            
        except Exception as e:
            last_error = e
            print(f"⚠️ Doubao Planner 第 {attempt} 次尝试失败：{e}")
            if attempt < max_retries:
                time.sleep(2)  # 等待 2 秒后重试
    
    # 所有重试都失败，使用降级策略
    print(f"❌ Doubao Planner 所有重试均失败，使用降级策略")
    return _fallback_planner(prompt, last_error)


def _parse_steps_json(json_str: str):
    """
    解析步骤 JSON，包含错误修复
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return _repair_json(json_str)


def _repair_json(s: str):
    """
    修复常见的 JSON 格式问题
    """
    # 清理注释和特殊字符
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"//.*?(?=[\n\r])", "", s)
    s = s.replace('\u3000', ' ')
    
    # 修复对象间缺失的逗号
    s = re.sub(r"}\s*{", "}, {", s)
    # 删除末尾多余逗号
    s = re.sub(r",\s*([}\]])", r"\1", s)
    
    # 尝试直接解析
    try:
        return json.loads(s)
    except:
        pass
    
    # 尝试替换单引号
    try:
        return json.loads(s.replace("'", '"'))
    except:
        pass
    
    raise ValueError(f"无法修复 JSON：{s[:200]}")


def _validate_and_fix_steps(steps: list, original_prompt: str) -> list:
    """
    验证并修正步骤格式，确保符合 Worker v2 协议
    """
    if not isinstance(steps, list):
        raise ValueError(f"steps 不是数组：{type(steps)}")
    
    fixed_steps = []
    expected_types = ["analyze", "plan", "write", "refine", "test", "fix", "doc", "docstring"]
    
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {idx} 不是对象：{step}")
        
        # 修正字段名
        if "step" in step and "type" not in step:
            step["type"] = step.pop("step")
        
        # 自动生成 id
        if "id" not in step:
            step["id"] = f"step-{idx+1}"
        
        # 自动生成 input
        if "input" not in step:
            step["input"] = {"prompt": original_prompt}
        
        # 必须有 type
        if "type" not in step:
            # 如果步骤数量匹配，按顺序分配类型
            if idx < len(expected_types):
                step["type"] = expected_types[idx]
            else:
                step["type"] = "analyze"
        
        # 必须有 status
        step.setdefault("status", "pending")
        
        fixed_steps.append(step)
    
    return fixed_steps


def _fallback_planner(prompt: str, error: Exception = None) -> list:
    """
    降级策略：当 LLM 调用失败时，生成默认的步骤链
    """
    error_msg = str(error) if error else "未知错误"
    
    # 生成标准的 8 步执行链
    fallback_steps = [
        {
            "id": "step-1",
            "type": "analyze",
            "input": {"prompt": prompt},
            "status": "pending"
        },
        {
            "id": "step-2",
            "type": "plan",
            "input": {"prompt": "根据分析结果制定执行计划"},
            "status": "pending"
        },
        {
            "id": "step-3",
            "type": "write",
            "input": {"prompt": "根据 engineer 人格生成代码/内容"},
            "status": "pending"
        },
        {
            "id": "step-4",
            "type": "refine",
            "input": {"prompt": "根据执行结果优化代码（多文件协议 v3.0）"},
            "status": "pending"
        },
        {
            "id": "step-5",
            "type": "test",
            "input": {"prompt": "为代码生成并执行 pytest 风格测试"},
            "status": "pending"
        },
        {
            "id": "step-6",
            "type": "fix",
            "input": {"prompt": "根据错误信息修复代码"},
            "status": "pending"
        },
        {
            "id": "step-7",
            "type": "doc",
            "input": {"prompt": "为代码生成 Markdown 文档"},
            "status": "pending"
        },
        {
            "id": "step-8",
            "type": "docstring",
            "input": {"prompt": "为代码添加完整 docstring（多文件）"},
            "status": "pending"
        }
    ]
    
    print(f"⚠️ 使用降级策略生成标准 8 步执行链（原因：{error_msg}）")
    return fallback_steps
