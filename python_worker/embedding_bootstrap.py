# -*- coding: utf-8 -*-
"""
AlphaPilot 本地 Embedding 启动自愈 + 预加载
==========================================
工业级设计目标：任何全新 venv 启动时，本地 embedding（fastembed + BGE-small-zh-v1.5）
都能自动就绪，启动即命中常驻缓存，无需人工复制依赖或重复下载模型。

三层保障：
  1. 依赖声明可复现：requirements.txt 已声明 fastembed（`pip install -r` 即可复现引擎）
  2. 启动自愈：fastembed 运行时缺失时自动 `pip install fastembed`；
     若本地存在 vendor wheel 目录则离线兜底，否则走网络镜像
  3. 启动预加载：模型权重常驻 ~/.cache/fastembed_cache，启动即加载、永不重复下载

非阻塞契约：任何失败只打印降级提示（云端 embedding 兜底），绝不拖垮 worker 主循环。
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_VENDOR_WHEELS = _PACKAGE_DIR / "vendor" / "wheels"

# 本地 embedding 最小运行时：fastembed 依赖 onnxruntime + tokenizers
_MINIMUM_RUNTIME = ("fastembed", "onnxruntime", "tokenizers")

# 与 memory_service 保持一致的云端模式开关
_CLOUD_MODES = ("cloud", "api", "dashscope", "openai")


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _missing_modules() -> list:
    return [m for m in _MINIMUM_RUNTIME if not _module_available(m)]


def _pip_install_fastembed() -> bool:
    """尽力安装 fastembed，绝不抛出异常。成功返回 True，失败返回 False。"""
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input", "-q",
    ]
    if _VENDOR_WHEELS.is_dir():
        # 离线兜底：本地 vendor wheel 优先，禁止联网
        cmd += ["--no-index", "--find-links", str(_VENDOR_WHEELS)]
    cmd.append("fastembed")

    print("[embed] fastembed 运行时缺失，正在自动安装 ...", flush=True)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("[embed] fastembed 自动安装超时（600s），转降级模式", flush=True)
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[embed] fastembed 自动安装异常: {e}", flush=True)
        return False

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        print(f"[embed] fastembed 自动安装失败: {tail[-1] if tail else 'unknown'}", flush=True)
        return False

    print("[embed] fastembed 运行时安装完成", flush=True)
    return True


def ensure_embedding_ready() -> dict:
    """
    启动自愈 + 预加载本地 embedding。

    返回状态字典（永不抛出异常）：
      {"ok": bool, "backend": str|None, "dim": int|None,
       "model": str|None, "size_mb": int|None}
    """
    status = {"ok": False, "backend": None, "dim": None, "model": None, "size_mb": None}

    use_cloud = os.getenv("ALPHAPILOT_EMBEDDING", "local").lower() in _CLOUD_MODES
    if use_cloud:
        print("[embed] 配置使用云端 embedding，跳过本地模型预加载", flush=True)
        return status

    # 自愈：fastembed 运行时缺失时自动安装
    missing = _missing_modules()
    if missing:
        print(f"[embed] 检测到本地 embedding 运行时缺失: {', '.join(missing)}", flush=True)
        if not _pip_install_fastembed():
            print("[embed] 本地 embedding 运行时不可用，将降级到云端 embedding", flush=True)
            return status

    # 预加载：命中常驻缓存，触发懒加载
    if str(_PACKAGE_DIR) not in sys.path:
        sys.path.insert(0, str(_PACKAGE_DIR))
    try:
        from local_embedding import get_embedding_provider
        provider = get_embedding_provider()
    except Exception as e:  # noqa: BLE001
        print(f"[embed] 本地 embedding 预加载失败: {e}（降级到云端 embedding）", flush=True)
        return status

    if provider is None:
        print("[embed] 本地 embedding 未加载，将降级到云端 embedding", flush=True)
        return status

    try:
        dim = provider.dimension  # 触发 _lazy_load，打印目标就绪日志
        backend = provider.backend_name
        spec = getattr(provider, "_active_spec", None) or {}
        status.update({
            "ok": True,
            "backend": backend,
            "dim": dim,
            "model": spec.get("name"),
            "size_mb": spec.get("size_mb"),
        })
        print(f"[embed] 启动预加载完成 -> BACKEND= {backend} DIM= {dim} VEC_LEN= {dim}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[embed] 本地 embedding 加载失败: {e}（降级到云端 embedding）", flush=True)
        return status

    return status