---
name: complaint-handling
description: 投诉处理：情绪分级、转人工规则、工单打包
triggers: [投诉, 退款, 差评, 举报, 态度差, 恶心, 欺骗]
dependent_tools: [assess_emotion, check_handoff_rules, create_handoff_ticket, search_knowledge_base]
---
# 投诉处理

## 情绪分级
- 强烈不满（intensity ≥ 0.8）：安抚 + 直接转人工。
- 不满（0.4-0.8）：了解诉求，符合转人工规则则转人工。

## 转人工规则（确定性）
- 涉及金额争议 / 重复投诉 / 人身攻击 → 必须转人工。
- 命中规则立即终止当前流程，打包上下文创建工单。

## 工单打包
- summary 简洁概括诉求；context_snapshot 附最近消息与识别到的意图。
- 创建成功后明确告知"已为你创建工单，客服稍后联系"。
