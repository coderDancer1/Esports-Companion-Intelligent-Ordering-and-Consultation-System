"""端到端冒烟测试：不依赖外部服务，验证 recommend/RAG/order 三条主链路。"""
from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")


async def main() -> None:
    from app.config import get_settings
    from app.db.mysql import create_all
    from app.db.chroma_client import init_chroma
    from app.rag.indexer import load_index
    from app.seed import seed_demo_data
    from app.business.playmate.service import list_playmates
    from app.matching.profile_index import rebuild as rebuild_playmates
    from app.security.auth import AuthUser
    from app.orchestrator.core import get_orchestrator

    s = get_settings()
    print(f"SETTINGS: mysql={s.MYSQL_URL} redis={s.REDIS_URL!r} emb={s.EMBEDDING_BACKEND}")

    create_all()
    init_chroma()
    load_index()
    seed = seed_demo_data()
    print(f"SEED: {seed}")

    n = rebuild_playmates(list_playmates())
    print(f"PLAYMATE VECTORS: {n}")

    from app.db.vector_store import get_vector_store
    from app.db.chroma_client import COLLECTION_PLAYMATE_PROFILES, COLLECTION_KNOWLEDGE_BASE
    store = get_vector_store()
    print(f"VECTOR playmate count: {store.count(COLLECTION_PLAYMATE_PROFILES)}")
    print(f"VECTOR knowledge count: {store.count(COLLECTION_KNOWLEDGE_BASE)}")

    auth = AuthUser(user_id="u_1001", is_minor=False, token_exp=0)
    orch = get_orchestrator()

    cases = [
        "帮我推荐一个无畏契约钻石段位的陪玩",
        "帮我推荐一个英雄联盟带飞的陪玩",
        "陪玩怎么收费？",
        "查询订单 202611080001",
        "我的订单 202611080002 能退款吗",
        "退款规则是什么？",
    ]
    for i, msg in enumerate(cases):
        r = await orch.handle(auth, f"smoke_{i}", msg)
        print("\n" + "=" * 70)
        print(f"[Q] {msg}")
        print(f"[intent] {r.get('intent')} conf={r.get('confidence')} src={r.get('route_source')}")
        print(f"[reply] {r.get('reply')}")
        if r.get("cards"):
            for c in r["cards"]:
                print(f"   - card: {c.get('nickname')} {c.get('rank')} {c.get('price_per_hour')}元  score={c.get('match_score')} reason={c.get('reason')}")
        if r.get("clarify_options"):
            print(f"[clarify] {r.get('clarify_options')}")


if __name__ == "__main__":
    asyncio.run(main())
