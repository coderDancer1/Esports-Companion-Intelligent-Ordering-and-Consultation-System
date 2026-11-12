"""全部 ORM 表定义（对应文档 §15 日志表与 §13 业务表）。

此处为统一表定义，business 层复用同一批模型。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    is_minor: Mapped[bool] = mapped_column(Boolean, default=False)
    realname_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    member_level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    playmate_id: Mapped[str] = mapped_column(String(64), default="")
    game: Mapped[str] = mapped_column(String(32), default="")
    amount_fen: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="待支付", index=True)
    escrow_status: Mapped[str] = mapped_column(String(32), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class OrderTransition(Base):
    __tablename__ = "order_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    from_status: Mapped[str] = mapped_column(String(16), default="")
    to_status: Mapped[str] = mapped_column(String(16), default="")
    action: Mapped[str] = mapped_column(String(32), default="")
    actor: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PaymentFlow(Base):
    __tablename__ = "payment_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_type: Mapped[str] = mapped_column(String(32), default="")  # freeze/unfreeze/settle/refund
    amount_fen: Mapped[int] = mapped_column(Integer, default=0)
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    type: Mapped[str] = mapped_column(String(32), default="general")  # complaint/after_sales/general
    status: Mapped[str] = mapped_column(String(16), default="pending")
    summary: Mapped[str] = mapped_column(Text, default="")
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Playmate(Base):
    __tablename__ = "playmates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    game: Mapped[str] = mapped_column(String(32), index=True)
    rank: Mapped[str] = mapped_column(String(32), default="")
    price_per_hour: Mapped[int] = mapped_column(Integer, default=0)
    personality_tags: Mapped[list] = mapped_column(JSON, default=list)
    heroes: Mapped[list] = mapped_column(JSON, default=list)
    intro: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    ontime_rate: Mapped[float] = mapped_column(Float, default=1.0)
    online_status: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    doc_parse_quality: Mapped[str] = mapped_column(String(16), default="high")
    index_version: Mapped[str] = mapped_column(String(64), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class RouteLog(Base):
    __tablename__ = "route_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    intent: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    route_source: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(String(255), default="")
    handoff_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_clarify_at_turn: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ToolLog(Base):
    __tablename__ = "tool_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    agent: Mapped[str] = mapped_column(String(32), default="")
    tool_name: Mapped[str] = mapped_column(String(64), default="")
    params_digest: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CompressionLog(Base):
    __tablename__ = "compression_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="")
    token_before: Mapped[int] = mapped_column(Integer, default=0)
    token_after: Mapped[int] = mapped_column(Integer, default=0)
    summary_len: Mapped[int] = mapped_column(Integer, default=0)
    trigger_reason: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class RagLog(Base):
    __tablename__ = "rag_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="")  # A / B
    query: Mapped[str] = mapped_column(Text, default="")
    top_k_scores: Mapped[list] = mapped_column(JSON, default=list)
    need_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class HandoffLog(Base):
    __tablename__ = "handoff_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger_rule: Mapped[str] = mapped_column(String(64), default="")
    ticket_id: Mapped[str] = mapped_column(String(64), default="")
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Feedback(Base):
    """用户对某一轮答复的显式反馈（数据飞轮的采集入口）。"""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text, default="")       # 回捞的原始用户输入
    intent: Mapped[str] = mapped_column(String(32), default="")  # 该轮路由出的意图
    rating: Mapped[int] = mapped_column(Integer, default=0)      # +1 好 / 0 中性 / -1 差
    category: Mapped[str] = mapped_column(String(32), default="")  # intent/grounding/knowledge_gap/other
    correction: Mapped[str] = mapped_column(Text, default="")    # 用户纠错文本（可选）
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/reviewed/ignored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
