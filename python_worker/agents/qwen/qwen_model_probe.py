# -*- coding: utf-8 -*-
# qwen_model_probe.py
# ---------------------------------------------------------
# Qwen 模型运行时探测 — 客观模型发现
#
# 设计原则：
#   第一步：GET /v1/models 获取 API Key 真实的可用模型列表（不预设候选）
#   第二步：按能力自动分类（文本 / 视觉 / 全模态 / 专用）
#   第三步：按代际 + 能力排序构建降级链
#
# 不硬编码任何模型名，一切以 API 返回为准。
# ---------------------------------------------------------

import os
import sys
import json
import re
import time
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dotenv import load_dotenv

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PACKAGE_ROOT / ".env")

if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

try:
    from ...worker_config import DASHSCOPE_API_KEY
except (ImportError, ValueError):
    from worker_config import DASHSCOPE_API_KEY

# ============================================================
# 常量
# ============================================================
COMPATIBLE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 非对话类模型关键词（排除：embedding / rerank / audio / tts / asr / image-gen / livetranslate / s2s / mt / deep-research 等）
NON_CHAT_PATTERNS = [
    r"embedding", r"rerank", r"embed",
    r"audio", r"asr", r"tts", r"speech",
    r"livetranslate", r"s2s",
    r"image-\d", r"wan2", r"z-image",
    r"mt-", r"ocr",
    r"deep-research", r"deep-search",
    r"xiaomi", r"fun-asr",
    r"gui-plus", r"sre-gpu", r"test-",
]

# 视觉模型关键词
VISION_PATTERNS = [r"\bvl\b", r"vision", r"vl-"]

# 全模态模型关键词（支持文本+图片+音频）
OMNI_PATTERNS = [r"omni"]

# 专用代码模型（可当文本模型用）
CODER_PATTERNS = [r"coder"]

# 缓存
_cache: Optional[Dict] = None
_cache_ts: float = 0
_CACHE_TTL = 3600


# ============================================================
# 第一步：从 /v1/models 获取 API Key 真实可用模型列表
# ============================================================
def _fetch_models_from_api() -> List[str]:
    """调用 DashScope compatible-mode /v1/models，获取完整模型清单"""
    if not DASHSCOPE_API_KEY:
        return []

    try:
        r = requests.get(
            f"{COMPATIBLE_BASE}/models",
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            models = [m["id"] for m in data.get("data", [])]
            return models
        else:
            print(f"   ⚠️ /v1/models 返回 {r.status_code}")
            return []
    except Exception as e:
        print(f"   ⚠️ /v1/models 请求失败: {e}")
        return []


# ============================================================
# 第二步：按能力分类
# ============================================================
def _is_non_chat(model_id: str) -> bool:
    """排除非对话类模型（embedding、audio、tts 等）"""
    lower = model_id.lower()
    for pat in NON_CHAT_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


def _is_qwen_model(model_id: str) -> bool:
    """判断是否为 Qwen 系列模型"""
    lower = model_id.lower()
    return lower.startswith("qwen")


def _is_vision_model(model_id: str) -> bool:
    """判断是否为视觉模型（vl / vision）"""
    lower = model_id.lower()
    for pat in VISION_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


def _is_omni_model(model_id: str) -> bool:
    """判断是否为全模态模型（omni）"""
    lower = model_id.lower()
    for pat in OMNI_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


def _is_coder_model(model_id: str) -> bool:
    """判断是否为专用代码模型"""
    lower = model_id.lower()
    for pat in CODER_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


def _categorize_models(model_ids: List[str]) -> Dict[str, List[str]]:
    """
    将模型按能力分类。

    返回:
        {
            "text":       纯文本对话模型,
            "vision":     视觉语言模型 (vl),
            "omni":       全模态模型 (文本+图片+音频),
            "coder":      专用代码模型,
            "all_qwen":   所有 Qwen 对话模型,
            "all_chat":   所有可用对话模型 (含第三方),
        }
    """
    text_models = []
    vision_models = []
    omni_models = []
    coder_models = []
    all_qwen_chat = []
    all_chat_models = []

    for m in model_ids:
        if _is_non_chat(m):
            continue

        all_chat_models.append(m)

        if not _is_qwen_model(m):
            continue

        all_qwen_chat.append(m)

        if _is_omni_model(m):
            omni_models.append(m)
        elif _is_vision_model(m):
            vision_models.append(m)
        elif _is_coder_model(m):
            coder_models.append(m)
        else:
            text_models.append(m)

    return {
        "text": text_models,
        "vision": vision_models,
        "omni": omni_models,
        "coder": coder_models,
        "all_qwen": all_qwen_chat,
        "all_chat": all_chat_models,
    }


# ============================================================
# 第三步：按能力排序
# ============================================================
def _parse_generation(model_id: str) -> Tuple[float, str]:
    """
    解析模型代际，返回 (numeric_version, tier)。

    代际识别规则（按发布时间和命名）:
      qwen3.8  → 3.8
      qwen3.7  → 3.7
      qwen3.6  → 3.6
      qwen3.5  → 3.5
      qwen3    → 3.0
      qwen2.5  → 2.5
      qwen2    → 2.0
      qwen1.5  → 1.5
      qwen-max → 2.5  (qwen2.5 时代的旗舰)
      qwen     → 1.0  (原始 qwen)
    """
    lower = model_id.lower()

    # 精确匹配 qwenX.Y 格式
    m = re.search(r"qwen(\d+)\.?(\d+)?", lower)
    if m:
        major = int(m.group(1))
        minor = int(m.group(2)) if m.group(2) else 0
        gen = float(f"{major}.{minor}")
    else:
        # qwen-max / qwen-plus 等旧命名 → 视为 qwen2.5 时代
        gen = 2.5

    # 能力等级
    if "max" in lower:
        tier = "max"
    elif "plus" in lower:
        tier = "plus"
    elif "flash" in lower:
        tier = "flash"
    elif "turbo" in lower:
        tier = "turbo"
    elif "long" in lower:
        tier = "long"
    elif "coder" in lower:
        tier = "coder"
    else:
        tier = "base"

    return gen, tier


def _model_sort_key(model_id: str):
    """
    排序优先级：
      1. 代际（高版本优先）
      2. 能力等级（max > plus > flash > turbo > coder > long > base）
      3. 无日期后缀优先（规范名优先于版本号后缀名）
    """
    gen, tier = _parse_generation(model_id)

    tier_order = {"max": 0, "plus": 1, "flash": 2, "turbo": 3, "coder": 4, "long": 5, "base": 6}
    tier_rank = tier_order.get(tier, 9)

    # 无日期后缀的规范名优先
    has_date_suffix = bool(re.search(r"\d{4}-\d{2}-\d{2}|\d{4}$", model_id))
    date_penalty = 1 if has_date_suffix else 0

    # 短名优先（如 qwen-max 优于 qwen-max-1201）
    name_len_penalty = len(model_id) * 0.001

    return (-gen, tier_rank, date_penalty, name_len_penalty)


def _rank_models(models: List[str]) -> List[str]:
    """按能力排序（最强在前）"""
    return sorted(models, key=_model_sort_key)


# ============================================================
# 第四步：轻量可用性验证（可选，对排序后的链做二次确认）
# ============================================================
def _lightweight_text_probe(model: str, verbose: bool = True) -> bool:
    """
    轻量文本探测：用 compatible-mode chat/completions 端点发最小请求。

    返回 True 表示模型可用；返回 False 时会打印具体失败原因。
    内置二次重试：max_tokens=1 失败时尝试不带 max_tokens 的请求。
    """
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    def _try_request(body: dict, timeout: int = 15) -> Tuple[bool, str]:
        try:
            r = requests.post(
                f"{COMPATIBLE_BASE}/chat/completions",
                headers=headers,
                json=body,
                timeout=timeout,
            )
            if r.status_code == 200:
                data = r.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return True, ""
                else:
                    return False, f"200 但无 choices: {json.dumps(data, ensure_ascii=False)[:200]}"
            else:
                try:
                    err_body = r.json()
                    err_msg = err_body.get("error", {}).get("message", err_body.get("message", r.text[:200]))
                except Exception:
                    err_msg = r.text[:200]
                return False, f"HTTP {r.status_code}: {err_msg}"
        except requests.exceptions.Timeout:
            return False, "超时 (10s)"
        except requests.exceptions.ConnectionError as e:
            return False, f"连接失败: {e}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    body_v1 = {
        "model": model,
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1,
        "temperature": 0.0,
    }
    ok, err = _try_request(body_v1)
    if ok:
        return True

    if "400" in err or "max_tokens" in err.lower() or "invalid" in err.lower():
        body_v2 = {
            "model": model,
            "messages": [{"role": "user", "content": "1"}],
            "temperature": 0.0,
        }
        ok2, err2 = _try_request(body_v2, timeout=12)
        if ok2:
            return True
        if verbose:
            print(f"      ↳ {err}  |  重试(无max_tokens): {err2}")
    else:
        if verbose:
            print(f"      ↳ {err}")

    return False


def _probe_all_chat_fallback(
    categorized: Dict[str, List[str]],
    already_probed: set,
    max_probe: int = 50,
) -> List[str]:
    """
    全量兜底探测：当 Qwen 专有模型全部不可用时，
    对 all_chat 中所有剩余对话模型（含第三方）进行探测。

    Args:
        categorized: _categorize_models 的返回结果
        already_probed: 已经探测过的模型名集合
        max_probe: 最多额外探测的模型数

    Returns:
        已验证可用的模型名列表（按代际排序）
    """
    all_chat = categorized.get("all_chat", [])
    remaining = [m for m in all_chat if m not in already_probed]

    if not remaining:
        return []

    print(f"\n🔄 [Qwen Probe] Qwen 专有模型不可用，扩展探测到全部对话模型 ({len(remaining)} 个)...")

    remaining_ranked = _rank_models(remaining)
    verified = []
    probe_count = 0

    for m in remaining_ranked:
        if probe_count >= max_probe:
            remaining_unprobed = len(remaining_ranked) - probe_count
            if remaining_unprobed > 0:
                print(f"   ... 已达探测上限 ({max_probe})，剩余 {remaining_unprobed} 个模型未探测")
            break

        ok = _lightweight_text_probe(m)
        status = "✅" if ok else "❌"
        is_qwen = _is_qwen_model(m)
        label = "Qwen" if is_qwen else "第三方"
        print(f"   {status} [{label}] {m}")
        if ok:
            verified.append(m)
        probe_count += 1
        time.sleep(0.05)

    return verified


# ============================================================
# 公开 API
# ============================================================
def probe_qwen_models(force: bool = False) -> Dict[str, List[str]]:
    """
    探测 DASHSCOPE_API_KEY 实际可用的 Qwen 模型。

    流程:
      1. GET /v1/models → 获取完整模型清单
      2. 按能力分类（文本 / 视觉 / 全模态）
      3. 按代际 + 能力排序
      4. 轻量可用性验证（可选）

    返回:
        {
            "text":         ["qwen3.8-max", "qwen3.7-max", "qwen-max", ...],
            "vision":       ["qwen3-vl-plus", ...],
            "omni":         ["qwen3.8-omni-flash", ...],
            "coder":        ["qwen-coder-plus-1106", "qwen3-coder-flash"],
            "all_qwen":     [...所有 Qwen 对话模型...],
            "all_chat":     [...所有可用对话模型（含第三方）...],
            "best_text":    "qwen3.8-max",
            "best_vision":  "qwen3.8-omni-flash",  # 视觉取 vl + omni 中最强的
        }
    """
    global _cache, _cache_ts

    now = time.time()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL and not force:
        return _cache

    if not DASHSCOPE_API_KEY:
        result = {
            "text": [], "vision": [], "omni": [], "coder": [],
            "all_qwen": [], "all_chat": [],
            "best_text": "", "best_vision": "",
        }
        _cache = result
        _cache_ts = now
        return result

    # ── 第一步：从 API 获取真实模型列表 ──
    print("\n📡 [Qwen Probe] 第一步：从 /v1/models 获取 API Key 可用模型清单...")
    all_models = _fetch_models_from_api()
    print(f"   ✅ 获取到 {len(all_models)} 个模型")

    # ── 第二步：分类 ──
    print("\n🔬 [Qwen Probe] 第二步：按能力自动分类...")
    categorized = _categorize_models(all_models)

    text_raw = categorized["text"]
    vision_raw = categorized["vision"]
    omni_raw = categorized["omni"]
    coder_raw = categorized["coder"]

    print(f"   文本模型: {len(text_raw)} 个")
    print(f"   视觉模型: {len(vision_raw)} 个")
    print(f"   全模态模型: {len(omni_raw)} 个")
    print(f"   代码模型: {len(coder_raw)} 个")
    print(f"   Qwen 对话模型合计: {len(categorized['all_qwen'])} 个")
    print(f"   全部对话模型（含第三方）: {len(categorized['all_chat'])} 个")

    # ── 第三步：排序 ──
    print("\n📊 [Qwen Probe] 第三步：按代际 + 能力排序...")
    text_ranked = _rank_models(text_raw)
    vision_ranked = _rank_models(vision_raw)
    omni_ranked = _rank_models(omni_raw)
    coder_ranked = _rank_models(coder_raw)

    # ── 第四步：轻量可用性验证 ──
    print("\n🔍 [Qwen Probe] 第四步：轻量可用性验证（Top 候选）...")
    already_probed = set()
    text_verified = []
    for m in text_ranked[:10]:
        ok = _lightweight_text_probe(m)
        already_probed.add(m)
        status = "✅" if ok else "❌"
        print(f"   {status} 文本: {m}")
        if ok:
            text_verified.append(m)
        time.sleep(0.1)

    # 视觉候选 = 专用视觉模型 + 全模态模型（omni 也能处理图片）
    vision_candidates = _rank_models(vision_raw + omni_raw)
    vision_verified = []
    for m in vision_candidates:
        ok = _lightweight_text_probe(m)
        already_probed.add(m)
        status = "✅" if ok else "❌"
        print(f"   {status} 视觉/全模态: {m}")
        if ok:
            vision_verified.append(m)
        time.sleep(0.1)

    # ── 第五步：兜底探测 — Qwen 专有模型全失败时，全量扫描 all_chat ──
    if not text_verified and not vision_verified:
        fallback_verified = _probe_all_chat_fallback(categorized, already_probed)
        if fallback_verified:
            text_verified = fallback_verified
            print(f"\n   ✅ 兜底探测成功，从全部对话模型中找到 {len(fallback_verified)} 个可用模型")
        else:
            print(f"\n   ❌ 兜底探测也未找到可用模型，API Key 可能无权限或网络不通")

    result = {
        "text": text_verified,
        "vision": vision_verified,
        "omni": omni_ranked,
        "coder": coder_ranked,
        "all_qwen": categorized["all_qwen"],
        "all_chat": categorized["all_chat"],
        "best_text": text_verified[0] if text_verified else "",
        "best_vision": vision_verified[0] if vision_verified else "",
        "_raw_categories": categorized,
    }

    _cache = result
    _cache_ts = now

    print(f"\n📋 [Qwen Probe] 探测完成:")
    print(f"   文本链 ({len(text_verified)}): {' → '.join(text_verified[:5]) if text_verified else '(无)'}")
    print(f"   视觉链 ({len(vision_verified)}): {' → '.join(vision_verified[:5]) if vision_verified else '(无)'}")

    return result


def get_text_fallback_chain() -> List[str]:
    """
    获取文本模型降级链。

    优先级：
      1. 环境变量 QWEN_MODEL / QWEN_FALLBACK_1 / QWEN_FALLBACK_2 / QWEN_FALLBACK_3
      2. 运行时探测结果（已包含全量兜底）
      3. 最终兜底：返回探测中 all_chat 的前几个模型名（即使未验证也尝试使用）
    """
    chain = []
    env_models = [
        os.getenv("QWEN_MODEL"),
        os.getenv("QWEN_FALLBACK_1"),
        os.getenv("QWEN_FALLBACK_2"),
        os.getenv("QWEN_FALLBACK_3"),
    ]
    for m in env_models:
        if m and m not in chain:
            chain.append(m)
    if chain:
        return chain

    probe = probe_qwen_models()
    if probe["text"]:
        return probe["text"]

    all_chat_ranked = _rank_models(probe.get("all_chat", []))
    if all_chat_ranked:
        print(f"[Qwen Probe] 无已验证模型，使用 all_chat 排序列表作为最终降级链 ({len(all_chat_ranked)} 个)")
        return all_chat_ranked[:10]

    return ["qwen-max"]


def get_vision_fallback_chain() -> List[str]:
    """
    获取视觉模型降级链。

    优先级：
      1. 环境变量 QWEN_VISION_MODEL / QWEN_VISION_FALLBACK
      2. 运行时探测结果（视觉 + 全模态合并，已包含全量兜底）
    """
    chain = []
    env_models = [
        os.getenv("QWEN_VISION_MODEL"),
        os.getenv("QWEN_VISION_FALLBACK"),
    ]
    for m in env_models:
        if m and m not in chain:
            chain.append(m)
    if chain:
        return chain

    probe = probe_qwen_models()
    if probe["vision"]:
        return probe["vision"]

    all_chat_ranked = _rank_models(probe.get("all_chat", []))
    if all_chat_ranked:
        return all_chat_ranked[:10]

    return ["qwen-vl-plus"]


# ============================================================
# CLI 入口：python -m agents.qwen.qwen_model_probe
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Qwen Model Probe — DashScope 模型可用性探测")
    print("=" * 60)
    print(f"API Key 前缀: {DASHSCOPE_API_KEY[:12]}..." if DASHSCOPE_API_KEY else "API Key: ⚠️ 未设置")
    print()

    result = probe_qwen_models(force=True)

    # 完整模型清单
    print("\n" + "=" * 60)
    print("📋 完整 API 可用模型清单（按分类）:")
    print("=" * 60)

    cat = result.get("_raw_categories", {})
    for label, key in [
        ("🔤 纯文本对话模型", "text"),
        ("👁️ 视觉语言模型 (VL)", "vision"),
        ("🌐 全模态模型 (Omni)", "omni"),
        ("💻 专用代码模型", "coder"),
    ]:
        models = _rank_models(cat.get(key, []))
        print(f"\n  {label} ({len(models)} 个):")
        for m in models:
            mark = "  ⭐" if m == result.get("best_text") or m == result.get("best_vision") else ""
            print(f"    - {m}{mark}")

    # 建议配置
    print("\n" + "=" * 60)
    print("📋 建议 .env 配置:")
    print("=" * 60)
    if result["text"]:
        print(f"QWEN_MODEL={result['text'][0]}")
        for i, m in enumerate(result["text"][1:4], 1):
            print(f"QWEN_FALLBACK_{i}={m}")
    if result["vision"]:
        print(f"QWEN_VISION_MODEL={result['vision'][0]}")
        if len(result["vision"]) > 1:
            print(f"QWEN_VISION_FALLBACK={result['vision'][1]}")