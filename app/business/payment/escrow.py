"""资金托管：支付→冻结→结算→提现四步，每步记录流水。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import PaymentFlow, now


def _flow(db: Session, order_id: str, flow_type: str, amount_fen: int,
          from_status: str, to_status: str) -> None:
    db.add(PaymentFlow(
        order_id=order_id, flow_type=flow_type, amount_fen=amount_fen,
        from_status=from_status, to_status=to_status, created_at=now(),
    ))


def freeze(db: Session, order_id: str, amount_fen: int) -> None:
    """支付后冻结到平台托管账户。"""
    _flow(db, order_id, "freeze", amount_fen, "paid", "frozen")


def settle(db: Session, order_id: str, amount_fen: int) -> None:
    """结算：解冻并结算给陪玩师。"""
    _flow(db, order_id, "settle", amount_fen, "frozen", "settled")


def refund(db: Session, order_id: str, amount_fen: int) -> None:
    """退款：退回用户。"""
    _flow(db, order_id, "refund", amount_fen, "frozen", "refunded")
