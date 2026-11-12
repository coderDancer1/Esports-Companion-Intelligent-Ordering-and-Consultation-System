"""FastAPI 应用入口：创建 app、注册路由、启动/关闭钩子。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings

logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化存储与索引，填充演示数据
    from app.db.mysql import create_all
    from app.db.chroma_client import init_chroma
    from app.rag.indexer import load_index

    create_all()
    init_chroma()
    load_index()

    if get_settings().SEED_DEMO_DATA:
        from app.seed import seed_demo_data
        try:
            summary = seed_demo_data()
            if summary.get("seeded"):
                logger.info("演示数据已填充: %s", summary)
        except Exception as e:  # noqa: BLE001
            logger.warning("演示数据填充失败（可忽略）: %s", e)

    # 内存向量库不跨进程，需每次启动从 MySQL 重建陪玩师向量索引
    try:
        from app.business.playmate.service import list_playmates
        from app.matching.profile_index import rebuild as rebuild_playmates
        n = rebuild_playmates(list_playmates())
        logger.info("陪玩师向量索引已重建: %d 条", n)
    except Exception as e:  # noqa: BLE001
        logger.warning("陪玩师向量索引重建失败（可忽略）: %s", e)

    _print_demo_tokens()
    yield
    logger.info("应用关闭")


def _print_demo_tokens() -> None:
    from app.security.auth import mint_token
    logger.info("=" * 60)
    logger.info("演示 token（Authorization: Bearer <token>）：")
    logger.info("  普通用户 u_1001: %s", mint_token("u_1001", is_minor=False))
    logger.info("  未成年 u_2001:   %s", mint_token("u_2001", is_minor=True))
    logger.info("  也支持开发模式：Bearer demo_u_1001")
    logger.info("=" * 60)


app = FastAPI(title="电竞陪玩智能点单与咨询系统", version="2.1.0", lifespan=lifespan)

from app.api import chat, feedback, health, order, playmate, ticket  # noqa: E402
from app.api.admin import knowledge as admin_knowledge  # noqa: E402
from app.api.admin import logs as admin_logs  # noqa: E402

app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])
app.include_router(order.router, prefix="/api/v1", tags=["order"])
app.include_router(playmate.router, prefix="/api/v1", tags=["playmate"])
app.include_router(ticket.router, prefix="/api/v1", tags=["ticket"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(admin_knowledge.router, prefix="/api/v1", tags=["admin"])
app.include_router(admin_logs.router, prefix="/api/v1", tags=["admin"])


@app.get("/")
def root():
    return {"name": "电竞陪玩智能点单与咨询系统", "docs": "/docs", "health": "/api/v1/healthz"}
