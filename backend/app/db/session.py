from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        # В SQLite внешние ключи (и ON DELETE CASCADE) включаются отдельно для каждого соединения.
        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
