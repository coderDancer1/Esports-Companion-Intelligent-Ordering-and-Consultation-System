---
name: knowledge-qa
description: 知识问答：检索通道选择、兜底话术、引用来源
triggers: [多少钱, 收费, 规则, 怎么, 能不能, 价格]
dependent_tools: [search_knowledge_base]
---
# 知识问答

## 检索通道
- 通道 A（前置 RAG）：直接检索知识库，命中则基于来源作答。
- 通道 B（Agentic RAG）：订单/投诉场景按需检索。

## 兜底
- need_fallback=True 时明示"没有找到相关说明"，并给出转人工入口。
- 回答需注明来源（文档标题），不得编造规则。

## 引用
- 组织回答时优先引用检索到的原文片段，保留金额/规则等关键数字。
