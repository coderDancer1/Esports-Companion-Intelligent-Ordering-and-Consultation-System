"""知识问答专家：通道 A 前置 RAG；need_fallback 时明示未找到 + 转人工入口。"""
from __future__ import annotations

from typing import Dict

from app.orchestrator.experts.base import result
from app.orchestrator.log_writer import write_rag_log
from app.rag.retriever import HybridRetriever


async def knowledge_expert(ctx) -> Dict:
    chunks, need_fallback = await HybridRetriever().retrieve(ctx.message)
    write_rag_log(ctx.session_id, "A", ctx.message, [c.get("score", 0.0) for c in chunks],
                  need_fallback)

    if need_fallback or not chunks:
        return result("没有找到相关说明，可以帮你转人工客服咨询。")

    lines = []
    for c in chunks[:3]:
        title = " > ".join(c.get("title_path") or []) or "平台说明"
        lines.append(f"{title}：{c['text'][:200]}")
    facts_text = "\n".join(lines)
    reply = "根据平台说明，为你找到以下信息：\n" + "\n".join(f"· {l}" for l in lines)
    return result(reply, facts={"检索到的说明": facts_text})
