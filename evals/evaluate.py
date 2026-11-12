"""离线评测：意图分类 + RAG 检索 + Agent 回路。

用法：
    python evals/evaluate.py --task intent   # 意图分类（级联整体 + 分层贡献 + 混淆矩阵）
    python evals/evaluate.py --task rag      # RAG 检索（需要先有知识库数据）
    python evals/evaluate.py --task agent    # Agent 回路（工具选择 + grounding，需真实 LLM）
    python evals/evaluate.py --task all

无大模型 API Key 时意图分类仍可运行（LLM 层走 mock 降级），结果会如实标注。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

INTENTS = ["recommend", "order", "complaint", "knowledge", "chitchat", "human"]


def _load(name: str):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- intent

async def run_intent_eval() -> None:
    from app.intent.classifier import IntentClassifier
    from app.llm.client import is_llm_available

    data = _load("intent_cases.json")
    cases = data["cases"]
    clf = IntentClassifier()

    correct = 0
    confusion = defaultdict(Counter)  # gold -> Counter(pred)
    source_count = Counter()
    errors = []

    for case in cases:
        msg, gold = case["message"], case["intent"]
        d = await clf.classify(message=msg)
        pred = d.intent
        confusion[gold][pred] += 1
        source_count[d.route_source] += 1
        if pred == gold:
            correct += 1
        else:
            errors.append((msg, gold, pred, d.route_source, d.confidence))

    total = len(cases)
    print("=" * 70)
    print("意图分类评测")
    print(f"LLM 可用：{is_llm_available()}  样例数：{total}")
    print(f"整体准确率：{correct}/{total} = {correct / total:.2%}")
    print()
    print("分层贡献（route_source 分布）：")
    for src, n in source_count.most_common():
        print(f"  {src:<16} {n:>3}  ({n / total:.1%})")
    print()

    # 每意图 P / R / F1
    print(f"{'意图':<12}{'精确率':>10}{'召回率':>10}{'F1':>10}{'样例':>6}")
    for intent in INTENTS:
        tp = confusion[intent][intent]
        gold_n = sum(confusion[intent].values())
        pred_n = sum(confusion[g][intent] for g in INTENTS)
        p = tp / pred_n if pred_n else 0.0
        r = tp / gold_n if gold_n else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        print(f"{intent:<12}{p:>9.2%}{r:>9.2%}{f1:>9.2%}{gold_n:>6}")

    # 混淆矩阵
    print()
    print("混淆矩阵（行=真实，列=预测）：")
    header = "           " + "".join(f"{i[:7]:>9}" for i in INTENTS)
    print(header)
    for gold in INTENTS:
        row = f"{gold:<11}"
        for pred in INTENTS:
            row += f"{confusion[gold][pred]:>9}"
        print(row)

    if errors:
        print()
        print("误分类明细（可用于调阈值 / 补规则）：")
        for msg, gold, pred, src, conf in errors:
            print(f"  [{gold} -> {pred}] src={src} conf={conf:.3f}  「{msg}」")
    print("=" * 70)


# ---------------------------------------------------------------- agent

async def run_agent_eval() -> None:
    from app.llm.client import is_llm_available
    from app.orchestrator.context import AgentContext
    from app.orchestrator.react import react_events

    if not is_llm_available():
        print("=" * 70)
        print("Agent 回路评测：需要真实 LLM，当前无 API Key，已跳过")
        print("=" * 70)
        return

    _init_storage()
    data = _load("agent_cases.json")
    cases = data["cases"]
    user_id = data.get("user_id", "u_1001")

    tool_pass = ground_pass = 0
    total = len(cases)
    details = []

    for i, case in enumerate(cases):
        msg, intent = case["message"], case["intent"]
        ctx = AgentContext(user_id=user_id, session_id=f"eval_agent_{i}",
                           message=msg, turn_index=0)
        result = None
        async for ev in react_events(ctx, intent):
            if ev.get("type") == "done":
                result = ev["result"]

        if not result:
            details.append(("NO_RESULT", msg, intent, "-", "-", False, False))
            continue
        tools_called = [tc["tool"] for s in result.get("steps", [])
                        for tc in s.get("tool_calls", [])]
        reply = result.get("reply", "")

        allowed_tools = case.get("expect_tool_any") or \
            ([case["expect_tool"]] if case.get("expect_tool") else [])
        tool_ok = (not allowed_tools) or any(t in tools_called for t in allowed_tools)
        ground_ok = all(c in reply for c in case.get("expect_contains", [])) and \
                    all(c not in reply for c in case.get("expect_not_contains", []))
        if tool_ok:
            tool_pass += 1
        if ground_ok:
            ground_pass += 1
        details.append(("PASS" if (tool_ok and ground_ok) else "FAIL", msg, intent,
                        ",".join(tools_called) or "-", reply, tool_ok, ground_ok))

    print("=" * 70)
    print("Agent 回路评测（ReAct 工具调用正确性 + 答复 grounding）")
    print(f"样例数：{total}  工具选择正确率：{tool_pass}/{total} = {tool_pass / total:.2%}"
          f"  grounding 正确率：{ground_pass}/{total} = {ground_pass / total:.2%}")
    print()
    for verdict, msg, intent, tools, reply, tool_ok, ground_ok in details:
        mark = "✓" if verdict == "PASS" else "✗"
        flags = []
        if not tool_ok:
            flags.append("工具错误")
        if not ground_ok:
            flags.append("未grounded")
        print(f"  {mark} [{intent}] 「{msg}」")
        print(f"       tools=[{tools}] {'/'.join(flags) if flags else 'OK'}")
        print(f"       reply=「{reply[:80]}{'…' if len(reply) > 80 else ''}」")
    print("=" * 70)


# ---------------------------------------------------------------- multiturn

async def run_multiturn_eval() -> None:
    """多轮上下文评测：跑完整 Orchestrator.handle，验证跨轮/跨 agent 路由后仍保留上下文。"""
    import time as _time

    from app.llm.client import is_llm_available
    from app.orchestrator.core import get_orchestrator
    from app.security.auth import AuthUser

    _init_storage()
    from app.db.redis_client import get_redis

    data = _load("multiturn_cases.json")
    scenarios = data["scenarios"]
    orch = get_orchestrator()

    pass_cnt = fail_cnt = 0
    recall_total = recall_ok = 0
    amnesia_total = amnesia_ok = 0
    intent_total = intent_ok = 0

    print("=" * 70)
    print("多轮上下文评测（跨轮 + 跨 agent 路由后的记忆）")
    print(f"LLM 可用：{is_llm_available()}  场景数：{len(scenarios)}")

    for sc in scenarios:
        sid = sc["session_id"]
        auth = AuthUser(user_id=sc.get("user_id", "u_1001"),
                        is_minor=False, token_exp=int(_time.time()) + 3600)
        # 清理残留，保证场景独立可重跑
        get_redis().delete(f"session:{sid}:messages", f"session:{sid}:meta")

        print(f"\n[场景] {sc['name']}  (session={sid})")
        scenario_ok = True
        replies = []

        for i, turn in enumerate(sc["turns"]):
            msg = turn["message"]
            r = await orch.handle(auth, sid, msg)
            replies.append(r.get("reply", ""))
            pred_intent = r.get("intent")
            line = f"  turn{i+1} [{pred_intent}] 「{msg}」"

            if "expect_intent" in turn:
                intent_total += 1
                ok = pred_intent == turn["expect_intent"]
                intent_ok += ok if ok else 0
                line += f"  intent={'✓' if ok else '✗(期望' + turn['expect_intent'] + ')'}"
                scenario_ok = scenario_ok and ok

            reply = r.get("reply", "")
            if "expect_contains" in turn or "expect_not_contains" in turn:
                contains_ok = all(c in reply for c in turn.get("expect_contains", []))
                not_contains_ok = all(c not in reply for c in turn.get("expect_not_contains", []))
                recall_total += 1
                recall_ok += 1 if contains_ok else 0
                amnesia_total += 1
                amnesia_ok += 1 if not_contains_ok else 0
                flags = []
                if not contains_ok:
                    flags.append("未回忆到关键词")
                if not not_contains_ok:
                    flags.append("出现失忆话术")
                line += f"  回忆={'✓' if contains_ok else '✗'} 无反={'✓' if not_contains_ok else '✗'}"
                if flags:
                    line += "  (" + "/".join(flags) + ")"
                scenario_ok = scenario_ok and contains_ok and not_contains_ok
            print(line)
            print(f"        reply=「{reply[:80]}{'…' if len(reply) > 80 else ''}」")

        # 结构校验：短期记忆是否按轮累积（不依赖 LLM）
        from app.memory import short_term
        stored = [m.get("content", "") for m in short_term.get_all(sid) if m.get("role") == "user"]
        expected = [t["message"] for t in sc["turns"]]
        mem_ok = stored == expected
        if not mem_ok:
            scenario_ok = False
            print(f"  ✗ 短期记忆未完整累积：期望 {len(expected)} 条用户消息，实际 {len(stored)} 条")

        pass_cnt += 1 if scenario_ok else 0
        fail_cnt += 0 if scenario_ok else 1
        print(f"  => 场景 {'通过' if scenario_ok else '失败'}（记忆累积 {'✓' if mem_ok else '✗'}）")

    print()
    total = len(scenarios)
    print(f"场景通过率：{pass_cnt}/{total} = {pass_cnt / total:.2%}")
    if intent_total:
        print(f"跨 agent 路由意图正确率：{intent_ok}/{intent_total} = {intent_ok / intent_total:.2%}")
    if recall_total:
        print(f"上下文回忆（expect_contains）：{recall_ok}/{recall_total} = {recall_ok / recall_total:.2%}")
    if amnesia_total:
        print(f"无失忆话术（expect_not_contains）：{amnesia_ok}/{amnesia_total} = {amnesia_ok / amnesia_total:.2%}")
    print("=" * 70)


# ---------------------------------------------------------------- rag

async def run_rag_eval() -> None:
    _init_storage()
    from app.orchestrator.context import AgentContext
    from app.tools.definitions.search_knowledge_base import run as kb_run

    cases = _load("rag_cases.json")["cases"]
    ctx = AgentContext(user_id="eval", session_id="eval", message="", turn_index=0)

    tp = fp = fn = tn = 0
    details = []
    for case in cases:
        q, expect = case["query"], case["expect_found"]
        res = await kb_run(ctx, query=q)
        found = res.status == "success"
        if expect and found:
            tp += 1
            tag = "TP"
        elif expect and not found:
            fn += 1
            tag = "FN"
        elif not expect and found:
            fp += 1
            tag = "FP"
        else:
            tn += 1
            tag = "TN"
        details.append((tag, q, found))

    total = len(cases)
    acc = (tp + tn) / total
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    print("=" * 70)
    print("RAG 检索评测")
    print(f"样例数：{total}  命中判定：search_knowledge_base.status == success")
    print(f"准确率：{acc:.2%}  精确率：{p:.2%}  召回率：{r:.2%}  F1：{f1:.2%}")
    print()
    for tag, q, found in details:
        mark = {"TP": "✓", "FP": "✗(误检)", "FN": "✗(漏检)", "TN": "·"}[tag]
        print(f"  [{tag}] {mark} 命中={found}  「{q}」")
    print("=" * 70)


def _init_storage() -> None:
    from app.db.mysql import create_all
    from app.db.chroma_client import init_chroma
    from app.rag.indexer import load_index
    from app.seed import seed_demo_data
    from app.business.playmate.service import list_playmates
    from app.matching.profile_index import rebuild as rebuild_playmates

    create_all()
    init_chroma()
    load_index()
    seed_demo_data()
    rebuild_playmates(list_playmates())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["intent", "rag", "agent", "multiturn", "all"], default="all")
    args = ap.parse_args()

    if args.task in ("intent", "all"):
        asyncio.run(run_intent_eval())
    if args.task in ("rag", "all"):
        asyncio.run(run_rag_eval())
    if args.task in ("agent", "all"):
        asyncio.run(run_agent_eval())
    if args.task in ("multiturn", "all"):
        asyncio.run(run_multiturn_eval())


if __name__ == "__main__":
    main()
