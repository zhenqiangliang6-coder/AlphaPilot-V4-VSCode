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

# G10.52（2026-11-18）：ModelScope 主链从 429 恢复 200 后暴露的健壮性缺口。
# 旧实现流/非流都只靠 requests 的 (connect, read)=(15,180) 超时：服务端保持
# 连接活跃却持续吐 reasoning/保活字节、迟迟不给完整 body 时 read timeout 永不
# 触发，长 prompt（refine/fix 阶段带整个工作区源码）会 hang 死整个任务链。
# v45 靠 429 被动降级到有墙钟治理的 qwen_client 才幸免；主链恢复后 R7 fix
# 卡死即此因。与 qwen_client 共用同一组墙钟环境变量口径，超时抛错 → 走既有
# 降级链 → call_llm 最终兜底 DashScope，FAIL-CLOSED。
_DEFAULT_STREAM_WALL_TIMEOUT_SEC = 240.0
_DEFAULT_STREAM_FIRST_CONTENT_SEC = 45.0


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.getenv(name, "").strip() or default))
    except (ValueError, AttributeError):
        return default


def stream_wall_timeout_sec() -> float:
    return _env_float("QWEN_STREAM_WALL_TIMEOUT_SEC", _DEFAULT_STREAM_WALL_TIMEOUT_SEC)


def stream_first_content_sec() -> float:
    return _env_float("QWEN_STREAM_FIRST_CONTENT_SEC", _DEFAULT_STREAM_FIRST_CONTENT_SEC)

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

# G10.28 续：账号轮换从「仅换 key」升级为「(key, base_url, model_chain) 整组切换」。
# 每个账号的 base_url 与模型链可独立配置（MODELSCOPE_BASE_URL{_A/_B/_C}、
# MODELSCOPE_MODEL{_A/_B/_C} + FALLBACK_1..5{_A/_B/_C}），缺省回退全局配置。
_ACCOUNT_SUFFIXES = ("", "_A", "_B", "_C")

_MODEL_CHAIN_KEY_NAMES = (
    "MODELSCOPE_MODEL",
    "MODELSCOPE_FALLBACK_1",
    "MODELSCOPE_FALLBACK_2",
    "MODELSCOPE_FALLBACK_3",
    "MODELSCOPE_FALLBACK_4",
    "MODELSCOPE_FALLBACK_5",
)


def _build_model_chain(suffix: str = "") -> list:
    """构建单个账号的模型降级链；suffix 为空即全局链。"""
    chain = []
    for key in _MODEL_CHAIN_KEY_NAMES:
        val = (os.getenv(f"{key}{suffix}") or "").strip()
        if val and val not in chain:
            chain.append(val)
    return chain


_DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1"
_DEFAULT_MODEL = "Qwen/Qwen3.8-Flash-Next"


def _build_account(suffix: str = "") -> dict:
    """构建单个账号的 (key, base_url, chain) 三元组；无 key 返回 None。

    G10.28 续：账号轮换从「仅换 key」升级为「整组切换」。每个账号的
    base_url 与模型降级链可独立配置（MODELSCOPE_BASE_URL{_A/_B/_C}、
    MODELSCOPE_MODEL{_A/_B/_C} + FALLBACK_1..5{_A/_B/_C}），缺省逐项回退
    全局配置。保证「换 key 必换 base_url + 模型链」，避免新 key 配旧模型名
    造成 400 无效模型。
    """
    key = (os.getenv(f"MODELSCOPE_API_KEY{suffix}") or "").strip()
    if not key:
        return None
    base_url = (
        os.getenv(f"MODELSCOPE_BASE_URL{suffix}")
        or os.getenv("MODELSCOPE_BASE_URL")
        or _DEFAULT_BASE_URL
    ).rstrip("/")
    chain = _build_model_chain(suffix) or _build_model_chain("") or [_DEFAULT_MODEL]
    return {"key": key, "base_url": base_url, "chain": chain}


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
        # G10.28 续：账号池由「纯 key 列表」升级为 (key, base_url, chain) 三元组，
        # 轮换时整组切换，杜绝「新 key 配旧 base_url/旧模型名」的 400 无效模型。
        accounts: list = []
        seen_keys: list = []
        for suffix in _ACCOUNT_SUFFIXES:
            acct = _build_account(suffix)
            if not acct or acct["key"] in seen_keys:
                continue
            seen_keys.append(acct["key"])
            accounts.append(acct)
        self._accounts = accounts
        self._key_index = 0
        # 向后兼容：既有代码读 self._api_key 判断「是否配置」，
        # 测试契约读 self._api_keys / self._key_index / self._current_key()。
        self._api_keys = [a["key"] for a in accounts]
        self._api_key = self._api_keys[0] if self._api_keys else ""
        self._base_url = accounts[0]["base_url"] if accounts else _DEFAULT_BASE_URL
        proxy = (os.getenv("MODELSCOPE_PROXY_URL") or "").strip()
        self._proxies = {"http": proxy, "https": proxy} if proxy else None
        # 独立 Session：trust_env=False 让 "直连" 真正不经由环境变量代理。
        # 否则 proxies=None 时 requests 仍读 HTTP_PROXY/HTTPS_PROXY，
        # 代理故障会连带打死兜底路径，降级链形同虚设。
        self._session = requests.Session()
        self._session.trust_env = False

    # ------------------------------------------------------------------
    # 模型降级链：MODELSCOPE_MODEL → MODELSCOPE_FALLBACK_1..5
    # G10.28 续：链改为按当前账号返回（整组切换），避免换号后仍用旧账号模型名。
    # ------------------------------------------------------------------
    def _get_chain(self):
        return self._current_chain()

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
    # G10.28: 账号级额度轮换（key + base_url + 模型链 整组切换）
    # ------------------------------------------------------------------
    def _current_account(self) -> dict:
        if not self._accounts:
            return {}
        return self._accounts[min(self._key_index, len(self._accounts) - 1)]

    def _current_key(self) -> str:
        if not self._api_keys:
            return ""
        return self._api_keys[min(self._key_index, len(self._api_keys) - 1)]

    def _current_base_url(self) -> str:
        return self._current_account().get("base_url") or self._base_url

    def _current_chain(self) -> list:
        chain = self._current_account().get("chain")
        if chain:
            return chain
        # 无账号（或测试直连）时的全局兜底，维持旧默认链语义
        return _build_model_chain("") or [_DEFAULT_MODEL]

    def _rotate_key(self) -> bool:
        """切到池内下一个账号并整组切换；已到末尾返回 False（交由上层熔断）。"""
        if self._key_index + 1 >= len(self._api_keys):
            return False
        self._key_index += 1
        self._api_key = self._current_key()
        self._base_url = self._current_base_url()
        return True

    def _post(self, model, prompt, temperature, stream, proxies):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        body.update(_THINK_OFF)
        if stream:
            body["stream"] = True

        # 只把「429 免费额度耗尽」当作换账号信号；网络错误 / 5xx /
        # 普通限流仍交给既有路径策略与降级链处理，避免放大故障。
        # base_url 每次尝试按当前账号重取，配合 _rotate_key 的整组切换，
        # 保证换 key 的同时不再沿用旧账号的 base_url。
        response = None
        for _attempt in range(max(1, len(self._api_keys))):
            headers = {
                "Authorization": f"Bearer {self._current_key()}",
                "Content-Type": "application/json",
            }
            url = f"{self._current_base_url()}/chat/completions"
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
                    f"[ModelScope] 当前账号额度耗尽，切换备用账号 "
                    f"({self._key_index + 1}/{len(self._api_keys)}，"
                    f"base_url={self._current_base_url()}) 重发"
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
            # G10.52：墙钟上界。read timeout 只约束相邻 chunk 间隔，服务端
            # 持续吐 reasoning/保活字节时会永不触发；用 monotonic 墙钟兜底，
            # 首正文 45s / 全程 240s 超界即抛错，交回降级链（FAIL-CLOSED）。
            wall_sec = stream_wall_timeout_sec()
            first_sec = stream_first_content_sec()
            started = time.monotonic()
            produced = False
            # 兼容非 SSE 响应（含既有 key 轮换契约里的 json-only mock）：
            # 无 iter_lines 时按一次性 JSON 提取，语义等同旧 _call_one。
            if not hasattr(response, "iter_lines"):
                text = self._extract_text(response.json())
                if text:
                    yield text
                return
            # SSE 响应头通常只有 `text/event-stream`，不带 charset；
            # requests 会默认按 ISO-8859-1 解码，UTF-8 中文会变成 mojibake
            # （曾导致生成的 .py 里中文注释乱码 → SyntaxError）。
            # 因此取原始字节并显式按 UTF-8 解码，绝不依赖库的编码猜测。
            for raw_line in response.iter_lines(decode_unicode=False):
                elapsed = time.monotonic() - started
                if elapsed > wall_sec or (not produced and elapsed > first_sec):
                    raise TimeoutError(
                        f"ModelScope 流式超上界 "
                        f"(wall={wall_sec:.0f}s/first={first_sec:.0f}s, "
                        f"produced={produced})"
                    )
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
                        produced = True
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

        # G10.52：非流式阻塞 post 在服务端「连接活跃但无完整 body」时 read
        # timeout 永不触发（v55 R7 fix 卡死实证）。改为走 call_stream 拼接——
        # 两者共用 _post（429 key 轮换 + 直连/代理路径语义不变），但流式迭代
        # 带首正文/全程墙钟上界（_stream_one），超时抛错交回降级链。
        # 与 QwenClient.call() 的实现口径一致。
        chunks = []
        for chunk in self.call_stream(prompt, temperature):
            if "[API 调用失败" in chunk:
                raise RuntimeError(chunk.strip())
            chunks.append(chunk)
        text = "".join(chunks)
        if not text.strip():
            raise RuntimeError("ModelScope 返回空内容")
        return text

    def call_stream(self, prompt: str, temperature: float = 0.3, **kwargs) -> Generator[str, None, None]:
        if _provider_circuit_open("modelscope"):
            yield (f"\n\n[API 调用失败: ModelScope 暂时不可用（熔断/额度冷却中） - "
                   f"{_provider_circuit_reason('modelscope')}]")
            return
        if not self._api_key:
            yield "\n\n[API 调用失败: MODELSCOPE_API_KEY 未设置]"
            return

        last_error = None
        # G10.28 续：账号轮换是「整组切换」（key + base_url + 模型链）。
        # _post 在额度 429 时换号；若某次模型尝试期间发生了换号（_key_index
        # 前进），说明旧账号的模型链已不适用，须跳出旧链、用新账号自己的链
        # 重新开始，避免「新 key 配旧模型名」导致 400 无效模型。
        while True:
            account_index = self._key_index
            chain = self._get_chain()
            rotated = False
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
                        if self._key_index != account_index:
                            # 该模型尝试期间发生了账号轮换，用新账号链重来
                            rotated = True
                            break
                        if _provider_circuit_open("modelscope"):
                            print("[ModelScope Stream] 额度冷却/鉴权失效，停止遍历降级链")
                            break
                        continue
                if rotated:
                    break
            if not rotated:
                break

        yield f"\n\n[API 调用失败: 所有 ModelScope 模型不可用 - {last_error}]"