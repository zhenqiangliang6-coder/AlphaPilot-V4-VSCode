# -*- coding: utf-8 -*-
"""Worker 日志治理：结构化摘要代替全量 JSON dump。

真实问题（2026-11-14 ShopFlow 跟测）：
  `qwen_worker_v2.py` 把整个 result_data / task 用
  `TaskModel.pretty_print()`（json.dumps(indent=2)）打到 stdout，
  其中包含所有步骤的完整 prompt、记忆上下文、模型生成的全部源码。
  实测单行 **509,268 字符**，单轮 Worker 日志 **6.2 MB**，
  Node 侧同类全量打印累计 **11 MB**。

这对智能体系统是实打实的负担，不只是"日志难看"：
  1. 管道捕获 / 文件写入开销随输出量线性增长，实测输出重定向后
     同一测试从 21 分钟降到 9 分钟；
  2. 完整 prompt 与生成源码反复落盘，排查时真正有用的信号被淹没；
  3. 记忆上下文、用户请求原文被无差别写进长期日志文件。

治理原则：
  * 默认只输出**结构化摘要**：身份字段、状态、数量、路径列表、错误首行；
    大字段一律折叠为 `{类型, 长度, 预览}`，并硬截断。
  * 完整结果**不丢失** —— 本来就已写入 Redis（result_key），
    需要时用 `ALPHAPILOT_VERBOSE_LOG=1` 在终端开全量，或直接读 Redis。
  * 所有输出都有硬上界（单行 + 总量），防止以后新增字段再次撑爆。
"""

import os
from typing import Any

# 硬上界：任何一条日志都不允许超过这个值
MAX_LINE_CHARS = 400
MAX_PREVIEW_CHARS = 120
MAX_TOTAL_CHARS = 6000
MAX_LIST_ITEMS = 20
MAX_DEPTH = 4

# 这些字段的值通常是完整 prompt / 源码 / 大段文本，必须折叠
_HEAVY_KEYS = {
    "prompt", "content", "code", "text", "result", "input", "output",
    "response", "raw", "memory_context", "context", "messages",
    "file_ops", "final_file_ops", "steps", "events", "traceback",
    "baseline_errors", "detail", "payload", "source_code", "diff",
}

# 身份 / 状态字段：即使嵌套很深也保留原值（短且关键）
_IDENTITY_KEYS = {
    "task_id", "trace_id", "status", "task_state", "type", "task_type",
    "version", "protocol_version", "sequence", "event", "step_id",
    "phase", "path", "op", "model", "intent", "persona", "provider",
    "error", "success", "from_step", "file_type", "language",
}


def _verbose() -> bool:
    return (os.getenv("ALPHAPILOT_VERBOSE_LOG", "0") or "0").strip() == "1"


def _clip(text: str, limit: int) -> str:
    """硬截断：连截断标记本身也计入上界，保证返回值长度 <= limit。"""
    if len(text) <= limit:
        return text
    suffix = f"… [已截断 {len(text) - limit} 字符]"
    return text[:max(0, limit - len(suffix))] + suffix


def _summarize(value: Any, depth: int = 0, key: str = "") -> Any:
    """递归折叠大对象；超深/超长一律降级为摘要，绝不抛异常。"""
    if depth >= MAX_DEPTH:
        return f"<{type(value).__name__}, 深度>{MAX_DEPTH}"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if key in _IDENTITY_KEYS and len(value) <= MAX_LINE_CHARS:
            return value
        if len(value) <= MAX_PREVIEW_CHARS:
            return value
        # 大文本：保留首部预览 + 长度，绝不整段落盘
        return {
            "_type": "str",
            "len": len(value),
            "preview": _clip(value.replace("\n", "⏎"), MAX_PREVIEW_CHARS),
        }

    if isinstance(value, (list, tuple)):
        items = list(value)
        out = [_summarize(v, depth + 1) for v in items[:MAX_LIST_ITEMS]]
        if len(items) > MAX_LIST_ITEMS:
            out.append(f"… 另有 {len(items) - MAX_LIST_ITEMS} 项")
        return out

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            k = str(k)
            if k in _HEAVY_KEYS and isinstance(v, (str, list, dict)):
                if isinstance(v, str):
                    out[k] = _summarize(v, depth + 1, key=k)
                else:
                    size = len(v)
                    out[k] = {
                        "_type": type(v).__name__,
                        "len": size,
                        "items": _summarize(v, depth + 1, key=k)[:MAX_LIST_ITEMS]
                        if isinstance(v, list) else
                        f"<{size} 个字段: {', '.join(list(v)[:6])}…>",
                    }
            else:
                out[k] = _summarize(v, depth + 1, key=k)
        return out

    return _clip(repr(value), MAX_PREVIEW_CHARS)


def summarize(obj: Any) -> str:
    """把任意任务对象转成有硬上界的可读日志文本。"""
    import json
    try:
        text = json.dumps(_summarize(obj), ensure_ascii=False, indent=2)
    except Exception as e:  # 序列化失败也不能拖垮 Worker
        text = f"<日志摘要生成失败: {type(e).__name__}: {e}>"
    return _clip(text, MAX_TOTAL_CHARS)


def log_task(label: str, obj: Any, *, force_full: bool = False) -> None:
    """统一的「任务/结果」日志入口。

    force_full 或 ALPHAPILOT_VERBOSE_LOG=1 时输出全量（仅供本地调试），
    且全量输出同样受 MAX_TOTAL_CHARS 约束，避免再次撑爆管道。
    """
    print(f"\n{'=' * 60}")
    print(label)
    if force_full or _verbose():
        import json
        try:
            text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            text = f"<全量日志生成失败: {type(e).__name__}: {e}>"
        print(_clip(text, MAX_TOTAL_CHARS))
        print("(VERBOSE 模式：完整结果仍以 Redis 为准)")
    else:
        print(summarize(obj))
        print("(摘要模式：完整结果见 Redis；需全量请设 ALPHAPILOT_VERBOSE_LOG=1)")
    print("=" * 60 + "\n")


def log_line(text: str) -> str:
    """单行日志硬截断，供零星 print 使用。"""
    return _clip(str(text), MAX_LINE_CHARS)
