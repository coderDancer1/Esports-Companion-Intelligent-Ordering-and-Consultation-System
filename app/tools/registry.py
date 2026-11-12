"""工具注册表：登记名称/schema/所属 Agent/常驻或按需/实现。"""
from __future__ import annotations

from typing import Dict, List

from app.tools.definitions import (assess_emotion, check_action_eligibility,
                                   check_handoff_rules, create_handoff_ticket,
                                   get_playmate_detail, get_raw_messages,
                                   get_user_profile, load_skill, query_order,
                                   search_knowledge_base, search_playmates)
from app.skills.loader import get_catalog

# load_skill 的可选技能名从 SKILL.md 目录动态生成，保证与 system prompt 里的目录永远同步。
_SKILL_NAMES = sorted(get_catalog().keys())

# 常驻工具分层（公共 get_user_profile 全员常驻）
RESIDENT_TOOLS: Dict[str, List[str]] = {
    "recommend": ["search_playmates", "get_playmate_detail", "load_skill", "get_user_profile"],
    "order": ["query_order", "check_action_eligibility", "load_skill", "get_user_profile"],
    "complaint": ["assess_emotion", "check_handoff_rules", "create_handoff_ticket",
                  "load_skill", "get_user_profile"],
    "knowledge": ["search_knowledge_base", "load_skill", "get_user_profile"],
    "clarify": ["get_user_profile"],
    "human": ["create_handoff_ticket", "get_user_profile"],
    "chitchat": ["get_user_profile"],
}

TOOLS: Dict[str, dict] = {
    "search_playmates": {
        "run": search_playmates.run,
        "resident_for": ["recommend"],
        "on_demand": False,
        "schema": {"name": "search_playmates",
                   "description": "按结构化条件筛选陪玩师。game 用英文代码；rank 用中文段位名。"
                                  "务必把用户原始需求原样传入 semantic_query 以做语义排序。",
                   "input_schema": {"type": "object", "properties": {
                       "game": {"type": "string",
                                "enum": ["valorant", "lol", "delta", "pubg", "csgo"],
                                "description": "valorant=无畏契约, lol=英雄联盟, delta=三角洲行动, pubg=绝地求生, csgo=CS"},
                       "rank_min": {"type": "string",
                                    "enum": ["青铜", "白银", "黄金", "铂金", "钻石", "大师", "宗师", "王者", "神话", "无畏"]},
                       "rank_max": {"type": "string",
                                    "enum": ["青铜", "白银", "黄金", "铂金", "钻石", "大师", "宗师", "王者", "神话", "无畏"]},
                       "price_min": {"type": "integer"}, "price_max": {"type": "integer"},
                       "personality_tags": {"type": "array", "items": {"type": "string"}},
                       "online_only": {"type": "boolean"},
                       "semantic_query": {"type": "string"},
                       "limit": {"type": "integer"}}}},
    },
    "get_playmate_detail": {
        "run": get_playmate_detail.run, "resident_for": ["recommend"], "on_demand": False,
        "schema": {"name": "get_playmate_detail", "description": "获取陪玩师完整档案",
                   "input_schema": {"type": "object", "properties": {"playmate_id": {"type": "string"}},
                                    "required": ["playmate_id"]}},
    },
    "query_order": {
        "run": query_order.run, "resident_for": ["order"], "on_demand": False,
        "schema": {"name": "query_order", "description": "查询用户订单。order_id 从用户消息或上下文提取（纯数字）；"
                                                       "留空则返回该用户全部订单。",
                   "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}}},
    },
    "check_action_eligibility": {
        "run": check_action_eligibility.run, "resident_for": ["order"], "on_demand": False,
        "schema": {"name": "check_action_eligibility", "description": "判断订单操作是否可执行（只判断、绝不执行写操作）",
                   "input_schema": {"type": "object", "properties": {
                       "order_id": {"type": "string"},
                       "action": {"type": "string",
                                  "enum": ["refund", "cancel", "change_playmate", "reschedule"],
                                  "description": "refund=退款, cancel=取消, change_playmate=改派/换陪玩, reschedule=改期/改时间"},
                       "params": {"type": "object"}}, "required": ["order_id", "action"]}},
    },
    "assess_emotion": {
        "run": assess_emotion.run, "resident_for": ["complaint"], "on_demand": False,
        "schema": {"name": "assess_emotion", "description": "评估用户情绪强度与标签",
                   "input_schema": {"type": "object", "properties": {"message": {"type": "string"}},
                                    "required": ["message"]}},
    },
    "check_handoff_rules": {
        "run": check_handoff_rules.run, "resident_for": ["complaint"], "on_demand": False,
        "schema": {"name": "check_handoff_rules", "description": "确定性转人工规则校验",
                   "input_schema": {"type": "object", "properties": {"context": {"type": "object"}}}},
    },
    "create_handoff_ticket": {
        "run": create_handoff_ticket.run, "resident_for": ["complaint", "human"], "on_demand": False,
        "schema": {"name": "create_handoff_ticket", "description": "创建转人工工单",
                   "input_schema": {"type": "object", "properties": {
                       "type": {"type": "string"}, "summary": {"type": "string"},
                       "context_snapshot": {"type": "object"}}, "required": ["summary"]}},
    },
    "search_knowledge_base": {
        "run": search_knowledge_base.run, "resident_for": ["knowledge"], "on_demand": False,
        "schema": {"name": "search_knowledge_base", "description": "检索知识库",
                   "input_schema": {"type": "object", "properties": {
                       "query": {"type": "string"}, "topic": {"type": "string"}},
                       "required": ["query"]}},
    },
    "get_user_profile": {
        "run": get_user_profile.run, "resident_for": ["*"], "on_demand": False,
        "schema": {"name": "get_user_profile", "description": "获取用户画像",
                   "input_schema": {"type": "object", "properties": {}}},
    },
    "get_raw_messages": {
        "run": get_raw_messages.run, "resident_for": [], "on_demand": True,
        "schema": {"name": "get_raw_messages", "description": "按 message_id 回捞原文",
                   "input_schema": {"type": "object", "properties": {
                       "session_id": {"type": "string"},
                       "message_ids": {"type": "array", "items": {"type": "string"}}},
                       "required": ["session_id", "message_ids"]}},
    },
    "load_skill": {
        "run": load_skill.run, "resident_for": ["recommend", "order", "complaint", "knowledge"],
        "on_demand": False,
        "schema": {"name": "load_skill", "description": "加载指定技能的完整正文与依赖工具（渐进披露："
                                                        "技能目录常驻系统提示词，正文仅在需要时用本工具加载）。",
                   "input_schema": {"type": "object", "properties": {"skill_name": {"type": "string",
                                    "enum": _SKILL_NAMES}},
                                    "required": ["skill_name"]}},
    },
}


def get_tool(name: str):
    return TOOLS.get(name)


def get_resident_schemas(agent: str) -> List[dict]:
    names = RESIDENT_TOOLS.get(agent, ["get_user_profile"])
    return [TOOLS[n]["schema"] for n in names if n in TOOLS]
