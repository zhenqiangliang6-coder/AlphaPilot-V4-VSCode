# -*- coding: utf-8 -*-
"""
AlphaPilot 本地 Embedding 提供者
================================
设计原则:
  1. 默认本地（免费），可选 API（高质量）
  2. 模型懒加载（首次调用才加载）
  3. 下载失败降级到更小的模型
  4. CPU 友好（不依赖 GPU）
  5. fastembed 优先（ONNX, ~30MB，零深度学习依赖），sentence-transformers 备选
  6. 国内网络优先 ModelScope 下载，失败降级 HF 镜像

模型注册表（按优先级排列）:
  - BAAI/bge-small-zh-v1.5 : 24MB, 512维, 中英均衡, 推荐首选
  - sentence-transformers/all-MiniLM-L6-v2 : 80MB, 384维, 英文为主, 备选
  - BAAI/bge-micro-v2 : 17MB, 384维, 极限场景降级

后端加载优先级:
  1. fastembed (ONNX Runtime)      ← 推荐，轻量高效
  2. sentence-transformers (PyTorch) ← 备选，功能更全

模型下载优先级:
  1. ModelScope (modelscope.cn)    ← 国内首选，秒下
  2. HF-Mirror (hf-mirror.com)     ← 备选镜像
  3. HuggingFace 直连              ← 兜底

使用方式:
    from local_embedding import get_embedding_provider
    provider = get_embedding_provider()
    vec = provider.embed("def hello(): print('world')")
"""

import os
import shutil
import socket
import tempfile
from typing import List, Optional

# ============================================================
# 国内网络优化 — 智能代理检测
# ============================================================
def _detect_local_proxy() -> Optional[str]:
    common_ports = [22307, 7890, 10809, 1080, 8888, 8080]
    for port in common_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect(("127.0.0.1", port))
            s.close()
            return f"http://127.0.0.1:{port}"
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return None


_has_proxy = any(os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"))
if not _has_proxy:
    _local_proxy = _detect_local_proxy()
    if _local_proxy:
        os.environ["HTTP_PROXY"] = _local_proxy
        os.environ["HTTPS_PROXY"] = _local_proxy
        os.environ["http_proxy"] = _local_proxy
        os.environ["https_proxy"] = _local_proxy
    elif not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ============================================================
# 模型注册表
# ============================================================
EMBEDDING_MODELS = [
    {
        "name": "BAAI/bge-small-zh-v1.5",
        "dim": 512,
        "size_mb": 24,
        "language": "zh+en",
    },
    {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "dim": 384,
        "size_mb": 80,
        "language": "en",
    },
    {
        "name": "BAAI/bge-micro-v2",
        "dim": 384,
        "size_mb": 17,
        "language": "zh+en",
    },
]


# ============================================================
# 模型下载工具（国内网络优化）
# ============================================================
def _download_from_modelscope(model_name: str, target_dir: str) -> bool:
    try:
        from modelscope import snapshot_download
        print(f"[embed] 正在从 ModelScope 下载 {model_name} ...", flush=True)
        snapshot_download(model_name, cache_dir=target_dir)
        print(f"[embed] ModelScope 下载完成 -> {target_dir}", flush=True)
        return True
    except ImportError:
        print("[embed] modelscope 未安装, 跳过", flush=True)
        return False
    except Exception as e:
        print(f"[embed] ModelScope 下载失败: {e}", flush=True)
        return False


def _download_from_hf_mirror(model_name: str) -> Optional[str]:
    try:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        from huggingface_hub import snapshot_download
        print(f"[embed] 正在从 HF-Mirror 下载 {model_name} ...", flush=True)
        cache_dir = snapshot_download(model_name)
        print(f"[embed] HF-Mirror 下载完成 -> {cache_dir}", flush=True)
        return cache_dir
    except Exception as e:
        print(f"[embed] HF-Mirror 下载失败: {e}", flush=True)
        return None


class LocalEmbeddingProvider:
    """本地 embedding — 零 API 成本，离线可用。"""

    def __init__(self, model_name: str = None):
        self._model_name = model_name
        self._model = None
        self._dim = None
        self._backend = None
        self._active_spec = None

    # --------------------------------------------------------
    # 模型下载（国内网络优先 ModelScope -> HF-Mirror）
    # --------------------------------------------------------
    def _download_model_locally(self, spec: dict) -> Optional[str]:
        model_name = spec["name"]
        safe_name = model_name.replace("/", "--")

        # 尝试 1: ModelScope
        modelscope_dir = os.path.join(tempfile.gettempdir(), "fastembed_cache", "modelscope", safe_name)
        if os.path.isdir(modelscope_dir) and os.listdir(modelscope_dir):
            print(f"[embed] 已有 ModelScope 缓存: {modelscope_dir}", flush=True)
            return modelscope_dir
        if _download_from_modelscope(model_name, modelscope_dir):
            return modelscope_dir

        # 尝试 2: HF-Mirror (huggingface_hub 缓存格式)
        hf_dir = _download_from_hf_mirror(model_name)
        if hf_dir:
            return hf_dir

        return None

    # --------------------------------------------------------
    # 懒加载
    # --------------------------------------------------------
    def _lazy_load(self):
        if self._model is not None:
            return

        spec = EMBEDDING_MODELS[0]
        if self._model_name:
            spec = next((m for m in EMBEDDING_MODELS if m["name"] == self._model_name), spec)

        # 尝试 1: fastembed (ONNX, ~30MB, 零深度学习依赖 — 首选)
        # HF_ENDPOINT 已在模块加载时设为 hf-mirror.com
        for attempt_spec in [spec, EMBEDDING_MODELS[2]]:
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(model_name=attempt_spec["name"])
                self._dim = attempt_spec["dim"]
                self._backend = "fastembed"
                self._active_spec = attempt_spec
                print(
                    f"[embed] 本地模型已加载 (fastembed): {attempt_spec['name']} "
                    f"({attempt_spec['size_mb']}MB, {self._dim}维)",
                    flush=True,
                )
                return
            except (ImportError, Exception) as e:
                print(f"[embed] fastembed 不可用: {e}", flush=True)
                continue

        # 尝试 2: sentence-transformers (Pytorch, ~1.2GB — 备选)
        # 先尝试本地下载模型，以便离线使用
        local_dir = self._download_model_locally(spec)
        for attempt_spec in [spec, EMBEDDING_MODELS[2]]:
            try:
                from sentence_transformers import SentenceTransformer
                model_path = local_dir if local_dir else attempt_spec["name"]
                self._model = SentenceTransformer(model_path)
                self._dim = attempt_spec["dim"]
                self._backend = "sentence_transformers"
                self._active_spec = attempt_spec
                print(
                    f"[embed] 本地模型已加载: {attempt_spec['name']} "
                    f"({attempt_spec['size_mb']}MB, {self._dim}维) 后端=sentence-transformers",
                    flush=True,
                )
                return
            except (ImportError, Exception) as e:
                print(f"[embed] sentence-transformers 不可用: {e}", flush=True)
                continue

        raise RuntimeError(
            "本地 embedding 不可用。请先安装依赖:\n"
            "  推荐: pip install fastembed          (ONNX, 零深度学习依赖, ~30MB)\n"
            "  备选: pip install sentence-transformers (Pytorch, 功能更全, ~1.2GB)\n"
        )

    # --------------------------------------------------------
    # 核心 API
    # --------------------------------------------------------
    def embed(self, text: str) -> List[float]:
        self._lazy_load()
        if self._backend == "sentence_transformers":
            return self._model.encode(
                text, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
        elif self._backend == "fastembed":
            return [float(v) for v in next(self._model.embed([text]))]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        self._lazy_load()
        if self._backend == "sentence_transformers":
            return self._model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
        elif self._backend == "fastembed":
            return [[float(v) for v in vec] for vec in self._model.embed(texts)]

    @property
    def dimension(self) -> int:
        self._lazy_load()
        return self._dim

    @property
    def backend_name(self) -> str:
        self._lazy_load()
        return self._backend


# ============================================================
# 全局单例
# ============================================================
_embedding_provider: Optional[LocalEmbeddingProvider] = None


def get_embedding_provider() -> Optional[LocalEmbeddingProvider]:
    global _embedding_provider

    if _embedding_provider is not None:
        return _embedding_provider

    use_cloud = os.getenv("ALPHAPILOT_EMBEDDING", "local").lower() in ("cloud", "api", "dashscope", "openai")

    if use_cloud:
        print("[embed] 配置使用云端 embedding (DashScope/OpenAI)", flush=True)
        return None

    try:
        _embedding_provider = LocalEmbeddingProvider()
        return _embedding_provider
    except RuntimeError as e:
        print(f"[embed] 本地 embedding 不可用: {e}", flush=True)
        print("[embed]    降级到云端 embedding (需配置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY)", flush=True)
        return None


def get_embedding_dimension() -> int:
    provider = get_embedding_provider()
    if provider is not None:
        return provider.dimension
    return 1536


def make_vector_str(embedding: List[float]) -> str:
    return "[" + ",".join(str(v) for v in embedding) + "]"