"""数据库引擎与会话工厂。

- 以 DATABASE_URL 为准，开发环境默认 SQLite，生产使用 RDS for MySQL。
- 不依赖应用启动时自动重建数据库；初始化和迁移由 scripts/ 与 alembic 显式执行。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args: dict[str, object] = {}
if settings.is_sqlite:
    # 允许多线程共享同一 SQLite 连接（FastAPI 线程池）
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.resolved_database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个会话，异常时回滚，结束时关闭。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()