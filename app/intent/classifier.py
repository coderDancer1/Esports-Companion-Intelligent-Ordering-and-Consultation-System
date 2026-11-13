"""IntentClassifier 入口：澄清回填→规则→粘性→embedding→LLM，命中即短路。"""
from __future__ import annotations

from typing import List, Optional

from app.intent import llm_classifier, rules, sticky
from app.intent.embedding_router import EmbeddingRouter
from app.intent.route_decision import RouteDecision

_INTENT_NAMES = {"推荐": "recommend", "订单": "order", "投诉": "complaint",
                 "咨询": "knowledge", "人工": "human"}


class IntentClassifier:
    def __init__(self) -> None:
        self.embedding_router = EmbeddingRouter()

    async def classify(self, message: str, recent_messages: Optional[List[dict]] = None,
                       compressed_summary: str = "", last_intent: Optional[str] = None,
                       pending_clarify: Optional[List[str]] = None) -> RouteDecision:
        # 0. 澄清回填
        if pending_clarify:
            hit = self._match_clarify(message, pending_clarify)
            if hit:
                return RouteDecision(intent=hit, confidence=0.95, reason="clarify_resolved",
                                     route_source="clarify_resolved")

        # 1. 规则层（仅当前输入）
        hit = rules.match(message)
        if hit:
            return RouteDecision(intent=hit, confidence=1.0, reason="rule", route_source="rule")

        # 1.5 否定短路：规则层未命中但存在「被否定的意图词」时，
        #     embedding 对否定不敏感（会把"不用推荐陪玩"按词面误判成 recommend），
        #     跳过 embedding 直接交 LLM 理解否定语义。
        if rules.negates_intent(message):
            return await llm_classifier.classify(message, recent_messages, compressed_summary)

        # 2. 粘性（仅 recommend/order）
        sticky_hit = sticky.check(message, last_intent)
        if sticky_hit:
            return RouteDecision(intent=sticky_hit, confidence=0.70, reason="sticky_continuation",
                                 route_source="sticky")

        # 3. Embedding
        emb = await self.embedding_router.classify(message, recent_messages)
        if emb:
            return emb

        # 4. LLM
        return await llm_classifier.classify(message, recent_messages, compressed_summary)

    def _match_clarify(self, message: str, options: List[str]) -> Optional[str]:
        t = message.strip()
        # 1. 等于候选意图中文名
        if t in _INTENT_NAMES and _INTENT_NAMES[t] in options:
            return _INTENT_NAMES[t]
        # 2. 命中候选意图规则层
        rule_hit = rules.match(t)
        if rule_hit in options:
            return rule_hit
        # 3. 与候选意图样例余弦相似度 ≥ 阈值（按有效后端取值，避免哈希向量够不到语义阈值）
        from app.llm.embedder import example_match_threshold, get_embedder
        from app.intent.examples import EXAMPLES

        qv = get_embedder().embed(t)
        best_intent, best_sim = None, 0.0
        for intent in options:
            vecs = get_embedder().embed_batch(EXAMPLES.get(intent, []))
            if len(vecs) == 0:
                continue
            sim = max(float(v.dot(qv)) for v in vecs)
            if sim > best_sim:
                best_intent, best_sim = intent, sim
        if best_intent and best_sim >= example_match_threshold():
            return best_intent
        return None
