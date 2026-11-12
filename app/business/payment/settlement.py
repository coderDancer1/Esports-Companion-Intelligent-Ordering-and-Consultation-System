"""分账结算：平台抽成、陪玩师结算规则、对账接口。"""
from __future__ import annotations

PLATFORM_COMMISSION_RATE = 0.20  # 平台抽成 20%


def platform_fee(amount_fen: int) -> int:
    return int(amount_fen * PLATFORM_COMMISSION_RATE)


def playmate_payout(amount_fen: int) -> int:
    return amount_fen - platform_fee(amount_fen)


def reconcile(order_amount_fen: int) -> dict:
    """对账：返回平台/陪玩师分账明细。"""
    return {
        "total_fen": order_amount_fen,
        "platform_fen": platform_fee(order_amount_fen),
        "playmate_fen": playmate_payout(order_amount_fen),
    }
