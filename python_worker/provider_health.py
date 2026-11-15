# -*- coding: utf-8 -*-
"""进程级 LLM Provider 健康状态（跨组件共享）。

背景（2026-11-14 真实故障 + 2026-11-14 事后核查纠错）：

ModelScope API-Inference 是**免费**的开发者服务（官方文档：非商业化、
非盈利产品），不使用人民币计费，也没有充值入口。它用「魔粒」积分抵扣调用：
轻量 0.5 / 主流 1 / 旗舰 2 魔粒每次，每日登录发放 200 魔粒（绑定阿里云
再 +50），短期魔粒 24 小时过期，额度每日 UTC+8 0 点重置。

因此 `429 insufficient balance` 指的是**免费魔粒额度不足**，不是账户欠费。
社区实测文档还指出：突发调用 / 单分钟限流时，ModelScope 会把 429 **误报**
为 `insufficient balance`。两种情况都**可恢复**（额度重置、限流窗口过去），
绝不是「账号报废」。

旧版实现把它判成「账户级不可恢复」并永久熔断（进程内不恢复，直到重启
Worker）——这是方向性错误：一次当天额度用完就把主线从 ModelScope 切走，
且永远不回头。

正确做法（本版）：
  * `fatal`   —— 401 鉴权失效 / 402 / 403 quota：真不可恢复，进程内永久熔断；
  * `quota`   —— 429 insufficient balance：免费额度耗尽或限流误报，
                 带 TTL 的**冷却**，到期自动半开（half-open）重新探测；
  * 普通 429 —— rate limit / too many requests：瞬时错误，不熔断，交给退避。

冷却期间跨 Provider 降级（DashScope）照常接管，意图分类 / 规划器旁路
共享同一状态，避免每个组件各撞一次墙。到期后自动恢复，无需重启 Worker、
无需人工 reset。

状态只存在于本进程内存（Worker 重启即重置），不落盘、不跨进程。
"""

import os
import threading
import time

_lock = threading.Lock()
_state: dict[str, dict] = {}

FATAL = "fatal"
QUOTA = "quota"

# 免费额度冷却时长（秒）。默认 5 分钟：
#   - 限流误报通常在分钟级窗口内自愈；
#   - 真额度耗尽时每 5 分钟只花 1 次请求做半开探测，代价可忽略；
#   - 冷却期间主链已由跨 Provider 降级接管，不影响端到端耗时。
# 可用环境变量 PROVIDER_QUOTA_COOLDOWN_SEC 调整。
_DEFAULT_QUOTA_COOLDOWN_SEC = 300


def _quota_cooldown_seconds() -> float:
    try:
        val = float(os.getenv("PROVIDER_QUOTA_COOLDOWN_SEC", "") or
                    _DEFAULT_QUOTA_COOLDOWN_SEC)
        return max(1.0, val)
    except (TypeError, ValueError):
        return float(_DEFAULT_QUOTA_COOLDOWN_SEC)


def trip(provider: str, reason: str, kind: str = FATAL, ttl: float | None = None) -> None:
    """标记某个 Provider 不可用（幂等，保留首次原因）。

    kind=FATAL：永久（进程内），不会被 quota 覆盖。
    kind=QUOTA：带 TTL 冷却，到期由 is_open() 自动清除实现半开。
    """
    key = (provider or "").lower().strip()
    if not key:
        return
    now = time.time()
    expires = (now + (ttl if ttl is not None else _quota_cooldown_seconds())) \
        if kind == QUOTA else None
    with _lock:
        existing = _expire_if_needed(key)
        if existing:
            # 已存在的永久熔断：幂等保留首次原因，不允许任何后续信号覆盖
            if existing.get("kind") == FATAL:
                return
            # quota 冷却未到期时不无限续期，保留首次探测时间点
            # （FATAL 可以升级覆盖 QUOTA，因为它是更强的不可用信号）
            if (existing.get("kind") == QUOTA and kind == QUOTA
                    and existing.get("expires") and now < existing["expires"]):
                return
        _state[key] = {
            "reason": reason[:400],
            "since": now,
            "kind": kind,
            "expires": expires,
        }


def trip_quota(provider: str, reason: str, ttl: float | None = None) -> None:
    """免费额度耗尽 / 限流误报 → 带 TTL 冷却。"""
    trip(provider, reason, kind=QUOTA, ttl=ttl)


def _expire_if_needed(key: str) -> dict | None:
    """调用方必须持有 _lock。冷却到期自动半开。"""
    item = _state.get(key)
    if item and item.get("expires") is not None and time.time() >= item["expires"]:
        del _state[key]
        return None
    return item


def is_open(provider: str) -> bool:
    """该 Provider 当前是否不可用（True = 熔断/冷却中）。

    冷却到期时自动清除状态并返回 False，实现无需人工干预的半开重试。
    """
    key = (provider or "").lower().strip()
    with _lock:
        return _expire_if_needed(key) is not None


def reason(provider: str) -> str:
    key = (provider or "").lower().strip()
    with _lock:
        item = _expire_if_needed(key)
        return item["reason"] if item else ""


def kind(provider: str) -> str:
    """返回 FATAL / QUOTA / ""（无状态）。"""
    key = (provider or "").lower().strip()
    with _lock:
        item = _expire_if_needed(key)
        return item["kind"] if item else ""


def cooldown_remaining(provider: str) -> float:
    """剩余冷却秒数；fatal / 无状态返回 0。"""
    key = (provider or "").lower().strip()
    with _lock:
        item = _expire_if_needed(key)
        if not item or item.get("expires") is None:
            return 0.0
        return max(0.0, item["expires"] - time.time())


def reset(provider: str | None = None) -> None:
    """清除状态（运维手动恢复 / 测试隔离用）。"""
    with _lock:
        if provider is None:
            _state.clear()
        else:
            _state.pop(provider.lower().strip(), None)


def snapshot() -> dict:
    with _lock:
        out = {}
        for k in list(_state):
            item = _expire_if_needed(k)
            if item:
                out[k] = {
                    "reason": item["reason"],
                    "since": item["since"],
                    "kind": item["kind"],
                    "expires": item["expires"],
                }
        return out


def classify_response(response) -> tuple[str | None, str | None]:
    """把 HTTP 响应分类为 (kind, reason)。

    FATAL —— 401 / 402 / 403 quota：鉴权或付费层不可恢复。
    QUOTA —— 429 + balance：免费魔粒额度耗尽或限流误报，可恢复。
    None  —— 普通 429 限流、其它状态码：瞬时错误，不熔断。
    """
    try:
        status = response.status_code
        if status not in (401, 402, 403, 429):
            return None, None
        body = (response.text or "")[:400]
        low = body.lower()
        why = f"HTTP {status}: {body[:200]}"
        if status in (401, 402) or (status == 403 and "quota" in low):
            return FATAL, why
        if status == 429 and ("insufficient balance" in low or "balance" in low
                              or "insufficient_quota" in low):
            return QUOTA, why
    except Exception:
        pass
    return None, None


def fatal_reason(response) -> str | None:
    """兼容旧接口：返回「需要熔断/冷却」的原因，或 None。

    注意：名字沿用历史调用点，但语义已扩展——429 balance 现在属于
    可恢复的 QUOTA 冷却，不再是账户级永久故障。分类请用 classify_response()。
    """
    _kind, why = classify_response(response)
    return why


def trip_if_fatal(provider: str, response) -> bool:
    """按分类标记 Provider；返回是否触发了熔断/冷却。

    兼容旧接口名。内部按 classify_response() 分流：
    FATAL → 永久熔断；QUOTA → 带 TTL 冷却；其它 → 什么都不做。
    """
    k, why = classify_response(response)
    if not k or not why:
        return False
    if k == QUOTA:
        trip_quota(provider, why)
    else:
        trip(provider, why, kind=FATAL)
    return True
