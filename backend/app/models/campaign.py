from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.stream import Stream


class Campaign(TimestampMixin, Base):
    """Локальная копия кампании Keitaro, с которой работает редактор."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    kt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64))
    domain: Mapped[str | None] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(255))
    traffic_source_name: Mapped[str | None] = mapped_column(String(255))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    streams: Mapped[list[Stream]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stream.position",
        lazy="selectin",
    )
