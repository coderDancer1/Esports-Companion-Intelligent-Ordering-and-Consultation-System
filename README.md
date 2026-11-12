# 电竞陪玩智能点单与咨询系统

一个基于「Agent 只做理解/判断/对话，后端服务负责写操作与资金」原则的陪玩点单与咨询智能体。

技术栈（按开发文档 v2.1 冻结架构）：Python 3.9+ / FastAPI / SQLAlchemy 2.x / Redis List / Chroma / MySQL 8 / bm25s / DeepSeek V4 Pro（经 Anthropic SDK 调用）。**全部外部依赖均可优雅降级**——不装 MySQL/Redis/Chroma/向量模型/真实 LLM 也能完整运行（SQLite + 内存实现 + 哈希向量 + 确定性 mock LLM）。

## 快速开始

```bash
# 1. 安装依赖（Windows + Python 3.9 无 MSVC 时，若 greenlet 编译失败，先执行：pip install greenlet==3.0.3）
pip install -r requirements.txt

# 2.（可选）复制环境变量，默认值即可运行
# cp .env.example .env

# 3. 启动服务
PYTHONIOENCODING=utf-8 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后访问：
- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/healthz

> **语义向量（可选）**：`.env` 默认 `EMBEDDING_BACKEND=sentence_transformers` + `EMB_MODEL=BAAI/bge-small-zh-v1.5`，
> 首次运行会经 `HF_ENDPOINT=https://hf-mirror.com` 下载模型（约 100MB，一次）。未安装 sentence-transformers
> 或加载失败时自动回落 `hash` 向量（jieba 词面重合，256 维），阈值按后端自适应切换。
> 注意 RAG 重排器 `bge-reranker-v2-m3`（约 1.1GB）首次也会触发下载，加载失败则回落 jieba 词覆盖度打分。
> 语义重排与 jieba 降级是两套阈值（`RERANK_SEMANTIC_THRESHOLD` / `RERANK_THRESHOLD`），按有效后端自适应切换；
> 对小知识库二者准确率打平（语义更精确、更漏口语化改写，且 CPU 上更慢），详见 [`改进记录.md`](改进记录.md) 第十三节。

## 演示账号 / Token

首次启动自动填充演示数据（6 位陪玩师、3 笔订单、3 篇知识文档）。鉴权支持两种方式：

| 方式 | 值 | 说明 |
|------|-----|------|
| 开发模式 | `demo_u_1001` | 普通用户，可下单/查单 |
| 开发模式 | `demo_u_2001` | 未成年用户（下单/充值会被拦截） |
| JWT | 启动日志打印 | `Authorization: Bearer <token>` |

```bash
# 示例（用 Python 的 requests，避免 Windows curl 对中文的 GBK 编码问题）
curl -H "Authorization: Bearer demo_u_1001" http://127.0.0.1:8000/api/v1/orders
```

## 核心接口（前缀 /api/v1）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 探活 MySQL/Redis/Chroma/bm25/LLM |
| POST | `/chat` | 统一对话入口（意图识别→ReAct 回路/护栏/专家回退） |
| POST | `/chat/stream` | 同上，SSE 流式输出（逐 token 回复 + 最终完整响应） |
| POST | `/feedback` | 用户对某轮答复打标签（👍/👎 + 可选纠错），数据飞轮采集入口 |
| GET | `/feedback` | 查看本人历史反馈 |
| POST | `/feedback/review` | 人工审核反馈 + 一键并入评测集（需 `X-Admin-Key`） |
| GET | `/playmates/search` | 陪玩师搜索（结构化过滤 + 语义排序） |
| GET | `/playmates/{id}` | 陪玩师详情 |
| GET | `/orders` / `/orders/{id}` | 订单列表 / 详情（仅本人） |
| POST | `/orders/{id}/cancel` | 取消订单 |
| POST | `/orders/{id}/after-sales` | 售后申请（退款/改派/改期） |
| POST | `/tickets` / GET `/tickets` / GET `/tickets/{id}` | 工单 |
| POST | `/admin/knowledge/ingest` | 知识库入库（需 `X-Admin-Key`） |
| GET | `/admin/logs/*` | 路由/工具/RAG/转接日志（需 `X-Admin-Key`） |

## 三条主链路自检

```bash
# 进程内冒烟（不依赖外部服务，覆盖推荐/知识/订单/退款/投诉）
PYTHONIOENCODING=utf-8 python smoke_test.py

# HTTP 端到端
#（先启动 uvicorn，再运行）
PYTHONIOENCODING=utf-8 python http_test.py
```

## ReAct 回路（LLM 主执行路径）

对话在意图识别后进入 **ReAct 工具调用回路**（`app/orchestrator/react.py`），而非硬编码专家：

```
意图识别（规则→粘性→embedding→LLM）
   → 确定性安全护栏（未成年下单红线 / 投诉转人工规则）
   → ReAct 回路：LLM 读取该意图常驻工具 schema → 规划 → 调用工具 → 观察结果 → 迭代作答
   → 失败回退：确定性专家（无 LLM / 回路未产出时）
```

- LLM 通过 Anthropic SDK 的 function calling 实际调用进程内工具（`search_playmates`、`query_order`、
  `search_knowledge_base`、`create_handoff_ticket` 等），工具返回 `success/empty/error` 三态，LLM 据此如实作答、不编造。
- 工具结果同时物化为结构化产物（陪玩卡片 `cards`、工单 `ticket_id`、`handoff_to_human`、`tool_calls` 轨迹），
  随 `/chat` 响应一并返回。
- **确定性护栏先于 LLM**：未成年人下单/充值、投诉转人工规则等安全红线在回路外强制判定，LLM 无法绕过。
- 思考模式已关闭（`DEEPSEEK_THINKING=disabled`），保证 function calling 与流式拿到纯文本块。

## 评测集

```bash
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task intent   # 意图分类
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task rag      # RAG 检索
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task agent    # Agent 回路（需真实 LLM）
PYTHONIOENCODING=utf-8 python evals/evaluate.py --task multiturn # 多轮上下文（跨轮/跨 agent 记忆）
```

见 [`evals/README.md`](evals/README.md)：意图分类 120 条、RAG 45 条、Agent 回路 20 条、多轮场景 2 个，
输出准确率/混淆矩阵/分层贡献。历次优化项、根因与指标汇总见 [`改进记录.md`](改进记录.md)。

## 数据飞轮（线上真实数据回流）

线上弱信号归集成候选评测样例，**只采集 + 人工审核，不做在线自动重训**（小样本会漂移）：

```
显式反馈  POST /feedback（👍/👎 + 纠错）   ┐
RAG 未命中 rag_log.need_fallback          ├─→ python evals/flywheel.py
工具异常  tool_log(status=error/bad_input) │     → evals/_flywheel_candidates.json
转人工    handoff_log                       ┘     （人工审核后并入评测集 / 补知识库）
```

- 四类信号已随主链路落库（`feedback/rag_log/tool_log/handoff_log`）。
- `python evals/flywheel.py` 归集为待审核清单，`--pretty` 打印明细。
- `POST /feedback/review`（需 `X-Admin-Key`）：标记 reviewed/ignored，并把通过项一键并入 `intent_cases` / `rag_cases`（按 message/query 去重）——「人工审核」也可演示。
- 冷启动阶段评测集本身就是飞轮；线上回流负责「自动发现评测集没覆盖的 badcase」。

## 关键架构约束（已落实）

1. **Agent 不做写操作**：写操作只返回「可执行性判断 + 参数」，由后端领域服务执行并写审计。
2. **Agent 不直连数据库**：通过进程内工具（`app/tools/definitions/*`）访问业务能力。
3. **三态工具结果**：`success` / `empty`（查无） / `error`（异常），不伪造空结果。
4. **user_id 只来自鉴权 token**：请求体中的 `user_id` 与 token 不一致直接 403。
5. **三明治架构**：意图三层识别（规则→粘性→embedding→LLM）、专家 Agent、RAG（向量 + BM25 → RRF → 重排）、订单状态机（中文状态）、资金托管流水、合规（未成年/内容安全）。
6. **优雅降级**：见 `app/config.py` 与 `requirements.txt` 注释，全部重依赖可切换为内存/纯 Python 实现。

## 目录结构

```
app/
  api/            HTTP 路由（chat/feedback/order/playmate/ticket/health/admin）
  business/       领域服务（订单状态机、资金托管、工单、陪玩师、合规）
  matching/       陪玩师匹配（结构化过滤 + 向量排序 + 档案索引）
  rag/            解析/切分/BM25/混合检索/重排
  intent/         意图三层识别
  memory/         会话记忆（短期/画像/压缩/组装）
  orchestrator/   手写 Orchestrator + ReAct 回路 + 专家 Agent 回退
  tools/          进程内工具（定义 + 注册表 + 三态结果）
  llm/            LLM 客户端 + 向量化 + token 计数
  db/             MySQL/SQLite、Redis、向量库、锁
  security/       鉴权（JWT）+ 安全守卫
  flywheel.py     数据飞轮：线上弱信号归集成候选评测样例
evals/            离线评测（意图分类 / RAG / Agent + 评测集 + 报告 + 飞轮归集）
```
