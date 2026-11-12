"""工具：通道 B Agentic RAG，包装 HybridRetriever，返回 chunks+need_fallback。"""
from __future__ import annotations

from typing import Optional

from app.orchestrator.log_writer import write_rag_log
from app.rag.retriever import HybridRetriever
from app.tools.errors import ToolResult, empty, error, success


async def run(ctx, query: str, topic: Optional[str] = None) -> ToolResult:
    try:
        retriever = HybridRetriever()
        chunks, need_fallback = await retriever.retrieve(query)
        # 采集弱信号：无论命中与否都落 rag_log，need_fallback 供数据飞轮发现知识库缺口
        write_rag_log(ctx.session_id, "B", query,
                      [c.get("score", 0.0) for c in chunks], need_fallback)
        if need_fallback or not chunks:
            return empty({"chunks": [], "need_fallback": True})
        return success({"chunks": chunks, "need_fallback": False})
    except Exception as e:  # noqa: BLE001
        return error("kb_search_failed", str(e))
