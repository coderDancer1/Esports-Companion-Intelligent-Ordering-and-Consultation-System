"""重排封装：bge-reranker-v2-m3（best-effort）；降级为哈希向量余弦 + 裁剪。"""
from __future__ import annotations

from typing import List, Tuple

import logging

from app.config import apply_hf_offline, get_settings

logger = logging.getLogger("app.reranker")

_reranker = None
_reranker_failed = False


def _get_reranker():
    global _reranker, _reranker_failed
    if _reranker is None and not _reranker_failed:
        try:
            apply_hf_offline()
            from sentence_transformers import CrossEncoder
            model_name = get_settings().RERANK_MODEL
            # 大模型（约 1GB）首次会触发下载，可能耗时数分钟——明确打日志，避免"静默卡住"。
            logger.info("重排模型加载中：%s（首次需下载，可能较慢）", model_name)
            _reranker = CrossEncoder(model_name)
            logger.info("重排模型加载完成：%s", model_name)
        except Exception as e:  # noqa: BLE001
            _reranker_failed = True
            logger.warning("重排模型加载失败，已回退到 jieba 词覆盖度打分。原因：%s", e)
    return _reranker


def rerank(query: str, chunks: List[dict], top_k: int = 5) -> List[Tuple[dict, float]]:
    """对候选 chunks 打分并排序，返回 (chunk, score)，score 归一化到 [0,1]。"""
    if not chunks:
        return []
    model = _get_reranker()
    if model is not None:
        try:
            pairs = [(query, c.get("text", "")) for c in chunks]
            scores = model.predict(pairs)
            ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]
            # bge-reranker-v2-m3 输出的已是 [0,1] 的相关度 logit（无关≈0、相关≈0.5~0.9），
            # 直接截断到 [0,1] 使用即可。若再套 sigmoid 会把 [0,1] 压到 [0.5,0.73]，
            # 毁掉「无关 0.5 vs 相关 0.6~0.7」的分隔，导致域外查询全部误判为命中。
            return [(c, float(min(1.0, max(0.0, s)))) for c, s in ranked]
        except Exception:  # noqa: BLE001
            pass
    # 降级：查询词覆盖度（短查询 vs 长文档时比余弦更稳定）
    import jieba
    qt = {w for w in jieba.cut(query) if w.strip()}
    scored = []
    for c in chunks:
        tt = {w for w in jieba.cut(c.get("text", "")) if w.strip()}
        overlap = (len(qt & tt) / len(qt)) if qt else 0.0
        scored.append((c, min(1.0, overlap)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def effective_reranker_backend() -> str:
    """当前重排后端：semantic（CrossEncoder 加载成功）| jieba（降级）。"""
    return "semantic" if _get_reranker() is not None else "jieba"


def rerank_threshold() -> float:
    """按有效重排后端取阈值：语义 CrossEncoder 用原始 logit 阈值，jieba 降级用词覆盖度阈值。"""
    s = get_settings()
    if effective_reranker_backend() == "semantic":
        return s.RERANK_SEMANTIC_THRESHOLD
    return s.RERANK_THRESHOLD
