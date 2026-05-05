# -*- coding: utf-8 -*-
# planner.py
# ---------------------------------------------------------
# LLM 任务拆解器（Planner）
# - 输入：用户 prompt
# - 输出：严格符合 Worker v2 的 steps 数组
# ---------------------------------------------------------

import json
import re
import requests
import ast
from .worker_config import DASHSCOPE_API_KEY   # ← ★ 修复后的正确路径


def llm_decompose_task(prompt: str) -> list:
    """
    使用 Qwen 拆解任务，返回严格符合 Worker v2 要求的 steps 数组：
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
你是一个专业的任务规划器，请把用户任务拆成 2~5 个可执行步骤。

每个步骤必须严格使用以下 JSON 格式：

{
  "id": "step-1",
  "type": "analyze",   // analyze / plan / write / refine / test
  "input": { "prompt": "..." }
}

要求：
1. 必须输出 JSON 数组
2. 不要输出任何解释文字
3. 每个步骤必须包含 id / type / input
4. type 必须是：analyze / plan / write / refine / test 之一
"""

    user_prompt = f"用户任务：{prompt}"

    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    body = {
        "model": "qwen-turbo",
        "input": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        },
        "parameters": {
            "result_format": "json"
        }
    }

    r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()

    # -------------------------------
    # 兼容所有 DashScope 返回格式
    # -------------------------------
    output = data.get("output", {})

    if "text" in output:
        raw = output["text"]
    elif "choices" in output:
        raw = output["choices"][0]["message"]["content"]
    else:
        raise ValueError(f"LLM 返回格式异常：{data}")

    # -------------------------------
    # ⭐ 从文本中提取 JSON 数组
    # -------------------------------
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        raise ValueError(f"LLM 未返回 JSON 数组：{raw}")

    json_str = match.group(0)

    # -------------------------------
    # ⭐ 尝试修复常见的 JSON 格式问题（更鲁棒的修复器）
    # -------------------------------
    def _repair_json(s: str):
        # 初步清理：去注释与全角空格
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        s = re.sub(r"//.*?(?=[\n\r])", "", s)
        s = s.replace('\u3000', ' ')

        # 插入缺失的对象间分隔逗号：}{ -> },{
        s_prep = re.sub(r"}\s*{", "}, {", s)
        # 删除对象或数组末尾的多余逗号
        s_prep = re.sub(r",\s*([}\]])", r"\1", s_prep)

        def _ensure_dict_list(val):
            if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                return val
            if isinstance(val, dict):
                return [val]
            return None

        # 先尝试 JSON 解析
        try:
            v = json.loads(s_prep)
            ok = _ensure_dict_list(v)
            if ok is not None:
                return ok
        except Exception:
            pass

        # 尝试把单引号替换为双引号并再次解析
        s_double = s_prep.replace("'", '"')
        try:
            v = json.loads(s_double)
            ok = _ensure_dict_list(v)
            if ok is not None:
                return ok
        except Exception:
            pass

        # 尝试将常见 JS 字面量替换为 Python 字面量，然后使用 ast.literal_eval
        s_py = s_prep
        s_py = re.sub(r"\bnull\b", 'None', s_py)
        s_py = re.sub(r"\btrue\b", 'True', s_py, flags=re.I)
        s_py = re.sub(r"\bfalse\b", 'False', s_py, flags=re.I)

        # ast.literal_eval 能解析单引号/尾随逗号等 Python 风格字面量
        try:
            val = ast.literal_eval(s_py)
            ok = _ensure_dict_list(val)
            if ok is not None:
                return ok
        except Exception:
            pass

        # 最后退化：尝试提取每个完整的大括号对象并拼接（最保守策略）
        inner = s_prep
        m = re.search(r"^\s*\[\s*(.*)\s*\]\s*$", inner, re.S)
        if m:
            inner = m.group(1)

        objs = []
        depth = 0
        buf = ''
        in_str = False
        esc = False
        for ch in inner:
            buf += ch
            if ch == '\\' and not esc:
                esc = True
                continue
            if ch in ('"', "'") and not esc:
                in_str = not in_str
            if not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            if esc:
                esc = False
            if depth == 0 and buf.strip():
                piece = buf.strip()
                piece = re.sub(r'^,\s*', '', piece)
                piece = re.sub(r',\s*}$', '}', piece)
                objs.append(piece)
                buf = ''

        cleaned = []
        for o in objs:
            # 尝试 JSON -> 单引号替换 -> ast 顺序
            try:
                v = json.loads(o)
                if isinstance(v, dict):
                    cleaned.append(v)
                    continue
            except Exception:
                pass
            try:
                v = json.loads(o.replace("'", '"'))
                if isinstance(v, dict):
                    cleaned.append(v)
                    continue
            except Exception:
                pass
            try:
                v = ast.literal_eval(o)
                if isinstance(v, dict):
                    cleaned.append(v)
                    continue
            except Exception:
                pass

        if cleaned:
            return cleaned

        raise ValueError('无法修复 JSON')

    # 先尝试直接解析，失败后走修复器
    try:
        steps = json.loads(json_str)
    except Exception:
        try:
            steps = _repair_json(json_str)
        except Exception as e:
            raise ValueError(f"JSON 解析失败：{e}\n原始内容：{json_str}")

    # -------------------------------
    # ⭐ 修正字段，确保符合 Worker v2 协议
    # -------------------------------
    fixed_steps = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤不是对象：{step}")

        # 修正模型可能输出的字段名
        if "step" in step and "type" not in step:
            step["type"] = step.pop("step")

        # 自动生成 id
        if "id" not in step:
            step["id"] = f"step-{idx+1}"

        # 自动生成 input
        if "input" not in step:
            step["input"] = {"prompt": prompt}

        # 必须有 type
        if "type" not in step:
            step["type"] = "analyze"

        # 必须有 status
        step.setdefault("status", "pending")

        fixed_steps.append(step)

    return fixed_steps
