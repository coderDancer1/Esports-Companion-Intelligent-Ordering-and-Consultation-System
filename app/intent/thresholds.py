"""各意图置信度阈值。阈值越高=判定越严格=越不容易触发该意图。"""
INTENT_THRESHOLDS = {
    "recommend": 0.65,
    "order": 0.65,
    "complaint": 0.80,  # 高风险，更严格
    "knowledge": 0.55,  # 低风险，更宽松
    "chitchat": 0.60,
    "human": 0.70,
}
