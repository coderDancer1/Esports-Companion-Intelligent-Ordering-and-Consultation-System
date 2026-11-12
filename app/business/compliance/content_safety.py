"""内容安全：敏感词过滤、情绪评估、防飞单监控。"""
from __future__ import annotations

from typing import Dict, List

# 防飞单 / 风险交易敏感词
_SENSITIVE = [
    "私下交易", "加微信", "加vx", "加v", "微信转账", "支付宝", "扫码付款",
    "线下", "绕过平台", "私下", "银行卡转账", "qq红包",
]

# 情绪标签词表
_ANGER = ["投诉", "举报", "退款", "太差", "恶心", "欺骗", "态度", "差评", "气死", "垃圾", "坑", "骂"]
_STRONG_ANGER = ["恶心", "欺骗", "气死", "垃圾", "坑", "滚", "骗子"]


def check_sensitive(text: str) -> List[str]:
    return [w for w in _SENSITIVE if w in text]


def assess_emotion(message: str) -> Dict:
    """评估情绪强度与标签。"""
    labels: List[str] = []
    intensity = 0.0
    if any(w in message for w in _STRONG_ANGER):
        intensity = 0.9
        labels.append("强烈不满")
    elif any(w in message for w in _ANGER):
        intensity = 0.6
        labels.append("不满")
    else:
        intensity = 0.1
        labels.append("平静")
    return {"intensity": intensity, "labels": labels}


def monitor_off_platform(message: str) -> Dict:
    """防飞单监控（异步触发；此处同步返回命中结果）。"""
    hits = check_sensitive(message)
    return {"risk": bool(hits), "hits": hits}
