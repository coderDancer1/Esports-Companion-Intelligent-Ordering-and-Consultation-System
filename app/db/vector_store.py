"""向量存储。

默认使用进程内向量库（余弦相似度 + metadata 过滤），无需安装 chromadb。
安装 chromadb 且配置 CHROMA_BACKEND=chroma 时切换为真实 Chroma（best-effort）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import json
import logging

from app.llm.embedder import get_embedder

# 彻底静音 Chroma 的遥测报错
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

def _matches(meta: Dict[str, Any], where: Optional[Dict[str, Any]]) -> bool:
    if not where:
        return True
    for k, v in where.items():
        if k not in meta:
            return False
        if isinstance(v, dict) and "$in" in v:
            if meta[k] not in v["$in"]:
                return False
        elif meta[k] != v:
            return False
    return True


class InMemoryVectorStore:
    """进程内向量存储，collection -> list[(id, emb, doc, meta)]。"""

    def __init__(self) -> None:
        self._cols: Dict[str, Dict[str, Any]] = {}

    def _col(self, name: str) -> Dict[str, Any]:
        return self._cols.setdefault(name, {"items": []})

    def upsert(self, collection: str, ids: List[str], documents: Optional[List[str]] = None,
               metadatas: Optional[List[Dict[str, Any]]] = None,
               embeddings: Optional[np.ndarray] = None) -> int:
        if embeddings is None:
            embeddings = get_embedder().embed_batch(documents or [""] * len(ids))
        docs = documents or [""] * len(ids)
        metas = metadatas or [{} for _ in ids]
        col = self._col(collection)
        idx = {item["id"]: i for i, item in enumerate(col["items"])}
        for i, cid in enumerate(ids):
            emb = np.asarray(embeddings[i], dtype=np.float32)
            norm = float(np.linalg.norm(emb))
            if norm > 1e-9:
                emb = emb / norm
            rec = {"id": cid, "emb": emb, "doc": docs[i], "meta": dict(metas[i])}
            if cid in idx:
                col["items"][idx[cid]] = rec
            else:
                col["items"].append(rec)
                idx[cid] = len(col["items"]) - 1
        return len(ids)

    def query(self, collection: str, query_embeddings: np.ndarray, n_results: int = 5,
              where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q = np.asarray(query_embeddings, dtype=np.float32)
        if q.ndim == 1:
            q = q[None, :]
        qn = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-9)
        col = self._col(collection)
        out_ids, out_docs, out_metas, out_sim = [], [], [], []
        for qv in qn:
            scored = []
            for item in col["items"]:
                if not _matches(item["meta"], where):
                    continue
                sim = float(np.dot(qv, item["emb"]))
                scored.append((sim, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:n_results]
            out_ids.append([s[1]["id"] for s in top])
            out_docs.append([s[1]["doc"] for s in top])
            out_metas.append([s[1]["meta"] for s in top])
            out_sim.append([s[0] for s in top])
        return {"ids": out_ids, "documents": out_docs, "metadatas": out_metas, "similarities": out_sim}

    def get(self, collection: str, ids: List[str]) -> Dict[str, Any]:
        col = self._col(collection)
        by_id = {item["id"]: item for item in col["items"]}
        out_ids, out_docs, out_metas = [], [], []
        for cid in ids:
            item = by_id.get(cid)
            if item is not None:
                out_ids.append(cid)
                out_docs.append(item["doc"])
                out_metas.append(item["meta"])
        return {"ids": out_ids, "documents": out_docs, "metadatas": out_metas}

    def count(self, collection: str) -> int:
        return len(self._col(collection)["items"])

    def delete(self, collection: str, ids: Optional[List[str]] = None) -> None:
        col = self._col(collection)
        if ids is None:
            col["items"] = []
        else:
            s = set(ids)
            col["items"] = [it for it in col["items"] if it["id"] not in s]


def _to_chroma_where(where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把内部 where 格式转成 Chroma 0.4.x 接受的格式。

    内部约定：多键表示 AND，值可为标量（相等）或 ``{"$in": [...]}``。
    而 Chroma 要求 where 顶层只能有且仅有一个键，多条件必须用 ``$and`` 包裹。
    """
    if not where:
        return None
    if len(where) == 1:
        # 单条件：{field: scalar} 或 {field: {"$in": [...]}} 均已被 Chroma 接受
        return where
    return {"$and": [{k: v} for k, v in where.items()]}


class ChromaVectorStore:
    """真实 Chroma 适配（best-effort，需安装 chromadb）。"""

    def __init__(self, path: str) -> None:
        import chromadb
        # 禁用遥测
        self._client = chromadb.PersistentClient(
            path=path,
            settings=chromadb.config.Settings(anonymized_telemetry=False)
        )
        # 当前向量维度：hash=256 / sentence_transformers=模型维度。切换后端会变维。
        self._dim = get_embedder().dim

    def _col(self, name: str):
        col = self._client.get_or_create_collection(
            name, metadata={"embedding_dim": str(self._dim)})
        md = col.metadata or {}
        if md.get("embedding_dim") and str(md["embedding_dim"]) != str(self._dim):
            # 向量维度变了（hash↔语义后端切换）→ 丢弃旧集合，按新维度重建
            return self._reset_col(name)
        return col

    def _reset_col(self, name: str):
        try:
            self._client.delete_collection(name)
        except Exception:  # noqa: BLE001
            pass
        return self._client.get_or_create_collection(
            name, metadata={"embedding_dim": str(self._dim)})

    def _is_dim_mismatch(self, err) -> bool:
        s = str(err).lower()
        return "dimension" in s or "dimensionality" in s

    def upsert(self, collection, ids, documents=None, metadatas=None, embeddings=None):
        col = self._col(collection)
        if embeddings is None:
            embeddings = get_embedder().embed_batch(documents or [""] * len(ids))
        # === 🚀 补丁：Chroma 不支持 list，把列表转成 JSON 字符串 ===
        safe_metadatas = []
        for meta in (metadatas or [{} for _ in ids]):
            safe_meta = {}
            for k, v in meta.items():
                if isinstance(v, list):
                    safe_meta[k] = json.dumps(v, ensure_ascii=False)
                else:
                    safe_meta[k] = v
            safe_metadatas.append(safe_meta)
        # =========================================================
        try:
            col.upsert(ids=ids, documents=documents, metadatas=safe_metadatas,
                       embeddings=embeddings.tolist())
        except Exception as e:  # noqa: BLE001
            if self._is_dim_mismatch(e):
                col = self._reset_col(collection)
                col.upsert(ids=ids, documents=documents, metadatas=safe_metadatas,
                           embeddings=embeddings.tolist())
            else:
                raise
        return len(ids)

    def query(self, collection, query_embeddings, n_results=5, where=None):
        col = self._col(collection)
        try:
            res = self._do_query(col, query_embeddings, n_results, where)
        except Exception as e:  # noqa: BLE001
            if self._is_dim_mismatch(e):
                col = self._reset_col(collection)
                res = self._do_query(col, query_embeddings, n_results, where)
            else:
                raise
        return res

    def _do_query(self, col, query_embeddings, n_results=5, where=None):
        res = col.query(query_embeddings=np.asarray(query_embeddings).tolist(),
                        n_results=n_results, where=_to_chroma_where(where),
                        include=["documents", "metadatas", "distances"])

        # === 🚀 修复：把 title_path 从 JSON 字符串还原成 list ===
        if "metadatas" in res and res["metadatas"]:
            for meta_batch in res["metadatas"]:
                for meta in meta_batch:
                    if "title_path" in meta and isinstance(meta["title_path"], str):
                        try:
                            meta["title_path"] = json.loads(meta["title_path"])
                        except Exception:
                            pass
        # =======================================================

        sims = [[1.0 - d for d in batch] for batch in res["distances"]]
        res["similarities"] = sims
        return res

    def get(self, collection, ids):
        col = self._col(collection)
        res = col.get(ids=ids, include=["documents", "metadatas"])

        # === 🚀 同样在这里还原 list ===
        if "metadatas" in res and res["metadatas"]:
            for meta in res["metadatas"]:
                if "title_path" in meta and isinstance(meta["title_path"], str):
                    try:
                        meta["title_path"] = json.loads(meta["title_path"])
                    except Exception:
                        pass
        # =======================================================
        return res

    def count(self, collection):
        return self._col(collection).count()

    def delete(self, collection, ids=None):
        col = self._col(collection)
        if ids is None:
            self._client.delete_collection(collection)
        else:
            col.delete(ids=ids)


_store: Optional[Any] = None


def get_vector_store():
    global _store
    if _store is None:
        from app.config import get_settings

        s = get_settings()
        backend = getattr(s, "CHROMA_BACKEND", "memory")
        if backend == "chroma":
            try:
                _store = ChromaVectorStore(s.CHROMA_PATH)
                return _store
            except Exception:
                pass
        _store = InMemoryVectorStore()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None
