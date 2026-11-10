import os
import httpx
from abc import ABC, abstractmethod
from typing import Any, Optional


class ProviderError(Exception):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class BaseModelProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        pass


class MockProvider(BaseModelProvider):
    async def generate(
        self,
        prompt: str,
        model: str = "mock",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "response": f"[Mock response for: {prompt[:50]}]",
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": 20},
        }


class OpenAICompatibleProvider(BaseModelProvider):
    def __init__(
        self,
        api_key_env: str,
        base_url: str,
        timeout_env: str = "PROVIDER_TIMEOUT",
    ):
        self.api_key = os.getenv(api_key_env)
        self.base_url = base_url
        self.timeout = float(os.getenv(timeout_env, "30"))

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderAuthError(
                f"API key not set for {self.base_url}"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException:
            raise ProviderTimeoutError(
                f"Provider timed out after {self.timeout}s"
            )

        return self._parse_response(resp, model)

    def _parse_response(self, resp: httpx.Response, model: str) -> dict[str, Any]:
        if resp.status_code in (401, 403):
            raise ProviderAuthError(
                f"Auth error: {resp.status_code} {resp.text[:200]}"
            )
        if resp.status_code == 429:
            raise ProviderRateLimitError("Rate limit exceeded")
        if resp.status_code != 200:
            raise ProviderError(
                f"Provider returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        return {
            "model": data.get("model", model),
            "response": data["choices"][0]["message"]["content"],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
            },
        }


class QwenProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="DASHSCOPE_API_KEY",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )


class QwenAccountAProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="DASHSCOPE_KEY_ACCOUNT_A",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self):
        maas_url = os.getenv("DEEPSEEK_MAAS_BASE_URL", "")
        if maas_url:
            super().__init__(
                api_key_env="DEEPSEEK_MAAS_API_KEY",
                base_url=maas_url,
            )
        else:
            super().__init__(
                api_key_env="VOLC_DEEPSEEK_API_KEY",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
            )


class VolcProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="VOLC_API_KEY",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )


class VolcDeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="VOLC_DEEPSEEK_API_KEY",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )


class ModelScopeProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="MODELSCOPE_API_KEY",
            base_url="https://api-inference.modelscope.cn/v1",
        )


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
        )


class GeminiProvider(BaseModelProvider):
    def __init__(self):
        self.proxy_url = os.getenv("GEMINI_PROXY_URL")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.timeout = float(os.getenv("PROVIDER_TIMEOUT", "30"))

    async def generate(
        self,
        prompt: str,
        model: str = "gemini-3.5-flash",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        if self.proxy_url:
            return await self._generate_via_proxy(
                prompt, model, temperature, max_tokens
            )
        if not self.api_key:
            raise ProviderAuthError("GEMINI_API_KEY is not set")
        raise NotImplementedError("Direct Gemini API not yet implemented")

    async def _generate_via_proxy(
        self, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        provider = OpenAICompatibleProvider(
            api_key_env="GEMINI_API_KEY",
            base_url=f"{self.proxy_url}/v1",
            timeout_env="PROVIDER_TIMEOUT",
        )
        provider.api_key = "proxy"
        return await provider.generate(prompt, model, temperature, max_tokens)


def get_model_provider(model_name: str) -> BaseModelProvider:
    registry = {
        "Mock": MockProvider(),
        "Qwen": QwenProvider(),
        "QwenAccountA": QwenAccountAProvider(),
        "DeepSeek": DeepSeekProvider(),
        "Volc": VolcProvider(),
        "VolcDeepSeek": VolcDeepSeekProvider(),
        "ModelScope": ModelScopeProvider(),
        "OpenAI": OpenAIProvider(),
        "Gemini": GeminiProvider(),
    }
    if model_name in registry:
        return registry[model_name]
    raise ProviderError(f"Unknown model: {model_name}")