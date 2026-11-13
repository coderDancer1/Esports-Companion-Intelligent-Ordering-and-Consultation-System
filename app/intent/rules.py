"""规则层：按优先级排列的关键词/正则模式，仅匹配当前输入。"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import jieba

_GAMES = "英雄联盟|无畏契约|三角洲行动|绝地求生|lol|valorant|csgo|瓦"
_RANKS = "青铜|白银|黄金|铂金|钻石|大师|宗师|王者|神话|无畏"
_ORDER_NUM = re.compile(r"^\d{8,20}$")

# 明确的闲聊/寒暄/回应词：短输入命中这些才算 chitchat。
# 其余短输入不再按"长度<10"一刀切，返回 None 交给 embedding/LLM 识别，
# 避免"找陪玩 / 推荐一下 / 陪我打瓦 / 平台抽成多少"这类短但有意图的输入被吞成闲聊。
_CHITCHAT_WORDS = (
    "你好", "您好", "嗨", "哈喽", "hi", "hello", "在吗", "在不在", "在的",
    "谢谢", "多谢", "感谢", "好的", "好", "收到", "知道了", "明白", "懂了",
    "嗯", "哦", "哈哈", "嘿嘿", "拜拜", "再见", "晚安", "早安", "早上好", "晚上好",
    "厉害", "666", "ok", "无聊", "没事",
)


# 否定词（jieba 整词命中，避免"特别/不错"里的"别/不"被误判为否定）
_NEGATIONS = {"不", "别", "没", "没有", "不用", "不要", "不想", "不需要", "不想要",
              "不是", "并非", "拒绝", "否认", "无需", "不必", "免", "勿", "莫"}


@lru_cache(maxsize=128)
def _negation_spans(text: str) -> tuple:
    """返回 text 中所有否定词的 (start, end) 区间（同一文本只分词一次）。"""
    spans = []
    for word, start, end in jieba.tokenize(text):
        if word in _NEGATIONS:
            spans.append((start, end))
    return tuple(spans)


def _negated_at(spans, pos: int) -> bool:
    """关键词起始位置 pos 之前（0~2 字内，覆盖"不是|要|投诉"这类隔一个词的情况）是否被否定。"""
    for _start, end in spans:
        if 0 <= pos - end <= 2:
            return True
    return False


def _has(text: str, *words: str) -> bool:
    spans = _negation_spans(text)
    for w in words:
        start = 0
        while True:
            pos = text.find(w, start)
            if pos == -1:
                break
            if not _negated_at(spans, pos):
                return True  # 存在一个"非否定"命中即可
            start = pos + len(w)
    return False


# 意图触发词（供 negates_intent 复用，与规则层关键词一致）
_INTENT_KEYWORDS = (
    "推荐", "陪玩", "找个", "来个", "带飞", "上分",                      # recommend
    "退款", "退钱", "下单", "充值", "打赏", "催单", "改单", "取消订单",   # order
    "投诉", "举报", "差评",                                            # complaint
    "转人工", "人工", "客服",                                          # human
)


def negates_intent(text: str) -> bool:
    """是否存在被否定修饰的意图关键词（如 不投诉 / 不用推荐 / 别举报 / 不要陪玩）。

    embedding 层对否定不敏感，会把「不用推荐陪玩」按词面误判成 recommend；
    分类器据此在规则层未命中时跳过 embedding、直接交 LLM（LLM 才真正理解否定）。
    """
    spans = _negation_spans(text)
    for w in _INTENT_KEYWORDS:
        start = 0
        while True:
            pos = text.find(w, start)
            if pos == -1:
                break
            if _negated_at(spans, pos):
                return True
            start = pos + len(w)
    return False


def match(message: str) -> Optional[str]:
    text = message.strip()
    has_order_num = re.search(r"\d{8,20}", text) is not None

    # 0. human（显式转人工）：用户明确要求转人工时，优先于投诉等其它意图。
    if _has(text, "转人工", "转接人工", "找人工", "人工服务", "转客服", "人工客服"):
        return "human"

    # 1. complaint（最高优先）：投诉/差评/极端情绪/违规举报。
    if _has(text, "投诉", "举报", "太差", "恶心", "骗", "态度", "差评", "骂",
            "垃圾", "气死", "坑", "违规", "私下", "加微信"):
        return "complaint"

    # 2. human（一般）
    if _has(text, "人工", "客服", "真人"):
        return "human"

    # 3. recommend：游戏名 + 陪玩/段位/价格，或 推荐动词 + 属性词。
    #    置于 knowledge 之前，避免"无畏契约…价格60-80"被"价格"误吞成知识咨询。
    if re.search(_GAMES, text, re.IGNORECASE) and (
            _has(text, "陪玩", "推荐", "找个", "有没有", "带飞", "上分", "段位", "价位", "预算", "价格")
            or re.search(_RANKS, text)):
        return "recommend"
    if _has(text, "推荐", "找个", "有没有", "来个", "想找", "帮我找", "陪玩") and \
            _has(text, "段位", "价位", "性格", "带飞", "温柔", "技术", "上分", "大神", "教学", "声音"):
        return "recommend"

    # 4. order：订单号 / 明确的订单动作；含疑问词时让位给 knowledge。
    if _ORDER_NUM.match(text):
        return "order"
    if has_order_num and _has(text, "退", "取消", "改", "查", "看", "状态", "订单"):
        return "order"
    if _has(text, "下单", "充值", "打赏") and not _has(text, "能不能", "可以吗", "怎么"):
        return "order"
    if _has(text, "退款", "退钱", "申请退款") and not _has(text, "规则", "怎么", "多久", "几天", "什么时候", "如何"):
        return "order"
    if _has(text, "催单", "改单", "取消订单", "查订单", "我的订单", "订单状态", "到哪了", "取消掉") \
            and not _has(text, "怎么", "如何"):
        return "order"
    if _has(text, "订单") and _has(text, "查", "看", "状态", "退", "取消", "改", "列表") \
            and not _has(text, "怎么", "如何", "多久", "规则"):
        return "order"

    # 5. knowledge：规则/收费/价格/流程咨询；含疑问词。
    if _has(text, "多少钱", "怎么收费", "收费", "规则", "包含什么", "能不能", "可以吗",
            "价格", "怎么", "多久"):
        return "knowledge"

    # 6. chitchat：仅当短输入命中明确的闲聊词时才判定为闲聊；其余短输入返回 None，
    #    交给 embedding/LLM 识别，避免按"长度<10"一刀切吞掉短查询。
    if len(text) < 10 and _has(text, *_CHITCHAT_WORDS):
        return "chitchat"

    return None
