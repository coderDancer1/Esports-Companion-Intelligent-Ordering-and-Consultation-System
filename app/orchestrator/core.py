"""Orchestrator：handle（加载→分类→日志→组装→dispatch→写回→压缩检查）与 dispatch。"""
from __future__ import annotations

import re
from typing import Dict, Optional

from app.config import get_settings
from app.db.lock import now_ts
from app.db.redis_client import json_dumps, json_loads
from app.intent.classifier import IntentClassifier
from app.intent.thresholds import INTENT_THRESHOLDS
from app.llm.client import complete, is_llm_available
from app.memory import assembler, compressor, profile as profile_store, raw_store, short_term
from app.memory.compressed_store import get_latest
from app.orchestrator import handoff as handoff_helper
from app.orchestrator.context import AgentContext
from app.orchestrator.expert_prompts import build_reply_prompt
from app.orchestrator.react import react_events
from app.orchestrator.experts.clarify import clarify_expert
from app.orchestrator.experts.complaint import complaint_expert
from app.orchestrator.experts.human import human_expert
from app.orchestrator.experts.knowledge import knowledge_expert
from app.orchestrator.experts.order import order_expert
from app.orchestrator.experts.recommend import recommend_expert
from app.orchestrator.log_writer import write_route_log


class Orchestrator:
    def __init__(self) -> None:
        self.classifier = IntentClassifier()
        self._experts = {
            "recommend": recommend_expert,
            "order": order_expert,
            "complaint": complaint_expert,
            "knowledge": knowledge_expert,
            "clarify": clarify_expert,
            "human": human_expert,
        }

    def register(self, intent: str, fn) -> None:
        self._experts[intent] = fn

    async def handle(self, auth, session_id: str, message: str) -> Dict:
        ctx, decision, turn_index = await self._prepare(auth, session_id, message)
        result = await self.dispatch(ctx)
        await self._finalize(auth, session_id, message, turn_index, decision, ctx, result)
        return self._response(session_id, turn_index, decision, result)

    async def handle_stream(self, auth, session_id: str, message: str):
        """流式入口：yield {'type':'delta', text} 与 {'type':'done', ...完整响应字段}。"""
        ctx, decision, turn_index = await self._prepare(auth, session_id, message)
        result: Optional[Dict] = None
        async for ev in self._dispatch_stream(ctx):
            if ev.get("type") == "delta":
                yield ev
            elif ev.get("type") == "done":
                result = ev["result"]
        if result is None:
            result = {"reply": "", "handoff_to_human": False}
        await self._finalize(auth, session_id, message, turn_index, decision, ctx, result)
        yield {"type": "done", **self._response(session_id, turn_index, decision, result)}

    async def _prepare(self, auth, session_id: str, message: str):
        """加载上下文 → 意图分类 → 路由日志 → 组装 AgentContext。"""
        meta = short_term.get_meta(session_id)
        recent = short_term.get_recent(session_id, n=get_settings().CONTEXT_RECENT_MESSAGES)
        summary = get_latest(auth.user_id, session_id)
        profile = profile_store.get(auth.user_id)
        state = self._load_structured_state(session_id)

        pending = json_loads(meta.get("pending_clarify")) if meta.get("pending_clarify") else None
        decision = await self.classifier.classify(
            message=message, recent_messages=recent, compressed_summary=summary,
            last_intent=meta.get("last_intent"), pending_clarify=pending,
        )

        turn_index = int(meta.get("turn_count", "0") or 0) + 1
        write_route_log(session_id, turn_index, decision, meta)

        ctx = assembler.build(auth=auth, session_id=session_id, message=message,
                              turn_index=turn_index, profile=profile, summary=summary,
                              recent=recent, state=state, decision=decision)
        ctx.handoff_count = int(meta.get("handoff_count", "0") or 0)
        return ctx, decision, turn_index

    async def _finalize(self, auth, session_id: str, message: str, turn_index: int,
                        decision, ctx: AgentContext, result: Dict) -> None:
        """写回短期记忆 / meta / 原始记录，并触发压缩检查。"""
        short_term.append_user(session_id, message)
        short_term.append_assistant(session_id, result["reply"], result.get("tool_calls"))
        clarify_opts = result.get("clarify_options")
        short_term.update_meta(session_id, {
            "last_intent": decision.intent,
            "turn_count": turn_index,
            "last_active": now_ts(),
            "pending_clarify": json_dumps(clarify_opts) if clarify_opts else "",
            "handoff_count": ctx.handoff_count,
        })
        raw_store.write_turn(auth.user_id, session_id, turn_index, message,
                             result["reply"], result.get("tool_calls"))
        await compressor.maybe_compress(session_id, auth.user_id)

    async def dispatch(self, ctx: AgentContext) -> Dict:
        """非流式分派：消费 _dispatch_stream，仅取最终 done 结果。"""
        last: Dict = {"reply": "", "handoff_to_human": False}
        async for ev in self._dispatch_stream(ctx):
            if ev.get("type") == "done":
                last = ev["result"]
        return last

    async def _dispatch_stream(self, ctx: AgentContext):
        """分派生成器（单一事实源）。yield {'type':'delta'|'done'}，最后必有 done。"""
        d = ctx.route_decision or {}
        intent = d.get("intent", "unknown")
        confidence = d.get("confidence", 0.0)

        if intent == "unknown" or confidence < INTENT_THRESHOLDS.get(intent, 0.65):
            options = d.get("clarify_options") or self._top2_intents(ctx)
            result = await self._experts["clarify"](ctx, clarify_options=options)
            await self._naturalize_reply(ctx, result)
            yield {"type": "delta", "text": result["reply"]}
            yield {"type": "done", "result": result}
            return

        if intent == "chitchat":
            result = {"reply": self._chitchat_reply(ctx.message), "handoff_to_human": False}
            await self._naturalize_reply(ctx, result)
            yield {"type": "delta", "text": result["reply"]}
            yield {"type": "done", "result": result}
            return

        if handoff_helper.exceeded(ctx.handoff_count):
            result = await self._experts["human"](ctx, reason="handoff_limit")
            yield {"type": "delta", "text": result["reply"]}
            yield {"type": "done", "result": result}
            return

        # 确定性安全护栏：在 ReAct 之前强制判定（未成年人下单红线 / 投诉转人工规则）
        guard = await self._pre_guard(ctx, intent)
        if guard is not None:
            yield {"type": "delta", "text": guard["reply"]}
            yield {"type": "done", "result": guard}
            return

        # ReAct 回路（LLM 可用时作为主执行路径；观察→规划→调工具→迭代→作答）
        react_done: Optional[Dict] = None
        async for ev in react_events(ctx, intent):
            if ev.get("type") == "delta":
                yield ev
            elif ev.get("type") == "done":
                react_done = ev["result"]
        if react_done and react_done.get("reply"):
            yield {"type": "done", "result": react_done}
            return

        # 回退：确定性专家
        fn = self._experts.get(intent) or self._experts["human"]
        result = await fn(ctx)
        if result.get("detected_intent_change"):
            ctx.handoff_count += 1
            ctx.route_decision = {"intent": result["detected_intent_change"], "confidence": 0.9,
                                  "reason": "expert_detected_switch", "route_source": "llm"}
            async for ev in self._dispatch_stream(ctx):
                yield ev
            return
        await self._naturalize_reply(ctx, result)
        yield {"type": "delta", "text": result["reply"]}
        yield {"type": "done", "result": result}

    _MINOR_PURCHASE_WORDS = ("下单", "充值", "打赏", "购买", "买陪玩", "付款")

    async def _pre_guard(self, ctx: AgentContext, intent: str):
        """确定性安全护栏，返回非 None 表示拦截并直接给出结果。"""
        # 未成年人保护红线：禁止下单/充值/打赏
        if intent == "order" and ctx.is_minor and any(w in ctx.message for w in self._MINOR_PURCHASE_WORDS):
            return await self._experts["order"](ctx)
        # 投诉转人工规则（金额/重复投诉/人身攻击/高情绪）需确定性判定
        if intent == "complaint":
            forced = await self._complaint_forced(ctx)
            if forced is not None:
                return forced
        return None

    async def _complaint_forced(self, ctx: AgentContext):
        from app.tools.definitions.assess_emotion import run as tool_assess
        from app.tools.definitions.check_handoff_rules import run as tool_rules

        emo = await tool_assess(ctx, message=ctx.message)
        complaint_count = int(ctx.user_profile.get("complaint_count", 0) or 0)
        rules_res = await tool_rules(ctx, context={"message": ctx.message,
                                                  "complaint_count": complaint_count})
        should = (rules_res.status == "success" and rules_res.data.get("should_handoff"))
        intensity = (emo.data or {}).get("intensity", 0.0) if emo.status == "success" else 0.0
        if should or intensity >= 0.8:
            return await self._experts["complaint"](ctx)
        return None

    async def _naturalize_reply(self, ctx: AgentContext, result: Dict) -> None:
        """用 LLM + 各意图专属提示词生成自然回复；失败时保留原模板回复。

        ReAct 回路已直接产出 LLM 回复（result['llm_generated']），跳过二次自然化。
        """
        if not is_llm_available():
            return
        if result.get("llm_generated"):
            return
        intent = (ctx.route_decision or {}).get("intent", "")
        prompt = build_reply_prompt(intent, ctx, result)
        try:
            resp = await complete([{"role": "user", "content": prompt}],
                                  max_tokens=512, temperature=0.5)
            if resp.get("content"):
                result["reply"] = resp["content"].strip()
        except Exception:  # noqa: BLE001
            pass

    def _load_structured_state(self, session_id: str) -> Dict:
        state: Dict = {}
        for m in short_term.get_recent(session_id, n=get_settings().CONTEXT_RECENT_MESSAGES):
            if m.get("role") == "user":
                oid = re.search(r"\b(\d{8,20})\b", m.get("content", ""))
                if oid:
                    state["order_id"] = oid.group(1)
        return state

    def _top2_intents(self, ctx: AgentContext):
        try:
            return self.classifier.embedding_router.top_intents(ctx.message, ctx.recent_messages, k=2)
        except Exception:  # noqa: BLE001
            return ["recommend", "order"]

    def _chitchat_reply(self, message: str) -> str:
        if any(w in message for w in ["你好", "在吗", "hi", "hello"]):
            return "你好呀，我是陪玩助手，可以帮你推荐陪玩、查订单、处理售后～"
        if any(w in message for w in ["谢谢", "感谢"]):
            return "不客气，有需要随时找我～"
        return "好的，请问还有什么可以帮你的？"

    def _response(self, session_id: str, turn_index: int, decision, result: Dict) -> Dict:
        resp = {
            "session_id": session_id,
            "turn_index": turn_index,
            "reply": result.get("reply", ""),
            "intent": None if result.get("clarify_options") else decision.intent,
            "confidence": decision.confidence,
            "route_source": decision.route_source,
            "handoff_to_human": bool(result.get("handoff_to_human", False)),
        }
        if result.get("cards"):
            resp["cards"] = result["cards"]
        if result.get("ticket_id"):
            resp["ticket_id"] = result["ticket_id"]
        if result.get("clarify_options"):
            resp["clarify_options"] = result["clarify_options"]
        if result.get("tool_calls"):
            resp["tool_calls"] = result["tool_calls"]
        if result.get("steps"):
            resp["steps"] = result["steps"]
        return resp


# 全局单例
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
