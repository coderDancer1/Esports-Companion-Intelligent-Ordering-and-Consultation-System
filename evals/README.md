# 评测集与评测脚本

面向面试展示与阈值调优的离线评测。不依赖外部服务即可运行意图分类评测；
RAG 评测需要先有知识库数据（首次运行会自动 seed）。

## 运行

```bash
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task intent   # 意图分类
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task rag      # RAG 检索
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task agent    # Agent 回路（需真实 LLM）
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task multiturn # 多轮上下文（跨轮/跨 agent 记忆）
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task all      # 全部
```

无 DeepSeek API Key 时意图分类仍可运行（LLM 层走确定性 mock 降级），结果会如实标注 `LLM 可用`。
`agent` / `multiturn` 任务直接跑 ReAct 回路 / 完整 Orchestrator，需要真实 LLM（多轮的结构化「记忆累积」校验不依赖 LLM）。

## 数据集

| 文件 | 内容 | 规模 |
|------|------|------|
| `intent_cases.json` | `message → intent`，覆盖 6 类意图，含规则可命中的直白表达 + 需要 embedding/LLM 的同义改写与短边界用例 | 120 条 |
| `rag_cases.json` | `query → expect_found`，覆盖知识库 3 篇文档的正例 + 领域外负例 | 45 条 |
| `agent_cases.json` | `message/intent → expect_tool/expect_contains/expect_not_contains`，校验工具选择 + 答案 grounding（含反幻觉/写操作/转人工红线类） | 20 条 |
| `multiturn_cases.json` | 场景化多轮对话：逐轮 `message/expect_intent`，末轮用「复述」类问题校验 `expect_contains` 回忆早期内容 + `expect_not_contains` 拦截失忆话术 | 2 场景 |

## 指标

- **意图分类**：整体准确率、各意图精确率/召回率/F1、混淆矩阵、`route_source` 分层贡献（规则/粘性/embedding/LLM 各拦截多少）、误分类明细（用于补规则/调阈值）。
- **RAG 检索**：准确率/精确率/召回率/F1，逐条标注 TP/FP/FN/TN（命中判定为 `search_knowledge_base.status == success`）。
- **Agent 回路**：工具选择正确率（是否调用 `expect_tool`）+ grounding 正确率（答案含 `expect_contains` 事实、不含 `expect_not_contains` 幻觉）。
- **多轮上下文**：跑完整 `Orchestrator.handle`，逐轮校验 `expect_intent`（跨 agent 路由是否正确），末轮校验「上下文回忆」（`expect_contains` 命中早期关键词）与「无失忆话术」（`expect_not_contains` 不含"只能看到当前/没保留"）；另做结构化校验：短期记忆是否按轮完整累积（不依赖 LLM）。

## 当前基线结果

| 任务 | 准确率 | 说明 |
|------|--------|------|
| 意图分类 | 100.00% (120/120) | 规则 73.3% + LLM 20.8% + embedding 5.8%；六类意图精确/召回均 100%（见下） |
| RAG 检索 | 86.67% (39/45) | 语义重排启用后 精确 95.83% / 召回 82.14%；漏检=口语化退款（语义重排对口语化退款得分低），误检=「退」 |
| Agent 工具选择 | 90.00% (18/20) | 2 处失败：模糊需求过度澄清、未收录游戏（王者荣耀） |
| Agent grounding | 90.00% (18/20) | 抓到一个「平台抽成」幻觉（模型编造 20%–30%） |
| 多轮上下文 | 100% (2/2 场景) | 跨 agent 路由 2/2、上下文回忆 2/2、无失忆话术 2/2、记忆累积 2/2 |

> 完整的时间线式改进记录（含所有指标、根因、修复方案与已知局限）见项目根目录 [`改进记录.md`](../改进记录.md)。

## 评测驱动的改进记录（重要，面试可讲）

评测集不是摆设——它直接暴露并推动了五处修复：

1. **recommend 规则过度匹配**：原规则「触发词含"陪玩"」与「属性词含"陪玩"」两处同时出现"陪玩"，
   退化为"含'陪玩'即推荐"，把 `这个陪玩师骗我钱`、`陪玩费用包含哪些服务` 等投诉/咨询误判为推荐。
   → 改为「推荐动词 + 真实属性词」，准确率 77% → 86%，recommend/complaint 精确率到 100%。
2. **投诉关键词缺失**：`骗我钱`、`辱骂我` 无关键词命中。→ 补入「骗/骂」。
3. **embedding 层阈值与后端不匹配（方案 A+F 根治）**：`EMB_ABS_THRESHOLD=0.75` 是按 BGE 语义空间调的，而默认 demo 后端是哈希向量（余弦上限约 0.5），「语义阈值 + hash 天花板」形成静默死区，embedding 层 0/120 永远不触发、级联退化为「规则→LLM」。
   → **A（让语义向量真跑起来）**：升级 Pillow 到 11.3.0（修 `transformers` import 崩溃）、设 `HF_ENDPOINT=https://hf-mirror.com`（huggingface.co 被墙）、`EMBEDDING_BACKEND=sentence_transformers` + `BAAI/bge-small-zh-v1.5`（dim=512）。
   → **F（自愈护栏）**：`effective_backend()` 动态判定后端，`embedding_thresholds()` / `example_match_threshold()` 按后端取阈值（语义 0.75/0.08、0.80；hash 0.35/0.05、0.45）；Chroma 维度漂移自动 `_reset_col` 重建。embedding 层 0% → **3.3%**。
4. **chitchat 兜底「无脑命中」**：原规则 `len(text) < 10 → chitchat` 不看内容，把 `找陪玩`、`平台抽成多少`、
   `看看我最近下的单` 等短但有意图的输入一刀切吞成闲聊，永远到不了 embedding/LLM。
   → 反转为「闲聊词白名单」：短输入仅当命中 `_CHITCHAT_WORDS`（你好/在吗/谢谢/好的/哈哈…）才算 chitchat，
   其余一律返回 None 交给 embedding/LLM。准确率 80.83% → **93.33%**，chitchat 精确/召回均 100%。
5. **规则优先级冲突（4 类 8 条误分类）**：`垃圾平台，退钱！`（投诉情绪词不全，被 `退钱` 抢成 order）、
   `我要投诉，转人工`（`投诉` 先于 `转人工`）、`退款要多久到账`/`未成年人能不能下单`/`订单取消后钱怎么退`
   （`退款/下单/订单` 先于知识咨询）、`打无畏契约…价格60-80`（`价格` 被 knowledge 抢走，应为 recommend），
   以及 `他私下让我加微信转账`、`陪玩师爽约了平台怎么处理` 两条 LLM 边界。
   → 重排优先级为「显式转人工 → 投诉 → 人工 → 推荐 → 订单 → 知识」：补投诉情绪词（垃圾/气死/坑/违规/私下）、
   `转人工` 前置、推荐规则先于知识（游戏名+段位/价格）、订单词遇疑问词（怎么/多久/能不能/规则）让位给知识。
   准确率 93.33% → **100.00%**，六类意图精确/召回均 100%。

## 已知局限（诚实呈现）

- **规则层仍是硬编码关键词**：即便当前 120 条全中，规则仍靠人工枚举关键词，遇到评测集之外的新表达
  （新游戏名、新情绪词、新咨询问法）会退回 embedding/LLM 或误判。这是「规则优先 + 短路」架构的固有取舍，
  可通过飞轮（线上反馈回流补评测集 + 补关键词）持续迭代。
- **哈希向量上限低**：语义相近但词面不重叠的短句（如 `来个技术好的大神带我上分`）sim 仅 0.17，
  只能交给 LLM 兜底——这正是级联设计里 LLM 层存在的意义。启用 BGE 语义后端后已缓解，但 hash
  仍是 sentence-transformers 未安装/加载失败时的降级路径，该上限对降级态依然成立。
