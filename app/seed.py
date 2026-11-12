"""演示数据：用户、陪玩师、订单、知识库文档。首次启动自动填充。"""
from __future__ import annotations

from typing import Dict

from app.business.playmate.service import upsert_playmate
from app.db.mysql import session_scope
from app.db.models import Order, Playmate, User
from app.matching.profile_index import rebuild as rebuild_playmates
from app.rag.indexer import ingest_document

_KNOWLEDGE = {
    "doc_001": ("陪玩收费规则", "收费规则.md",
                "# 陪玩收费规则\n\n## 计价方式\n- 按小时计费，不同游戏、段位、陪玩师定价不同。\n"
                "- 无畏契约陪玩参考价：白银 30 元/时起，钻石 50-70 元/时，大师及以上 80 元/时起。\n"
                "- 英雄联盟陪玩参考价：钻石 55 元/时起，大师 88 元/时起。\n\n## 支付与托管\n"
                "- 下单后资金进入平台托管，服务完成并验收后结算给陪玩师。\n"
                "- 平台收取 20% 服务费。\n"),
    "doc_002": ("退款规则", "退款规则.md",
                "# 退款规则\n\n## 可无损退款\n- 订单处于待支付、已支付、待接单状态时可全额退款。\n"
                "- 退款金额按整数分计算，原路退回。\n\n## 需人工核实\n- 服务已开始（服务中/待验收）或已完成后退款，需人工核实。\n"
                "- 涉及金额争议的退款走人工工单。\n"),
    "doc_003": ("未成年人保护", "未成年人保护.md",
                "# 未成年人保护\n\n- 未成年人禁止下单、充值、打赏。\n"
                "- 未成年人禁止注册为陪玩师。\n- 平台对疑似未成年人要求实名认证。\n"),
}


def _already_seeded() -> bool:
    with session_scope() as db:
        return db.get(User, "u_1001") is not None


def seed_demo_data() -> Dict:
    if _already_seeded():
        return {"seeded": False}

    # 用户
    with session_scope() as db:
        db.add(User(id="u_1001", nickname="测试用户", is_minor=False,
                    realname_verified=True, member_level=1))
        db.add(User(id="u_2001", nickname="未成年测试", is_minor=True,
                    realname_verified=True, member_level=0))

    # 陪玩师
    playmates = [
        {"id": "p_2001", "nickname": "夜刃", "game": "valorant", "rank": "钻石",
         "price_per_hour": 68, "personality_tags": ["温柔", "教学向"],
         "heroes": ["捷风", "芮娜"], "intro": "主打教学向，温柔耐心", "rating": 4.9,
         "order_count": 128, "ontime_rate": 0.98, "online_status": True},
        {"id": "p_2002", "nickname": "小鹿", "game": "valorant", "rank": "铂金",
         "price_per_hour": 45, "personality_tags": ["温柔", "搞笑"],
         "heroes": ["贤者"], "intro": "气氛担当，带你快乐上分", "rating": 4.8,
         "order_count": 86, "ontime_rate": 0.97, "online_status": True},
        {"id": "p_2003", "nickname": "战鹰", "game": "lol", "rank": "大师",
         "price_per_hour": 88, "personality_tags": ["技术", "带飞"],
         "heroes": ["盲僧", "卡莎"], "intro": "高分段大腿，稳定带飞", "rating": 4.95,
         "order_count": 210, "ontime_rate": 0.99, "online_status": True},
        {"id": "p_2004", "nickname": "甜心", "game": "lol", "rank": "钻石",
         "price_per_hour": 55, "personality_tags": ["温柔", "奶音"],
         "heroes": ["璐璐", "悠米"], "intro": "软辅专精，声音好听", "rating": 4.85,
         "order_count": 74, "ontime_rate": 0.96, "online_status": True},
        {"id": "p_2005", "nickname": "猎手", "game": "delta", "rank": "钻石",
         "price_per_hour": 60, "personality_tags": ["带飞", "心态好"],
         "heroes": ["突击"], "intro": "三角洲老玩家，心态稳", "rating": 4.9,
         "order_count": 95, "ontime_rate": 0.98, "online_status": False},
        {"id": "p_2006", "nickname": "静音", "game": "valorant", "rank": "白银",
         "price_per_hour": 30, "personality_tags": ["教学"],
         "heroes": ["零"], "intro": "新手教学向", "rating": 4.6,
         "order_count": 32, "ontime_rate": 0.95, "online_status": True},
    ]
    for p in playmates:
        upsert_playmate(p)
    rebuild_playmates(playmates)

    # 订单
    with session_scope() as db:
        db.add(Order(id="202611080001", user_id="u_1001", playmate_id="p_2001", game="valorant",
                     amount_fen=6800, status="待接单", escrow_status="frozen"))
        db.add(Order(id="202611080002", user_id="u_1001", playmate_id="p_2003", game="lol",
                     amount_fen=8800, status="服务中", escrow_status="frozen"))
        db.add(Order(id="202611080003", user_id="u_1001", playmate_id="p_2002", game="valorant",
                     amount_fen=4500, status="已完成", escrow_status="settled"))

    # 知识库
    for doc_id, (title, filename, content) in _KNOWLEDGE.items():
        ingest_document(doc_id, title, filename, content.encode("utf-8"))

    return {"seeded": True, "users": 2, "playmates": len(playmates),
            "orders": 3, "knowledge_docs": len(_KNOWLEDGE)}
