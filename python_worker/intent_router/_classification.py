# -*- coding: utf-8 -*-
# intent_router._classification — LLM 语义分类引擎
# 从 intent_router.py 拆分而来

import json
import os
import time
from typing import Dict, List

from ._data import ALL_INTENTS, ALL_TARGET_TYPES, LITE_CLASSIFY_PROMPT

try:  # 包内导入（python_worker.intent_router）与顶层导入（intent_router）都支持
    from ..provider_health import is_open as _provider_circuit_open
    from ..provider_health import trip_if_fatal as _trip_if_fatal
except ImportError:  # pragma: no cover - 兼容 sys.path 直接指向 python_worker 的启动方式
    from provider_health import is_open as _provider_circuit_open
    from provider_health import trip_if_fatal as _trip_if_fatal


def _get_env(key: str, default: str = "") -> str:
    try:
        from worker_config import __dict__ as cfg
        return cfg.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)


_CHAIN_CACHE = None
_CHAIN_CACHE_TS = 0
_CHAIN_CACHE_TTL = 3600


def _resolve_modelscope_classify_chain() -> List[str]:
    """
    Provider-aware: ModelScope 意图分类模型链。

    ModelScope 不需要 DashScope 探测，使用固定的可用模型链。
    该链与 modelscope_client.py 的降级链对齐。
    """
    env_model = os.environ.get("MODELSCOPE_CLASSIFY_MODEL", "").strip()
    if env_model:
        return [env_model]

    chain = os.environ.get("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next").strip()
    return [chain, "Qwen/Qwen3.8-27B"]


def _main_chain_candidates() -> List[str]:
    """主执行链配置的模型（与 qwen_model_probe.get_text_fallback_chain 同源）。

    只做「候选补充」，不参与排序决策：分类器必须与执行链共用同一组已配置
    模型，否则执行链能降级成功、分类器却因单点模型耗尽而直接放弃。
    """
    out: List[str] = []
    for key in ("QWEN_MODEL", "QWEN_FAST_MODEL",
                "QWEN_FALLBACK_1", "QWEN_FALLBACK_2", "QWEN_FALLBACK_3"):
        # _get_env 同时覆盖 worker_config 模块字典与 os.environ 两种 .env
        # 加载方式；只查 os.environ 会在「配置未注入进程环境」时补空链。
        model = str(_get_env(key, "") or "").strip()
        if model and model not in out:
            out.append(model)
    return out


def _resolve_qwen_classify_chain() -> List[str]:
    """从 Qwen 模型探测中动态获取可用的文本模型降级链。

    绝不硬编码任何模型名。每次调用均从探针缓存读取最新的
    /v1/models + 可用性验证结果，构造真实验证的降级链。

    优先级：
      1. INTENT_CLASSIFY_MODEL 环境变量（显式指定，作为**链首**）
      2. 模型探测 text 链（API 返回 + 可用性验证的全部文本模型）
      3. 模型探测 best_text（至少一个经过验证的模型）
      4. QWEN_MODEL 环境变量
      5. 绝对兜底（单模型）

    G10.23：显式配置只表达「首选」，**不再独占整条链**。
    shopflow_v4_1 实证：`INTENT_CLASSIFY_MODEL=qwen-plus` 当日免费额度耗尽
    (403)，旧实现 `if env_model: return [env_model]` 让分类器没有第二个
    模型可试，直接降级 Regex；R9 的「枚举值级联替换」题面没命中任何正则，
    被判成 chat（执行链 analyze→workspace→plan→respond），零 FileOps、
    无授权记录，却写回 outcome=success，质量+治理双红。
    现在链首仍是首选模型，其后接探测链，并始终补齐主执行链配置模型，
    链首失败会自动落到下一个可用模型（当时是 qwen3.5-plus）。
    """
    global _CHAIN_CACHE, _CHAIN_CACHE_TS

    env_model = os.environ.get("INTENT_CLASSIFY_MODEL", "").strip()

    def remember(chain: List[str]) -> List[str]:
        """写缓存：去空、补主链候选、把首选放链首（其余保序去重）。"""
        global _CHAIN_CACHE, _CHAIN_CACHE_TS
        base = [m for m in chain if m]
        if env_model:
            # 只有「显式指定了单点模型」时才补候选链 —— 未指定时原本就
            # 使用完整探测链，保持既有语义与既有契约断言不变。
            for m in _main_chain_candidates():
                if m not in base:
                    base.append(m)
            ordered = [env_model] + [m for m in base if m != env_model]
        else:
            ordered = base
        if not ordered:
            ordered = ["qwen3.8-max"]
        _CHAIN_CACHE = ordered
        _CHAIN_CACHE_TS = time.time()
        return ordered

    # ⭐ G10: Provider 感知 — LLM_PROVIDER=modelscope 时走 ModelScope 模型链，不探测 DashScope
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    # 熔断/额度冷却期间，意图分类旁路也必须绕开 ModelScope，否则每个任务
    # 都会再撞一次暂时不可用的上游。冷却到期后会自动半开恢复。
    if provider == "modelscope" and not _provider_circuit_open("modelscope"):
        return remember(_resolve_modelscope_classify_chain())

    now = time.time()
    # 熔断打开时，缓存里可能还是熔断前写入的 ModelScope 模型链；
    # 拿魔搭模型名去打 DashScope 必然失败，必须强制重新解析可用链。
    # 首选模型若发生变化（配置热变更 / 测试注入），缓存同样必须失效。
    preferred_unchanged = (not env_model or
                           (_CHAIN_CACHE and _CHAIN_CACHE[0] == env_model))
    if (_CHAIN_CACHE is not None and (now - _CHAIN_CACHE_TS) < _CHAIN_CACHE_TTL
            and not _provider_circuit_open("modelscope")
            and preferred_unchanged):
        return _CHAIN_CACHE

    try:
        try:
            from ..agents.qwen.qwen_model_probe import probe_qwen_models
        except ImportError:
            from agents.qwen.qwen_model_probe import probe_qwen_models

        probed = probe_qwen_models()
        text_chain = probed.get("text", [])
        if text_chain:
            return remember(text_chain)

        best = probed.get("best_text", "")
        if best:
            return remember([best])
    except Exception as e:
        print(f"\n⚠️ [Intent Router] 模型探测失败: {type(e).__name__}: {e}")

    qwen_model = os.environ.get("QWEN_MODEL", "").strip()
    if qwen_model:
        return remember([qwen_model])

    print("⚠️ [Intent Router] 无法探测模型池，使用绝对兜底")
    return remember(["qwen3.8-max"])


def llm_classify(prompt: str, model_name: str = "qwen") -> Dict:
    full_prompt = LITE_CLASSIFY_PROMPT + "\n用户：" + prompt
    max_timeout = int(os.environ.get("LLM_CLASSIFY_TIMEOUT", "60"))

    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if provider == "modelscope" and _provider_circuit_open("modelscope"):
        provider = "qwen"  # 熔断：分类改走 DashScope
    actual_model_name = model_name
    if model_name == "qwen" and provider == "modelscope":
        actual_model_name = "modelscope"

    if model_name == "qwen":
        chain = _resolve_qwen_classify_chain()
    elif actual_model_name == "modelscope":
        chain = _resolve_modelscope_classify_chain()
    else:
        chain = [None]

    last_error = None
    for idx, model in enumerate(chain):
        try:
            result_text = call_provider_for_classify(
                full_prompt, actual_model_name, model_override=model, max_timeout=max_timeout
            )
        except Exception as e:
            last_error = e
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 调用异常，尝试下一个...")
            continue

        if not result_text:
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 不可用，尝试下一个...")
            continue

        if idx == 0:
            print(f"   ✅ [Intent Router] 模型 '{model}' 分类成功")

        json_text = result_text.strip()
        if json_text.startswith("```"):
            json_text = json_text.split("```")[1]
            if json_text.startswith("json"):
                json_text = json_text[4:]
            json_text = json_text.strip()

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as e:
            if len(chain) > 1:
                print(f"   ⚠️ [Intent Router] 模型 '{model}' 返回非 JSON，尝试下一个...")
            continue

        intent = parsed.get("intent", "")
        target_type = parsed.get("target_type", "none")
        confidence = float(parsed.get("confidence", 0))

        if intent not in ALL_INTENTS:
            continue
        if target_type not in ALL_TARGET_TYPES:
            target_type = "none"

        if idx > 0:
            print(f"   ✅ [Intent Router] 模型 '{model}' 重试成功 (链索引 {idx})")

        return {
            "intent": intent,
            "target_type": target_type,
            "confidence": confidence,
            "reasoning": parsed.get("reasoning", ""),
            "is_compound": parsed.get("is_compound", False),
            "phases": parsed.get("phases", []) if isinstance(parsed.get("phases"), list) else [],
        }

    return None


def get_provider_config(model_name: str) -> Dict:
    model_lower = (model_name or "").lower()

    configs = {
        "qwen": {
            "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "model": "qwen3.8-max",
            "auth_key": "DASHSCOPE_API_KEY",
            "format": "openai",
        },
        "gemini": {
            "url": lambda: f"{_get_env('GEMINI_PROXY_URL', 'http://localhost:8000')}/gemini/v1beta/models/{_get_env('GEMINI_MODEL', 'gemini-3.5-flash')}:generateContent",
            "model": lambda: _get_env("GEMINI_MODEL", "gemini-3.5-flash"),
            "auth_key": None,
            "format": "gemini",
        },
        "modelscope": {
            "url": "https://api-inference.modelscope.cn/v1/chat/completions",
            "model": lambda: _get_env("MODELSCOPE_MODEL", "Qwen/Qwen3.8-Flash-Next"),
            "auth_key": "MODELSCOPE_API_KEY",
            "format": "openai",
        },
        "maas": {
            "url": lambda: (_get_env("TENCENT_MAAS_BASE_URL", _get_env("MAAS_URL", "https://tokenhub.tencentmaas.com/v1")).rstrip("/") + "/chat/completions"),
            "model": lambda: _get_env("TENCENT_MAAS_MODEL", "default"),
            "auth_key": "TENCENT_MAAS_API_KEY",
            "alt_auth_key": "TENCENT_MaaS_API_KEY",
            "format": "openai",
        },
        "local": {
            "url": lambda: (_get_env("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"),
            "model": lambda: _get_env("LOCAL_LLM_MODEL", "local-model"),
            "auth_key": None,
            "format": "openai",
        },
    }
    return configs.get(model_lower, configs["qwen"])


def call_provider_for_classify(prompt: str, model_name: str, model_override: str = None, max_timeout: int = 5) -> str:
    import requests
    # 熔断/额度冷却期间不再对暂时不可用的上游发分类请求
    if model_name == "modelscope" and _provider_circuit_open("modelscope"):
        return ""
    # 分类请求直连上游，不继承 HTTP_PROXY/HTTPS_PROXY 环境变量：
    # 宿主注入的会话代理对 ModelScope 域名并不可靠，会拖垮意图识别。
    session = requests.Session()
    session.trust_env = False
    cfg = get_provider_config(model_name)

    api_format = cfg.get("format", "openai")
    model = model_override if model_override else (cfg["model"]() if callable(cfg["model"]) else cfg["model"])
    url = cfg["url"]() if callable(cfg["url"]) else cfg["url"]

    auth_key = None
    if cfg.get("auth_key"):
        auth_key = _get_env(cfg["auth_key"], "")
    if not auth_key and cfg.get("alt_auth_key"):
        auth_key = _get_env(cfg["alt_auth_key"], "")

    try:
        if api_format == "dashscope":
            if not auth_key:
                return ""
            headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
            body = {
                "model": model,
                "input": {"prompt": prompt},
                "parameters": {"temperature": 0, "result_format": "message", "max_tokens": 1024},
            }
            r = session.post(url, headers=headers, json=body, timeout=max_timeout)
            r.raise_for_status()
            data = r.json()
            output = data.get("output", {})
            if "choices" in output:
                choices = output.get("choices", [])
                if choices and isinstance(choices, list):
                    return choices[0].get("message", {}).get("content", "")
            return output.get("text", "")

        elif api_format == "gemini":
            headers = {"Content-Type": "application/json"}
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
                "thinkingConfig": {"thinkingBudget": 0},
            }
            r = session.post(url, headers=headers, json=body, timeout=max_timeout)
            r.raise_for_status()
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {}) or {}
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""

        elif api_format == "openai":
            if auth_key:
                headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
            else:
                headers = {"Content-Type": "application/json"}
            prompt_len = len(prompt)
            if prompt_len < 1000:
                adaptive_tokens = 512
            elif prompt_len < 3000:
                adaptive_tokens = 1024
            else:
                adaptive_tokens = 2048
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an intent classifier. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": adaptive_tokens,
                "response_format": {"type": "json_object"},
            }
            r = session.post(url, headers=headers, json=body, timeout=max_timeout)
            if r.status_code == 400:
                try:
                    err_data = r.json()
                    err_msg_lower = str(err_data).lower()
                except Exception:
                    err_msg_lower = r.text.lower()
                if "response_format" in err_msg_lower or "json_object" in err_msg_lower:
                    del body["response_format"]
                    r = session.post(url, headers=headers, json=body, timeout=max_timeout)
                    r.raise_for_status()
                else:
                    r.raise_for_status()
            else:
                r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    except Exception as e:
        # ⭐ v4.0: 不再静默吞错——打印诊断信息
        print(f"\n⚠️ [Intent Router] LLM 分类 API 调用失败 ({model_name}/{model}):")
        print(f"   URL: {url}")
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_body = e.response.text[:300] if hasattr(e.response, 'text') else ''
                err_msg += f" | HTTP {e.response.status_code}: {err_body}"
                if model_name == "modelscope" and _trip_if_fatal(
                        "modelscope", e.response):
                    print("   ⛔ [Intent Router] ModelScope 熔断/额度冷却，已标记该 Provider")
            except Exception:
                pass
        print(f"   错误: {err_msg[:500]}")
        return ""