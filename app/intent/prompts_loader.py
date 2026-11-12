"""加载分类 Prompt（延迟导入，避免循环依赖）。"""
from __future__ import annotations

import os

_CLASSIFY_PROMPT = """你是意图分类器，将用户输入归入 6 类之一：
recommend（推荐陪玩）、order（订单查询/售后）、complaint（投诉）、
knowledge（平台规则/收费咨询）、chitchat（闲聊）、human（转人工）。

规则：
1. 当前用户输入是主要依据。历史仅用于消解指代（这个/那个/它/第N个）和判断
   意图延续/切换，不得因历史覆盖当前输入的明确信号。
2. 若当前输入出现投诉/人工/退款/取消等切换信号，即使前文是推荐或订单，
   也必须判为新意图。
3. 若当前输入含指代词且语义不完整，结合最近一轮 user 消息消解后再判定。
4. 无法确定时 confidence 必须低于 0.6，并说明缺少什么信息。
"""


def load_classify_prompt() -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", "classify.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    except Exception:  # noqa: BLE001
        pass
    return _CLASSIFY_PROMPT
