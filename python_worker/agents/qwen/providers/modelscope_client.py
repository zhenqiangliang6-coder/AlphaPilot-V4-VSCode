# -*- coding: utf-8 -*-
# providers/modelscope_client.py
# ---------------------------------------------------------
# ModelScope (魔搭) LLMClient 适配器
#
# 2026-11-14 事后核查纠错（重要）：
#   ModelScope API-Inference 是**免费**的开发者服务，用「魔粒」积分抵扣调用
#   （轻量 0.5 / 主流 1 / 旗舰 2 魔粒每次），每日登录发放 200 魔粒 + 绑定
#   阿里云 50 魔粒，短期魔粒 24h 过期、每日 0 点（UTC+8）重置。
#   `429 insufficient balance` = **免费魔粒额度不足**，不是账户欠费，
#   也没有充值入口。社区实测还记载：突发/单分钟限流会把 429 误报为
#   `insufficient balance`。两者都可恢复。
#   旧版把它当成「账户级不可恢复」永久熔断（进程内不恢复），是方向性错误。
#
# 本版策略：
#   * 429 balance → 先做 1 次 2s 退避验证（排除限流误报）；
#     两次都失败才进入 provider_health 的 **带 TTL 冷却**，到期自动半开。
#   * 冷却期间停止遍历 6 个降级模型（额度耗尽时换模型无意义），
#     由 qwen_api 跨 Provider 降级到 DashScope 接管。
#   * 401/402/403 quota 才是真不可恢复，永久熔断。
#
# 契约边界：密钥只从 os.environ 读取，绝不落盘。
# ---------------------------------------------------------

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

# 429 insufficient balance 有可能是「单分钟限流被误报成余额不足」。
# 按社区实测建议做 1 次短退避验证：自愈了就继续用，没自愈才冷却。
# 用环境变量可关闭（MODELSCOPE_QUOTA_VERIFY=0），便于离线契约测试。
_QUOTA_VERIFY_DELAY_SEC = 2.0
_QUOTA_VERIFY_MAX = 1

# ModelScope 深度思考关闭参数（开源 Qwen3 官方 chat_template_kwargs 口径）
_THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}

# 代理熔断：MODELSCOPE_PROXY_URL 只是可选加速项，不是必需组件。
# 一旦探测到不可用，冷却期内不再重复尝试，避免每次 LLM 调用都先白等一次连接。
# G10.29：旧实现是进程内永久布尔，一次 DNS 抖动就永远放弃代理；改为
# 带 TTL 的冷却（默认 300s），到期自动半开，长驻 Worker 可自愈。
_PROXY_CIRCUIT_OPENED_AT = None
_DEFAULT_PROXY_COOLDOWN_SEC = 300.0

# G10.28: 多账号 key 池。魔搭免费魔粒按账号独立计量，单 key 耗尽时
# 旧实现直接熔断整个 Provider，把「一个账号没额度」误判成「平台不可用」。
# 池内顺序即优先级；一旦切到后续 key，本进程后续调用都沿用该 key，
# 直到它也耗尽（进程重启后回到链首，届时额度可能已恢复）。
_KEY_ENV_NAMES = (
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_API_KEY_A",
    "MODELSCOPE_API_KEY_B",
    "MODELSCOPE_API_KEY_C",
)


def _proxy_cooldown_sec() -> float:
    raw = (os.getenv("MODELSCOPE_PROXY_COOLDOWN_SEC") or "").strip()
    if not raw:
        return _DEFAULT_PROXY_COOLDOWN_SEC
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_PROXY_COOLDOWN_SEC


def _proxy_circuit_open() -> bool:
    """代理是否仍在熔断冷却期；到期自动半开。"""
    global _PROXY_CIRCUIT_OPENED_AT
    if _PROXY_CIRCUIT_OPENED_AT is None:
        return False
    if time.monotonic() - _PROXY_CIRCUIT_OPENED_AT >= _proxy_cooldown_sec():
        _PROXY_CIRCUIT_OPENED_AT = None
        print("[ModelScope] 代理熔断冷却到期，重新纳入路径候选")
        return False
    return True


def _open_proxy_circuit():
    global _PROXY_CIRCUIT_OPENED_AT
    _PROXY_CIRCUIT_OPENED_AT = time.monotonic()


def _is_quota_429(response) -> bool:
    """是否为「免费魔粒额度不足」型 429（可能只是限流误报）。"""
    try:
        if response.status_code != 429:
            return False
        low = (response.text or "").lower()
        return ("balance" in low or "insufficient_quota" in low)
    except Exception:
        return False


def _quota_verify_enabled() -> bool:
    return (os.getenv("MODELSCOPE_QUOTA_VERIFY", "1") or "1").strip() != "0"


def _maybe_trip_account_circuit(response) -> bool:
    """按错误性质标记 Provider 状态，返回是否触发了熔断/冷却。

    * 401 / 402 / 403 quota → 真鉴权/付费故障，永久熔断（FATAL）。
    * 429 insufficient balance → 免费魔粒额度耗尽或限流误报，进入带 TTL 的
      冷却（QUOTA），到期自动半开重试，无需重启 Worker。
    * 普通 429 限流 → 不熔断，交给调用方退避。

    兼容旧函数名与调用点；内部分类由 provider_health.classify_response() 完成。
    """
    return _trip_if_fatal("modelscope", response)


def _verify_quota_response(response, post_fn):
    """429 balance 可能是单分钟限流被误报成「余额不足」。

    退避 2 秒重发一次：恢复了就当瞬时抖动继续用；仍失败才交给
    provider_health 进入带 TTL 的冷却。绝不遍历 6 个降级模型去放大限流。
    """
    if not (_is_quota_429(response) and _quota_verify_enabled()):
        return response
    for _ in range(_QUOTA_VERIFY_MAX):
        time.sleep(_QUOTA_VERIFY_DELAY_SEC)
        try:
            response.close()
        except Exception:
            pass
        try:
            response = post_fn()
        except Exception:
            break
        if not _is_quota_429(response):
            print("[ModelScope] 429 疑似限流误报，退避重试后恢复，继续使用该模型")
            break
    return response


def _is_network_error(exc: Exception) -> bool:
    """判断是否为瞬时网络错误（值得在同模型下换直连路径重试）。"""
    name = type(exc).__name__
    if name in ("SSLEOFError", "SSLError", "ReadTimeout", "ConnectionError",
                "ConnectionResetError", "RemoteDisconnected", "ProtocolError"):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("timed out", "timeout", "connection", "refused"))


class ModelScopeClient(LLMClient):
    def __init__(self):
        keys: list = []
        for name in _KEY_ENV_NAMES:
            val = (os.getenv(name) or "").strip()
            if val and val not in keys:
                keys.append(val)
        self._api_keys = keys
        self._key_index = 0
        # 向后兼容：既有代码读 self._api_key 判断「是否配置」
        self._api_key = keys[0] if keys else ""
        self._base_url = (
            os.getenv("MODELSCOPE_BASE_URL")
            or "https://api-inference.modelscope.cn/v1"
        ).rstrip("/")
        proxy = (os.getenv("MODELSCOPE_PROXY_URL") or "").strip()
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        # 独立 Session：trust_env=False 让 "直连" 真正不经由环境变量代理。
        # 否则 proxies=None 时 requests 仍读 HTTP_PROXY/HTTPS_PROXY，
        # 代理故障会连带打死兜底路径，降级链形同虚设。
        self._session = requests.Session()
        self._session.trust_env = False

    # ------------------------------------------------------------------
    # 模型降级链：MODELSCOPE_MODEL → MODELSCOPE_FALLBACK_1..5
    # ------------------------------------------------------------------
    def _get_chain(self):
        chain = []
        for key in ("MODELSCOPE_MODEL", "MODELSCOPE_FALLBACK_1", "MODELSCOPE_FALLBACK_2",
                    "MODELSCOPE_FALLBACK_3", "MODELSCOPE_FALLBACK_4", "MODELSCOPE_FALLBACK_5"):
            val = (os.getenv(key) or "").strip()
            if val and val not in chain:
                chain.append(val)
        return chain or ["Qwen/Qwen3.8-Flash-Next"]

    @staticmethod
    def _extract_text(data: dict) -> str:
        """提取 OpenAI 兼容响应文本。

        ModelScope API-Inference 非流式响应实测使用 choices[0].delta.content；
        DashScope 兼容 endpoints 使用 choices[0].message.content，两者都兼容。
        """
        choices = data.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        message = first.get("message") or {}
        delta = first.get("delta") or {}
        return message.get("content") or delta.get("content") or ""

    # ------------------------------------------------------------------
    # G10.28: 账号级额度轮换
    # ------------------------------------------------------------------
    def _current_key(self) -> str:
        if not self._api_keys:
            return ""
        return self._api_keys[min(self._key_index, len(self._api_keys) - 1)]

    def _rotate_key(self) -> bool:
        """切到池内下一个 key；已到末尾返回 False（交由上层熔断）。"""
        if self._key_index + 1 >= len(self._api_keys):
            return False
        self._key_index += 1
        self._api_key = self._current_key()
        return True

    def _post(self, model, prompt, temperature, stream, proxies):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        body.update(_THINK_OFF)
        if stream:
            body["stream"] = True
        url = f"{self._base_url}/chat/completions"

        # 只把「429 免费额度耗尽」当作换账号信号；网络错误 / 5xx /
        # 普通限流仍交给既有路径策略与降级链处理，避免放大故障。
        response = None
        for _attempt in range(max(1, len(self._api_keys))):
            headers = {
                "Authorization": f"Bearer {self._current_key()}",
                "Content-Type": "application/json",
            }
            response = self._session.post(
                url, headers=headers, json=body,
                timeout=(15, 180), stream=stream, proxies=proxies or {},
            )
            if _is_quota_429(response) and self._rotate_key():
                try:
                    response.close()
                except Exception:
                    pass
                print(
                    f"[ModelScope] 当前账号额度耗尽，切换备用 key "
                    f"({self._key_index + 1}/{len(self._api_keys)}) 重发"
                )
                continue
            break
        return response

    # ------------------------------------------------------------------
    # 路径策略：直连为主，代理仅为可选兜底
    # ------------------------------------------------------------------
    def _paths(self):
        """直连是默认真相路径（实测 1.6s 稳定）；代理只在直连网络不可达时兜底。"""
        paths = [("direct", None)]
        if self._proxies and not _proxy_circuit_open():
            paths.append(("proxy", self._proxies))
        return paths

    # ------------------------------------------------------------------
    # 单模型调用：直连优先，失败后再考虑代理
    # ------------------------------------------------------------------
    def _call_one(self, model, prompt, temperature=0.3):
        errors = []
        for label, proxies in self._paths():
            try:
                r = self._post(model, prompt, temperature, False, proxies)
                r = _verify_quota_response(
                    r, lambda: self._post(model, prompt, temperature, False, proxies)
                )
                _maybe_trip_account_circuit(r)
                r.raise_for_status()
                text = self._extract_text(r.json())
                if not text:
                    raise ValueError("ModelScope 返回空内容")
                return text
            except Exception as e:
                errors.append(f"{label}:{type(e).__name__}")
                if _provider_circuit_open("modelscope"):
                    # 额度冷却/鉴权失效：换代理路径同样无解，立即交回跨 Provider 兜底
                    break
                if label == "proxy" and _is_network_error(e):
                    _open_proxy_circuit()
        raise RuntimeError(f"模型 {model} 调用失败 ({', '.join(errors)})")

    def _stream_one(self, model, prompt, temperature, proxies) -> Generator[str, None, None]:
        response = None
        try:
            response = self._post(model, prompt, temperature, True, proxies)
            response = _verify_quota_response(
                response, lambda: self._post(model, prompt, temperature, True, proxies)
            )
            _maybe_trip_account_circuit(response)
            response.raise_for_status()
            # SSE 响应头通常只有 `text/event-stream`，不带 charset；
            # requests 会默认按 ISO-8859-1 解码，UTF-8 中文会变成 mojibake
            # （曾导致生成的 .py 里中文注释乱码 → SyntaxError）。
            # 因此取原始字节并显式按 UTF-8 解码，绝不依赖库的编码猜测。
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = (raw_line.decode("utf-8", errors="replace")
                        if isinstance(raw_line, bytes) else str(raw_line))
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                elif line.startswith("data: "):
                    data_str = line[6:].strip()
                else:
                    continue
                if data_str == "[DONE]":
                    break
                try:
                    import json
                    chunk = self._extract_text(json.loads(data_str))
                    if chunk:
                        yield chunk
                except (ValueError, TypeError):
                    continue
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # LLMClient 接口
    # ------------------------------------------------------------------
    def call(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        if _provider_circuit_open("modelscope"):
            raise RuntimeError(
                f"ModelScope 暂时不可用（熔断/额度冷却中）: "
                f"{_provider_circuit_reason('modelscope')}"
            )
        if not self._api_key:
            raise RuntimeError("MODELSCOPE_API_KEY 未设置")

        chain = self._get_chain()
        last_error = None
        for model in chain:
            if _provider_circuit_open("modelscope"):
                break
            try:
                print(f"[ModelScope] 调用模型: {model}")
                result = self._call_one(model, prompt, temperature)
                if model != chain[0]:
                    print(f"[ModelScope] 降级模型 {model} 调用成功")
                return result
            except Exception as e:
                print(f"[ModelScope] 模型 {model} 失败: {e}")
                last_error = e
                if _provider_circuit_open("modelscope"):
                    print("[ModelScope] 额度冷却/鉴权失效，停止遍历降级链，交回跨 Provider 兜底")
                    break
                continue

        raise RuntimeError(
            f"所有 ModelScope 模型均不可用 ({', '.join(chain)}): {last_error}"
        )

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if _provider_circuit_open("modelscope"):
            yield (f"\n\n[API 调用失败: ModelScope 暂时不可用（熔断/额度冷却中） - "
                   f"{_provider_circuit_reason('modelscope')}]")
            return
        if not self._api_key:
            yield "\n\n[API 调用失败: MODELSCOPE_API_KEY 未设置]"
            return

        chain = self._get_chain()
        last_error = None
        for model in chain:
            if _provider_circuit_open("modelscope"):
                break
            for label, proxies in self._paths():
                if _provider_circuit_open("modelscope"):
                    break
                emitted = False
                try:
                    print(f"[ModelScope Stream] 调用模型: {model} ({label})")
                    for chunk in self._stream_one(model, prompt, temperature, proxies):
                        emitted = True
                        yield chunk
                    if not emitted:
                        raise ValueError("ModelScope 流式返回空内容")
                    if model != chain[0]:
                        print(f"[ModelScope Stream] 降级模型 {model} 调用成功")
                    return
                except Exception as e:
                    print(f"[ModelScope Stream] 模型 {model} ({label}) 失败: {e}")
                    last_error = e
                    if label == "proxy" and _is_network_error(e):
                        _open_proxy_circuit()
                    if emitted:
                        # 已向调用方吐出内容，换路径重试会造成重复输出
                        return
                    if _provider_circuit_open("modelscope"):
                        print("[ModelScope Stream] 额度冷却/鉴权失效，停止遍历降级链")
                        break
                    continue

        yield f"\n\n[API 调用失败: 所有 ModelScope 模型不可用 - {last_error}]"