"""压缩：token 阈值触发 → Redis 分布式锁 → 异步执行摘要 + 画像更新 + 重建 List。"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List

from app.config import get_settings
from app.db.lock import RedisLock
from app.db.mysql import session_scope
from app.db.models import CompressionLog
from app.llm.client import complete, is_llm_available
from app.llm.token_counter import estimate_messages
from app.memory import profile_extractor
from app.memory import short_term
from app.memory.compressed_store import upsert as upsert_summary
from app.memory.compressed_store import get_latest


async def maybe_compress(session_id: str, user_id: str) -> None:
    """检查 token 阈值，超限则异步触发压缩（不阻塞本轮）。"""
    s = get_settings()
    msgs = short_term.get_all(session_id)
    est = estimate_messages(msgs)
    short_term.update_meta(session_id, {"token_est": est})
    if est < s.WINDOW_TOKENS * s.COMPRESS_TRIGGER_RATIO:
        return
    asyncio.create_task(_do_compress(session_id, user_id))


async def _do_compress(session_id: str, user_id: str) -> None:
    s = get_settings()
    lock = RedisLock(f"compress_lock:{session_id}", ttl=s.COMPRESS_LOCK_TTL)
    if not await lock.acquire():
        return
    try:
        msgs = short_term.get_all(session_id)
        if len(msgs) <= s.COMPRESS_KEEP_ROUNDS:
            return
        keep = msgs[-s.COMPRESS_KEEP_ROUNDS:]
        to_compress = msgs[:-s.COMPRESS_KEEP_ROUNDS]
        prev = get_latest(user_id, session_id)
        summary = await _summarize(to_compress, prev)
        await profile_extractor.update(user_id, to_compress)
        upsert_summary(user_id, session_id, summary)
        short_term.rebuild_with_summary(session_id, summary, keep)
        short_term.update_meta(session_id, {"token_est": estimate_messages([{"role": "summary", "content": summary}])})
        _write_log(session_id, user_id, len(to_compress), summary)
    finally:
        await lock.release()


async def _summarize(messages: List[Dict[str, Any]], prev: str) -> str:
    if is_llm_available():
        convo = "\n".join(f"{m.get('role')}: {m.get('content','')}" for m in messages)
        prompt = (
            "压缩以下对话为 200-400 字摘要。保留：用户偏好、关键实体、已确认结论、"
            "用户更正、工具失败。丢弃：寒暄、重复确认、过时信息。"
            "金额/订单号/状态必须抽取式保留，禁止改写。\n\n"
            f"历史摘要：{prev}\n\n对话：\n{convo}"
        )
        resp = await complete([{"role": "user", "content": prompt}], max_tokens=600)
        if resp.get("content"):
            return resp["content"].strip()
    return _extractive_summary(messages, prev)


def _extractive_summary(messages: List[Dict[str, Any]], prev: str) -> str:
    text = "\n".join(m.get("content", "") for m in messages if m.get("content"))
    entities: List[str] = []
    order_ids = set(re.findall(r"\b\d{8,20}\b", text))
    for oid in list(order_ids)[:3]:
        entities.append(f"订单号:{oid}")
    amounts = set(re.findall(r"\d+\s*(?:元|块)", text))
    for a in list(amounts)[:3]:
        entities.append(f"金额:{a}")
    head = text[:240]
    parts = [f"[前情]{prev}"] if prev else []
    parts.append(head)
    if entities:
        parts.append("关键信息:" + "；".join(entities))
    return " ".join(parts)[:400]


def _write_log(session_id: str, user_id: str, token_before: int, summary: str) -> None:
    try:
        with session_scope() as db:
            db.add(CompressionLog(
                session_id=session_id, user_id=user_id, token_before=token_before,
                token_after=estimate_messages([{"role": "summary", "content": summary}]),
                summary_len=len(summary), trigger_reason="window_ratio",
            ))
    except Exception:  # noqa: BLE001
        pass
