"""递归切分：chunk_size=500/overlap=80/中文分隔符；拼接标题路径生成索引文本。"""
from __future__ import annotations

from typing import List

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
_SEP = ["\n\n", "\n", "。", "！", "？", "；", "，"]


def _split_long(text: str, size: int) -> List[str]:
    """对超长段落按中文分隔符切分。"""
    parts: List[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？；\n" and len(buf) >= size // 2:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    units: List[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            units.append(para)
        else:
            units.extend(_split_long(para, chunk_size))

    chunks: List[str] = []
    cur = ""
    for u in units:
        if len(cur) + len(u) + 1 <= chunk_size:
            cur = f"{cur}\n{u}" if cur else u
        else:
            if cur:
                chunks.append(cur)
            while len(u) > chunk_size:
                chunks.append(u[:chunk_size])
                u = u[chunk_size - overlap:]
            cur = u
    if cur:
        chunks.append(cur)
    return chunks


def chunk_sections(doc_id: str, sections: List[dict]) -> List[dict]:
    """将解析出的 sections 切分为 chunk，并生成索引文本。"""
    chunks: List[dict] = []
    idx = 0
    for sec in sections:
        title_path = sec.get("title_path") or []
        for piece in split_text(sec.get("text", "")):
            index_text = ((" > ".join(title_path) + "\n") if title_path else "") + piece
            chunks.append({
                "chunk_id": f"{doc_id}:{idx}",
                "doc_id": doc_id,
                "title_path": title_path,
                "text": piece,
                "index_text": index_text,
            })
            idx += 1
    return chunks
