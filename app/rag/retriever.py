"""混合检索：向量 + BM25 双路 → RRF 融合 → 重排 → 阈值过滤。"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.config import get_settings
from app.db.chroma_client import COLLECTION_KNOWLEDGE_BASE
from app.db.vector_store import get_vector_store
from app.llm.embedder import get_embedder
from app.rag.bm25 import BM25
from app.rag.indexer import get_bm25
from app.rag.reranker import rerank, rerank_threshold


class HybridRetriever:
    K = 60

    def __init__(self) -> None:
        self.settings = get_settings()

    async def retrieve(self, query: str, rerank_pool: int = 20, top_k: int = 5,
                       threshold: float = None) -> Tuple[List[Dict[str, Any]], bool]:
        """返回 (chunks, need_fallback)。空结果或低于阈值时 need_fallback=True。"""
        embedder = get_embedder()
        store = get_vector_store()

        # 1. 向量路 Top-30
        qv = embedder.embed(query)
        vec_res = store.query(COLLECTION_KNOWLEDGE_BASE, qv, n_results=30)
        vec_rank: Dict[str, int] = {}
        vec_meta: Dict[str, dict] = {}
        for ids, metas in zip(vec_res["ids"], vec_res["metadatas"]):
            for i, cid in enumerate(ids):
                vec_rank[cid] = i
                vec_meta[cid] = metas[i] if i < len(metas) else {}

        # 2. BM25 路 Top-30
        bm: BM25 = get_bm25()
        bm_rank: Dict[str, int] = {}
        for i, (cid, _score) in enumerate(bm.search(query, k=30)):
            bm_rank[cid] = i

        # 3. RRF 融合
        rrf_scores: Dict[str, float] = {}
        all_ids = set(vec_rank) | set(bm_rank)
        for cid in all_ids:
            s = 0.0
            if cid in vec_rank:
                s += 1.0 / (self.K + vec_rank[cid] + 1)
            if cid in bm_rank:
                s += 1.0 / (self.K + bm_rank[cid] + 1)
            rrf_scores[cid] = s
        fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:rerank_pool]

        # 组装候选 chunk
        candidates: List[dict] = []
        for cid, _ in fused:
            meta = vec_meta.get(cid, {})
            raw = meta.get("raw_text", meta.get("chunk_id", ""))
            title = " > ".join(meta.get("title_path") or [])
            candidates.append({
                "chunk_id": cid,
                "text": (f"{title}\n{raw}" if title else raw),
                "raw_text": raw,
                "doc_id": meta.get("doc_id", ""),
                "title_path": meta.get("title_path", []),
                "score": rrf_scores[cid],
            })
        if not candidates:
            return [], True

        # 4. 重排 Top-5
        ranked = rerank(query, candidates, top_k=top_k)
        # 5. 阈值过滤（阈值按有效重排后端自适应：语义 CrossEncoder / jieba 词覆盖度）
        if threshold is None:
            threshold = rerank_threshold()
        chunks = []
        for c, score in ranked:
            if score >= threshold:
                chunks.append({**c, "score": round(score, 4)})
        need_fallback = len(chunks) == 0
        return chunks, need_fallback
