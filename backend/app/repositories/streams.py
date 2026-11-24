from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stream


class StreamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, stream_id: int) -> Stream | None:
        return await self.session.get(Stream, stream_id)

    async def get_for_update(self, stream_id: int) -> Stream | None:
        """Блокирует строку потока на время транзакции (PostgreSQL), чтобы два PUSH
        одного потока не выполнились параллельно. В SQLite запись и так сериализована."""
        stmt = select(Stream).where(Stream.id == stream_id)
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
