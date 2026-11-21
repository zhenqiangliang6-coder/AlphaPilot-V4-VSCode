# -*- coding: utf-8 -*-
# providers/__init__.py
# ---------------------------------------------------------
# AlphaPilot 统一 LLM Provider 注册中心
# - 所有 Provider 平级接入，实现 LLMClient 接口
# - 通过环境变量 LLM_PROVIDER 动态切换
# - 零硬编码，纯配置驱动
# ---------------------------------------------------------

import os
from typing import Optional
from ..step_executor.interfaces import LLMClient

_PROVIDER_MAP = {
    "modelscope": "ModelScopeClient",
    "qwen": "QwenClient",
    "deepseek": "DeepSeekClient",
    "deepseek_maas": "DeepSeekMaaSClient",
    "tencent_maas": "TencentMaaSClient",
    "volc_deepseek": "VolcDeepSeekClient",
    "openai": "OpenAICompatibleClient",
    "local": "OpenAICompatibleClient",
}


def get_llm_client(provider: str = None) -> LLMClient:
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "qwen").lower().strip()

    client_name = _PROVIDER_MAP.get(provider)
    if client_name is None:
        raise ValueError(
            f"不支持的 LLM Provider: '{provider}'，可选值: {list(_PROVIDER_MAP.keys())}"
        )

    if client_name == "ModelScopeClient":
        from .modelscope_client import ModelScopeClient
        return ModelScopeClient()
    elif client_name == "QwenClient":
        from .qwen_client import QwenClient
        return QwenClient()
    elif client_name == "DeepSeekClient":
        from .deepseek_client import DeepSeekClient
        return DeepSeekClient()
    elif client_name == "DeepSeekMaaSClient":
        from .maas_client import DeepSeekMaaSClient
        return DeepSeekMaaSClient()
    elif client_name == "TencentMaaSClient":
        from .maas_client import TencentMaaSClient
        return TencentMaaSClient()
    elif client_name == "VolcDeepSeekClient":
        from .maas_client import VolcDeepSeekClient
        return VolcDeepSeekClient()
    elif client_name == "OpenAICompatibleClient":
        from .openai_compatible_client import OpenAICompatibleClient
        return OpenAICompatibleClient()

    raise ValueError(f"Provider '{provider}' 已映射到 '{client_name}'，但未实现")


def get_default_provider() -> str:
    return os.getenv("LLM_PROVIDER", "qwen").lower().strip()


_CACHED_CLIENT: Optional[LLMClient] = None


def get_cached_llm_client(provider: str = None) -> LLMClient:
    global _CACHED_CLIENT
    if _CACHED_CLIENT is None:
        _CACHED_CLIENT = get_llm_client(provider)
    return _CACHED_CLIENT


def reset_client_cache():
    global _CACHED_CLIENT
    _CACHED_CLIENT = None