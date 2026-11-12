"""Embedding 层：样例编码缓存；短输入+指代词时拼上轮 user 消息；top1 判定。"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.intent.examples import EXAMPLES
from app.llm.embedder import embedding_thresholds, get_embedder

PRONOUNS = {"这个", "那个", "它", "它们", "第1个", "第一个", "第2个", "第二个",
            "上面那个", "刚才那个", "这款", "那位", "他", "她", "这个呢", "那个呢"}

_INTENTS = ["recommend", "order", "complaint", "knowledge", "chitchat", "human"]


def build_query(message: str, recent: Optional[List[dict]]) -> str:
    if recent and len(message) < 10 and any(p in message for p in PRONOUNS):
        for m in reversed(recent):
            if m.get("role") == "user":
                return f"{m.get('content', '')} {message}"
    return message


class EmbeddingRouter:
    def __init__(self) -> None:
        self._centroids: Optional[Dict[str, np.ndarray]] = None

    def _build_cache(self) -> Dict[str, np.ndarray]:
        emb = get_embedder()
        centroids: Dict[str, np.ndarray] = {}
        for intent in _INTENTS:
            vecs = emb.embed_batch(EXAMPLES.get(intent, []))
            if len(vecs):
                c = vecs.mean(axis=0)
                n = float(np.linalg.norm(c))
                centroids[intent] = c / n if n > 1e-9 else c
        return centroids

    def reload(self) -> None:
        self._centroids = self._build_cache()

    def _cache(self) -> Dict[str, np.ndarray]:
        if self._centroids is None:
            self._centroids = self._build_cache()
        return self._centroids

    async def classify(self, message: str, recent: Optional[List[dict]] = None):
        query = build_query(message, recent)
        qv = get_embedder().embed(query)
        centroids = self._cache()
        scored = []
        for intent in _INTENTS:
            c = centroids.get(intent)
            if c is None:
                continue
            sim = float(np.dot(qv, c))
            scored.append((intent, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            return None
        top1_intent, top1 = scored[0]
        top2 = scored[1][1] if len(scored) > 1 else 0.0
        abs_th, margin = embedding_thresholds()
        if top1 >= abs_th and (top1 - top2) >= margin:
            from app.intent.route_decision import RouteDecision
            return RouteDecision(intent=top1_intent, confidence=round(top1, 3),
                                 reason="embedding", route_source="embedding")
        return None

    def top_intents(self, message: str, recent: Optional[List[dict]] = None, k: int = 2) -> List[str]:
        query = build_query(message, recent)
        qv = get_embedder().embed(query)
        scored = sorted(((i, float(np.dot(qv, c))) for i, c in self._cache().items()),
                        key=lambda x: x[1], reverse=True)
        return [i for i, _ in scored[:k]]
