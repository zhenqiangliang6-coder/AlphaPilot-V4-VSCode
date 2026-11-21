# -*- coding: utf-8 -*-
# providers/maas_client.py
# ---------------------------------------------------------
# 跨 Provider 降级链的 OpenAI 兼容兜底适配器
#
# 背景（2026-11-18 v59 全链失败复盘）：
#   v59 一遍 4 failed 的根因不是代码回归，而是「当日额度耗尽」——
#   ModelScope 魔粒 429 耗尽、DashScope qwen3.7-max-preview 403 免费额度
#   耗尽。此前 qwen_api 的跨 Provider 降级是硬编码一跳（任意 Provider →
#   QwenClient），没有后续链路，Qwen 也 403 时整条链直接断掉。
#
# 本版策略：把已探测 200 OK 的备用 Provider 逐个接入，组成有序多级降级链
#   modelscope → qwen(dashscope) → deepseek_maas → tencent_maas → volc_deepseek
#   每个 Provider 一个 Key + 一组模型链，独立接入 provider_health 带 TTL 冷却：
#   * 429 insufficient balance → QUOTA 冷却（可恢复，到期自动半开回归）；
#   * 401 / 402 / 403 quota → FATAL 永久熔断。
#   冷却期 call_stream 第一块直接返回失败文本，qwen_api 的链循环据此跳到
#   下一 Provider，绝不「每步白撞一次 429/403」；额度恢复后链首自动回归。
#
# 契约边界：密钥只从 os.environ 读取，绝不落盘。
# ---------------------------------------------------------

import json
import os
import time
from pathlib import Path
from typing import Generator

import requests
from dotenv import load_dotenv

from ..step_executor.interfaces import LLMClient
from ....provider_health import is_open as _provider_circuit_open
from ....provider_health import reason as _provider_circuit_reason
from ....provider_health import trip_if_fatal as _trip_if_fatal

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

_NETWORK_RETRY_MAX = 2
_NETWORK_RETRY_DELAYS = [1, 2]

# 与 qwen_client / modelscope_client 共用同一组墙钟环境变量口径，超时抛错
# → 交回链循环降级到下一 Provider（FAIL-CLOSED）。
_DEFAULT_STREAM_WALL_TIMEOUT_SEC = 240.0
_DEFAULT_STREAM_FIRST_CONTENT_SEC = 45.0


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.getenv(name, "").strip() or default))
    except (ValueError, AttributeError):
        return default


def _is_network_error(exc: Exception) -> bool:
    """判断是否为瞬时网络错误（值得在同模型下重试）。"""
    name = type(exc).__name__
    if name in ("SSLEOFError", "SSLError", "ReadTimeout", "ConnectionError",
                "ConnectionResetError", "RemoteDisconnected", "ProtocolError"):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("timed out", "timeout", "connection", "refused"))


class OpenAICompatChainClient(LLMClient):
    """通用 OpenAI 兼容流式客户端（跨 Provider 降级链兜底用）。"""

    def __init__(self, provider_key, api_key_env, base_url_env, model_envs,
                 default_base_url, default_models):
        self._provider_key = provider_key
        self._api_key = (os.getenv(api_key_env) or "").strip()
        base = (os.getenv(base_url_env) or default_base_url).strip().rstrip("/")
        self._url = f"{base}/chat/completions"
        models = []
        for env in model_envs:
            val = (os.getenv(env) or "").strip()
            if val and val not in models:
                models.append(val)
        self._models = models or list(default_models)
        self._session = requests.Session()
        self._session.trust_env = False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract(data: dict) -> str:
        """只认 content，绝不把 reasoning_content（思维链）混进正文。"""
        choices = data.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        message = first.get("message") or {}
        delta = first.get("delta") or {}
        return message.get("content") or delta.get("content") or ""

    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        if _provider_circuit_open(self._provider_key):
            raise RuntimeError(
                f"{self._provider_key} 暂时不可用（熔断/额度冷却中）: "
                f"{_provider_circuit_reason(self._provider_key)}"
            )
        if not self._api_key:
            raise RuntimeError(f"{self._provider_key} API Key 未设置")
        chunks = []
        for chunk in self.call_stream(prompt, temperature):
            if "[API 调用失败" in chunk:
                raise RuntimeError(chunk.strip())
            chunks.append(chunk)
        text = "".join(chunks)
        if not text.strip():
            raise RuntimeError(f"{self._provider_key} 返回空内容")
        return text

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if _provider_circuit_open(self._provider_key):
            yield (f"\n\n[API 调用失败: {self._provider_key} 暂时不可用"
                   f"（熔断/额度冷却中） - {_provider_circuit_reason(self._provider_key)}]")
            return
        if not self._api_key:
            yield f"\n\n[API 调用失败: {self._provider_key} API Key 未设置]"
            return

        wall = _env_float("QWEN_STREAM_WALL_TIMEOUT_SEC", _DEFAULT_STREAM_WALL_TIMEOUT_SEC)
        first_bound = _env_float("QWEN_STREAM_FIRST_CONTENT_SEC", _DEFAULT_STREAM_FIRST_CONTENT_SEC)
        last_error = None
        for model in self._models:
            if _provider_circuit_open(self._provider_key):
                break
            for attempt in range(_NETWORK_RETRY_MAX + 1):
                response = None
                try:
                    response = self._session.post(
                        self._url,
                        headers=self._headers(),
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": temperature,
                            "stream": True,
                        },
                        timeout=(10, 45),
                        stream=True,
                        proxies={},
                    )
                except requests.RequestException as e:
                    last_error = e
                    if attempt < _NETWORK_RETRY_MAX and _is_network_error(e):
                        time.sleep(_NETWORK_RETRY_DELAYS[attempt])
                        continue
                    break
                except Exception as e:
                    last_error = e
                    break

                if _trip_if_fatal(self._provider_key, response):
                    try:
                        response.close()
                    except Exception:
                        pass
                    last_error = RuntimeError(f"{model} 额度/鉴权不可用，已进入熔断/冷却")
                    break

                try:
                    response.raise_for_status()
                except Exception as e:
                    last_error = e
                    try:
                        response.close()
                    except Exception:
                        pass
                    break

                response.encoding = "utf-8"
                started = time.monotonic()
                produced = False
                timed_out = False
                try:
                    for line in response.iter_lines(decode_unicode=True):
                        elapsed = time.monotonic() - started
                        if elapsed > wall or (not produced and elapsed > first_bound):
                            timed_out = True
                            break
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = self._extract(json.loads(data_str))
                                if chunk:
                                    produced = True
                                    yield chunk
                            except json.JSONDecodeError:
                                continue
                finally:
                    try:
                        response.close()
                    except Exception:
                        pass

                if timed_out:
                    last_error = TimeoutError(
                        f"{model} 流式生成超上界 (wall={wall:.0f}s/first={first_bound:.0f}s)"
                    )
                    break
                if not produced:
                    last_error = RuntimeError(f"{model} 流结束但零正文")
                    break
                if model != self._models[0]:
                    print(f"[{self._provider_key}] 降级模型 {model} 调用成功")
                return
        yield f"\n\n[API 调用失败: {self._provider_key} 所有模型不可用 - {last_error}]"


class DeepSeekMaaSClient(OpenAICompatChainClient):
    """DeepSeek 经阿里云 MaaS（OpenAI 兼容，已探测 200 OK）。"""

    def __init__(self):
        super().__init__(
            provider_key="deepseek_maas",
            api_key_env="DEEPSEEK_MAAS_API_KEY",
            base_url_env="DEEPSEEK_MAAS_BASE_URL",
            model_envs=("DEEPSEEK_MAAS_MODEL", "DEEPSEEK_MAAS_FALLBACK_MODEL"),
            default_base_url="https://llm-ithsvxlz15kgi8lc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            default_models=("deepseek-v4-pro-0813",),
        )


class TencentMaaSClient(OpenAICompatChainClient):
    """腾讯 MaaS（混元，OpenAI 兼容，已探测 200 OK）。"""

    def __init__(self):
        super().__init__(
            provider_key="tencent_maas",
            api_key_env="TENCENT_MAAS_API_KEY",
            base_url_env="TENCENT_MAAS_BASE_URL",
            model_envs=("TENCENT_MAAS_MODEL", "TENCENT_MAAS_FALLBACK_MODEL"),
            default_base_url="https://tokenhub.tencentmaas.com/v1",
            default_models=("deepseek-v4.1-flash",),
        )


class VolcDeepSeekClient(OpenAICompatChainClient):
    """火山引擎 DeepSeek（OpenAI 兼容，已探测 200 OK）。"""

    def __init__(self):
        super().__init__(
            provider_key="volc_deepseek",
            api_key_env="VOLC_DEEPSEEK_API_KEY",
            base_url_env="VOLC_DEEPSEEK_BASE_URL",
            model_envs=("VOLC_DEEPSEEK_MODEL",),
            default_base_url="https://ark.cn-beijing.volces.com/api/v3",
            default_models=("deepseek-v3-250324",),
        )