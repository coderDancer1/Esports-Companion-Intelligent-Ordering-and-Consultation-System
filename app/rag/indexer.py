"""入库 pipeline：解析→切分→双写向量库 + BM25 版本目录；写 CURRENT 指针。"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import jieba

from app.config import get_settings
from app.db.chroma_client import COLLECTION_KNOWLEDGE_BASE
from app.db.mysql import session_scope
from app.db.models import KnowledgeDoc
from app.db.vector_store import get_vector_store
from app.rag.bm25 import BM25
from app.rag.chunker import chunk_sections

_DATA_DIR = os.path.join("data", "bm25_index")
_CORPUS_FILE = os.path.join(_DATA_DIR, "corpus.json")
_CURRENT_FILE = os.path.join(_DATA_DIR, "CURRENT")

# 全局内存语料 + 当前 BM25 索引
_corpus: List[Dict[str, Any]] = []
_current_index: Optional[BM25] = None


def load_domain_dict() -> None:
    path = os.path.join(os.path.dirname(__file__), "domain_dict.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for word in f:
                w = word.strip()
                if w:
                    jieba.add_word(w)


def _persist_corpus() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CORPUS_FILE, "w", encoding="utf-8") as f:
        json.dump(_corpus, f, ensure_ascii=False, indent=2)


def _write_current(version: str) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CURRENT_FILE, "w", encoding="utf-8") as f:
        f.write(version)


def rebuild_bm25() -> BM25:
    global _current_index
    idx = BM25()
    if _corpus:
        idx.index([c["chunk_id"] for c in _corpus], [c["index_text"] for c in _corpus])
    _current_index = idx  # 原子切换引用
    _write_current(str(int(time.time() * 1000)))
    return idx


def rebuild_knowledge_vectors() -> int:
    """从持久化语料重建 knowledge_base 向量（内存向量库不跨进程，需每次启动重建）。"""
    store = get_vector_store()
    store.delete(COLLECTION_KNOWLEDGE_BASE)
    for c in _corpus:
        store.upsert(
            COLLECTION_KNOWLEDGE_BASE,
            ids=[c["chunk_id"]],
            documents=[c["index_text"]],
            metadatas=[{
                "doc_id": c.get("doc_id", ""), "chunk_id": c["chunk_id"],
                "title_path": c.get("title_path", []), "raw_text": c.get("text", ""),
                "doc_parse_quality": c.get("quality", "high"),
            }],
        )
    return len(_corpus)


def get_bm25() -> BM25:
    global _current_index
    if _current_index is None:
        _current_index = rebuild_bm25()
    return _current_index


def load_index() -> None:
    """启动时加载持久化语料。"""
    global _corpus
    load_domain_dict()
    if os.path.exists(_CORPUS_FILE):
        try:
            with open(_CORPUS_FILE, "r", encoding="utf-8") as f:
                _corpus = json.load(f)
        except Exception:  # noqa: BLE001
            _corpus = []
    rebuild_bm25()
    rebuild_knowledge_vectors()


def _parse_content(filename: str, content: bytes) -> tuple[List[dict], str]:
    """按扩展名解析文档，返回 (sections, quality)。"""
    from app.rag.parsers import docx as docx_parser
    from app.rag.parsers import markdown as md_parser
    from app.rag.parsers import pdf as pdf_parser

    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext in ("md", "markdown", "txt"):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("gbk", errors="ignore")
        return md_parser.parse(text), "high"
    if ext == "pdf":
        return pdf_parser.parse(content)
    if ext in ("docx", "doc"):
        return docx_parser.parse(content)
    # 未知类型按纯文本
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="ignore")
    return md_parser.parse(text), "low"


def ingest_document(doc_id: str, title: str, filename: str, content: bytes) -> Dict[str, Any]:
    """入库单个文档，返回 {doc_id, chunks, status}。"""
    global _corpus
    sections, quality = _parse_content(filename, content)
    chunks = chunk_sections(doc_id, sections)

    # 写入向量库
    store = get_vector_store()
    for c in chunks:
        store.upsert(
            COLLECTION_KNOWLEDGE_BASE,
            ids=[c["chunk_id"]],
            documents=[c["index_text"]],
            metadatas=[{
                "doc_id": doc_id, "chunk_id": c["chunk_id"],
                "title_path": c["title_path"], "raw_text": c["text"],
                "doc_parse_quality": quality,
            }],
        )

    # 追加到语料 + 重建 BM25
    for c in chunks:
        _corpus.append({**c, "title": title, "quality": quality})
    _persist_corpus()
    rebuild_bm25()

    # 记录知识文档表
    version = _read_current()
    with session_scope() as db:
        existing = db.get(KnowledgeDoc, doc_id)
        if existing:
            existing.title = title
            existing.chunk_count = len(chunks)
            existing.doc_parse_quality = quality
            existing.index_version = version
        else:
            db.add(KnowledgeDoc(id=doc_id, title=title, source=filename,
                                doc_parse_quality=quality, index_version=version,
                                chunk_count=len(chunks)))

    return {"doc_id": doc_id, "chunks": len(chunks), "status": "indexed"}


def rebuild_all() -> Dict[str, Any]:
    """全量重建 BM25 索引（向量库已持久）。"""
    global _corpus
    rebuild_bm25()
    return {"chunks": len(_corpus), "version": _read_current(), "status": "done"}


def _read_current() -> str:
    if os.path.exists(_CURRENT_FILE):
        with open(_CURRENT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "0"


def corpus_size() -> int:
    return len(_corpus)
