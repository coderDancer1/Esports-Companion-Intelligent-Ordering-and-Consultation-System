"""订单状态机：合法迁移表，非法迁移抛 InvalidTransitionError。

纯 Python 实现，语义与 sqlalchemy-state-machine 一致（该包对 Windows/Python3.9
无 wheel，故内置等价实现）。取消由 domain service 按规则单独处理，不进通用迁移表。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


class InvalidTransitionError(Exception):
    pass


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    name: str


class StateMachine:
    state_field = "status"
    transitions: List[Transition] = []

    @classmethod
    def can_transition(cls, source: str, name: str) -> bool:
        return any(t.source == source and t.name == name for t in cls.transitions)

    @classmethod
    def target(cls, source: str, name: str) -> str:
        for t in cls.transitions:
            if t.source == source and t.name == name:
                return t.target
        raise InvalidTransitionError(f"illegal transition {name!r} from {source!r}")

    @classmethod
    def apply(cls, order, name: str) -> str:
        source = getattr(order, cls.state_field)
        target = cls.target(source, name)
        setattr(order, cls.state_field, target)
        return target


class OrderSM(StateMachine):
    state_field = "status"
    transitions = [
        Transition("待支付", "已支付", "pay"),
        Transition("已支付", "待接单", "escrow_hold"),
        Transition("待接单", "服务中", "accept"),
        Transition("服务中", "待验收", "deliver"),
        Transition("待验收", "已完成", "confirm"),
        Transition("服务中", "售后中", "raise_after_sales"),
        Transition("售后中", "已关闭", "resolve"),
    ]
