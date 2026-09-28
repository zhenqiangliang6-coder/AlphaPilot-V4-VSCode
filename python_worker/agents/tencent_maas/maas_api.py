# -*- coding: utf-8 -*-
# maas_api.py
# ---------------------------------------------------------
# 腾讯 MaaS (TokenHub) API 调用封装
# - OpenAI 兼容格式 /chat/completions，支持流式与非流式
# - 由 maas_worker.py 消费（任务类型 maas_generate）
# ---------------------------------------------------------

import json
import os
import requests
from typing import Generator, Optional

from dotenv import load_dotenv

load_dotenv()


def _get_config():
    """读取配置（运行时读取，便于测试与热更新 .env）"""
    return {
        "api_key": os.getenv("TENCENT_MAAS_API_KEY"),
        "base_url": os.getenv("TENCENT_MAAS_BASE_URL", "https://tokenhub.tencentmaas.com/v1").rstrip("/"),
        "model": os.getenv("TENCENT_MAAS_MODEL", "hy4-preview"),
        "timeout": int(os.getenv("TENCENT_MAAS_TIMEOUT", "300")),
        "max_tokens": int(os.getenv("TENCENT_MAAS_MAX_TOKENS", "4096")),
        "temperature": float(os.getenv("TENCENT_MAAS_TEMPERATURE", "0.7")),
    }


def is_configured() -> bool:
    """是否已配置可用的腾讯 MaaS API Key"""
    return bool(_get_config()["api_key"])


def _build_request(prompt: str, model: Optional[str], stream: bool):
    config = _get_config()

    if not config["api_key"]:
        raise ValueError("TENCENT_MAAS_API_KEY 未设置（请检查 .env 文件）")

    url = f"{config['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model or config["model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }
    return url, headers, body, config["timeout"]


def _extract_text(message: dict) -> str:
    """hy4-preview 等推理模型在 content 为空时把正文放在 reasoning_content"""
    content = message.get("content", "")
    return content if content else message.get("reasoning_content", "")


def call_maas(prompt: str, model: str = None, stream: bool = False, task_id: str = None) -> str:
    """
    调用腾讯 MaaS 生成文本

    参数:
        prompt: 提示词
        model: 模型名称（默认取 TENCENT_MAAS_MODEL）
        stream: 是否流式输出
        task_id: 任务 ID，配合 stream=True 时把片段推送到前端

    返回:
        str: 完整的响应文本
    """
    url, headers, body, timeout = _build_request(prompt, model, stream and bool(task_id))

    if stream and task_id:
        return _call_streaming(url, headers, body, timeout, task_id)

    response = requests.post(url, headers=headers, json=body, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"腾讯 MaaS 返回了未知的响应格式: {list(data.keys())}")

    return _extract_text(choices[0].get("message", {}))


def call_maas_stream(prompt: str, model: str = None) -> Generator[str, None, None]:
    """流式调用腾讯 MaaS，逐块返回文本"""
    url, headers, body, timeout = _build_request(prompt, model, True)

    with requests.post(url, headers=headers, json=body, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        for token in _iter_text(response):
            yield token


def _iter_text(response) -> Generator[str, None, None]:
    """产出正文片段；推理内容先缓存，仅在全程无正文时作为兜底输出"""
    reasoning = []
    saw_content = False

    for kind, text in _iter_deltas(response):
        if kind == "content":
            saw_content = True
            yield text
        else:
            reasoning.append(text)

    if not saw_content and reasoning:
        yield "".join(reasoning)


def _iter_deltas(response) -> Generator[tuple, None, None]:
    """解析 SSE 数据流，逐个产出 (类型, 文本) 片段"""
    for line in response.iter_lines():
        if not line:
            continue

        line_str = line.decode("utf-8")
        if not line_str.startswith("data: "):
            continue

        data_str = line_str[6:]
        if data_str == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        choices = chunk.get("choices") or []
        if not choices:
            continue

        delta = choices[0].get("delta", {})
        if delta.get("content"):
            yield "content", delta["content"]
        elif delta.get("reasoning_content"):
            yield "reasoning", delta["reasoning_content"]


def _call_streaming(url: str, headers: dict, body: dict, timeout: int, task_id: str) -> str:
    """流式调用并把片段实时推送到前端"""
    try:
        from worker_config import stream_start, stream_chunk, stream_end
    except ImportError:
        from ...worker_config import stream_start, stream_chunk, stream_end

    full_response = ""

    try:
        stream_start(task_id, title="腾讯 MaaS 正在生成...")

        with requests.post(url, headers=headers, json=body, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            for token in _iter_text(response):
                full_response += token
                stream_chunk(task_id, token)

        stream_end(task_id)
        return full_response

    except Exception as e:
        try:
            from worker_config import stream_error
        except ImportError:
            from ...worker_config import stream_error
        stream_error(task_id, f"流式输出失败: {str(e)}")
        raise


def test_connection() -> bool:
    """测试腾讯 MaaS 连通性"""
    try:
        text = call_maas("ping")
        print(f"✅ 腾讯 MaaS 连接成功，响应: {text[:50]}")
        return True
    except Exception as e:
        print(f"❌ 腾讯 MaaS 连接失败: {e}")
        return False


if __name__ == "__main__":
    test_connection()
