"""文本向量化封装。

默认使用零依赖的哈希向量（jieba 分词 + hashing trick + L2 归一化），
余弦相似度近似于词面重叠，足以支撑 demo 期的意图路由与 RAG 双路检索。
配置 EMBEDDING_BACKEND=sentence_transformers 时切换到 BGE 模型。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import List

import numpy as np

from app.config import apply_hf_offline, get_settings

logger = logging.getLogger("app.embedder")

_DIM = 256

# sentence-transformers 懒加载句柄
_st_model = None
_st_failed = False


def _tokenize(text: str) -> List[str]:
    import jieba  # 惰性导入，避免启动开销

    text = (text or "").lower().strip()
    words = [w.strip() for w in jieba.cut(text, cut_all=False) if w.strip()]
    # 叠加二元字符组，提升对短语/未登录词的召回
    chars = re.sub(r"\s+", "", text)
    bigrams = [chars[i:i + 2] for i in range(len(chars) - 1)]
    return words + bigrams


def hash_embed(text: str) -> np.ndarray:
    """哈希技巧 bag-of-words，返回 L2 归一化向量。"""
    vec = np.zeros(_DIM, dtype=np.float32)
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % _DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec = vec / norm
    return vec


def hash_embed_batch(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, _DIM), dtype=np.float32)
    return np.stack([hash_embed(t) for t in texts])


class Embedder:
    """统一向量化入口，内部按配置选择后端。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend = self.settings.EMBEDDING_BACKEND

    @property
    def dim(self) -> int:
        if self.backend == "sentence_transformers":
            return self._st_dim()
        return _DIM

    def _st_dim(self) -> int:
        m = self._st_model()
        return int(m.get_sentence_embedding_dimension()) if m else _DIM

    def _st_model(self):
        global _st_model, _st_failed
        if _st_model is None and not _st_failed:
            if self.settings.HF_ENDPOINT:
                os.environ.setdefault("HF_ENDPOINT", self.settings.HF_ENDPOINT)
            apply_hf_offline()
            try:
                from sentence_transformers import SentenceTransformer
                _st_model = SentenceTransformer(self.settings.EMB_MODEL)
                logger.info("语义向量后端已加载：%s（dim=%s）", self.settings.EMB_MODEL,
                            _st_model.get_sentence_embedding_dimension())
            except Exception as e:  # noqa: BLE001
                _st_failed = True
                _st_model = None
                logger.warning(
                    "sentence_transformers 加载失败，已回落哈希向量（有效后端=hash，阈值将按哈希后端适配）。"
                    "原因：%s", e)
        return _st_model

    def embed(self, text: str) -> np.ndarray:
        if self.backend == "sentence_transformers":
            m = self._st_model()
            if m is not None:
                return np.asarray(m.encode(text, normalize_embeddings=True), dtype=np.float32)
        return hash_embed(text)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        if self.backend == "sentence_transformers":
            m = self._st_model()
            if m is not None:
                return np.asarray(m.encode(texts, normalize_embeddings=True), dtype=np.float32)
        return hash_embed_batch(texts)


_embedder = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """已归一化向量间的余弦相似度。"""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if a.ndim == 1 and b.ndim == 1:
        return float(np.dot(a, b))
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def effective_backend() -> str:
    """实际生效的向量后端：配置为 sentence_transformers 但加载失败时回落 hash。

    防止「语义阈值 + 哈希向量」的静默死区——embedding 层据此选阈值，
    向量库据此判维度。"""
    e = get_embedder()
    if e.backend == "sentence_transformers" and e._st_model() is not None:
        return "sentence_transformers"
    return "hash"


def embedding_thresholds() -> "tuple[float, float]":
    """返回与 effective_backend 匹配的 (abs_threshold, margin)。"""
    s = get_settings()
    if effective_backend() == "sentence_transformers":
        return (s.EMB_ABS_THRESHOLD, s.EMB_MARGIN)
    return (s.EMB_HASH_ABS_THRESHOLD, s.EMB_HASH_MARGIN)


def example_match_threshold() -> float:
    """与 few-shot 样例逐条相似度的判定阈值（比质心阈值更严格）。"""
    return 0.80 if effective_backend() == "sentence_transformers" else 0.45
