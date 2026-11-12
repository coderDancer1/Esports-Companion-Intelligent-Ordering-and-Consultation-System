"""SQLAlchemy engine / session 工厂。

默认使用 SQLite（便于零依赖运行）；配置 MYSQL_URL 为 mysql+pymysql://... 时切换 MySQL。
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models import Base

_engine = None
_SessionLocal = None


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().MYSQL_URL
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if _is_sqlite(url):
            # 提取 sqlite 文件路径并确保目录存在
            path = url.split("sqlite:///", 1)[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
            _engine = create_engine(url, **kwargs)
            # WAL 提升并发写体验
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        else:
            _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope():
    """业务服务统一使用的短生命周期会话上下文。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    Base.metadata.create_all(bind=get_engine())


def drop_all() -> None:
    Base.metadata.drop_all(bind=get_engine())
