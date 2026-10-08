# -*- coding: utf-8 -*-
# test_api_keys.py
# ---------------------------------------------------------
# 顶级专家级别 API 密钥验证脚本
# - 测试 ModelScope 和 MaaS API 密钥的真实有效性
# - 验证模型调用是否能正常返回结果
# - 提供详细的诊断信息
# ---------------------------------------------------------

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


def _report_response(response, provider, model):
    if response.ok:
        try:
            data = response.json()
        except ValueError:
            print(f"{provider} / {model}: HTTP {response.status_code}, invalid JSON response")
            return False

        if data.get("choices"):
            print(f"{provider} / {model}: available (HTTP {response.status_code})")
            return True

        print(f"{provider} / {model}: HTTP {response.status_code}, response has no choices")
        return False

    if response.status_code in (401, 403):
        reason = "authentication or permission rejected"
    elif response.status_code == 404:
        reason = "endpoint or model not found"
    elif response.status_code == 429:
        reason = "rate limit or quota exceeded"
    elif response.status_code < 500:
        reason = "request or model configuration rejected"
    else:
        reason = "provider server error"

    print(f"{provider} / {model}: unavailable (HTTP {response.status_code}: {reason})")
    return False

def test_modelscope_api():
    """
    测试 ModelScope API 密钥和模型可用性
    """
    print("=" * 60)
    api_key = os.getenv("MODELSCOPE_API_KEY")
    if not api_key:
        print("ModelScope: MODELSCOPE_API_KEY is not configured")
        return False

    configured_model = os.getenv("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next")
    models_to_test = list(dict.fromkeys([
        configured_model,
        "deepseek-ai/DeepSeek-V4-Flash-Vision-Exp",
        "Qwen/Qwen3.8-Flash-Next",
        "deepseek-ai/DeepSeek-V4.1-Flash",
        "Qwen/Qwen3.8-27B",
    ]))
    api_base = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1").rstrip("/")
    api_url = api_base if api_base.endswith("/chat/completions") else f"{api_base}/chat/completions"

    for model in models_to_test:
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": "Reply with OK."}
                ],
                "max_tokens": 10
            }

            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=45
            )
            if _report_response(response, "ModelScope", model):
                return True
            if response.status_code in (401, 403, 429):
                return False
        except requests.RequestException as exc:
            print(f"ModelScope / {model}: request failed ({type(exc).__name__})")

    return False


def test_maas_api():
    """
    测试腾讯 MaaS API 密钥和模型可用性
    """
    api_key = os.getenv("TENCENT_MAAS_API_KEY") or os.getenv("TENCENT_MaaS_API_KEY")
    if not api_key:
        print("MaaS: TENCENT_MAAS_API_KEY is not configured")
        return False

    model = os.getenv("TENCENT_MAAS_MODEL", os.getenv("MAAS_MODEL", "hy4-preview"))
    api_base = os.getenv("TENCENT_MAAS_BASE_URL", "https://tokenhub.tencentmaas.com/v1").rstrip("/")
    api_url = api_base if api_base.endswith("/chat/completions") else f"{api_base}/chat/completions"

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Reply with OK."}
            ],
            "max_tokens": 10
        }

        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=45
        )
        return _report_response(response, "MaaS", model)
    except requests.RequestException as exc:
        print(f"MaaS / {model}: request failed ({type(exc).__name__})")

    return False


def main():
    env_path = Path(__file__).with_name('.env')
    if not env_path.exists():
        print("Missing python_worker/.env; configure the model keys before testing")
        return

    modelscope_ok = test_modelscope_api()
    maas_ok = test_maas_api()
    print(f"Summary: ModelScope={'OK' if modelscope_ok else 'FAILED'}, MaaS={'OK' if maas_ok else 'FAILED'}")


if __name__ == "__main__":
    main()
