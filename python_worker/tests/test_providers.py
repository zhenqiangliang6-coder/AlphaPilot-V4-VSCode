import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from model_provider.providers import (
    MockProvider,
    QwenProvider,
    BaseModelProvider,
    get_model_provider,
    ProviderError,
    ProviderAuthError,
    ProviderTimeoutError,
    ProviderRateLimitError,
)


class TestMockProvider:
    @pytest.mark.anyio
    async def test_returns_unified_format(self):
        provider = MockProvider()
        result = await provider.generate(prompt="hello", model="mock")

        assert "model" in result
        assert "response" in result
        assert "usage" in result

    @pytest.mark.anyio
    async def test_response_contains_prompt_prefix(self):
        provider = MockProvider()
        result = await provider.generate(prompt="write a poem", model="mock")

        assert "write a poem" in result["response"]

    @pytest.mark.anyio
    async def test_usage_has_token_counts(self):
        provider = MockProvider()
        result = await provider.generate(prompt="one two three", model="mock")

        assert result["usage"]["prompt_tokens"] == 3
        assert result["usage"]["completion_tokens"] == 20

    @pytest.mark.anyio
    async def test_preserves_model_name(self):
        provider = MockProvider()
        result = await provider.generate(prompt="hi", model="custom-model")

        assert result["model"] == "custom-model"

    @pytest.mark.anyio
    async def test_accepts_temperature_and_max_tokens(self):
        provider = MockProvider()
        result = await provider.generate(
            prompt="hi", model="mock", temperature=1.2, max_tokens=512
        )
        assert result["model"] == "mock"


class TestQwenProviderWithoutKey:
    @pytest.mark.anyio
    async def test_raises_auth_error_when_no_api_key(self):
        provider = QwenProvider()
        provider.api_key = None

        with pytest.raises(ProviderAuthError, match="API key not set"):
            await provider.generate(prompt="hi", model="qwen-turbo")


class TestProviderFactory:
    def test_returns_mock_provider(self):
        provider = get_model_provider("Mock")
        assert isinstance(provider, MockProvider)

    def test_returns_qwen_provider(self):
        provider = get_model_provider("Qwen")
        assert isinstance(provider, QwenProvider)

    def test_returns_base_provider_type(self):
        provider = get_model_provider("Mock")
        assert isinstance(provider, BaseModelProvider)

    def test_unknown_model_raises(self):
        with pytest.raises(ProviderError, match="Unknown model"):
            get_model_provider("NonExistentModel")


class TestExceptionHierarchy:
    def test_auth_error_is_provider_error(self):
        assert issubclass(ProviderAuthError, ProviderError)

    def test_timeout_error_is_provider_error(self):
        assert issubclass(ProviderTimeoutError, ProviderError)

    def test_rate_limit_error_is_provider_error(self):
        assert issubclass(ProviderRateLimitError, ProviderError)