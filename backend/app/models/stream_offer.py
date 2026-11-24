from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.stream import Stream


class OfferStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def _status_type() -> Enum:
    return Enum(
        OfferStatus,
        name="offer_status",
        native_enum=False,
        length=16,
        values_callable=lambda enum: [member.value for member in enum],
    )


class StreamOffer(TimestampMixin, Base):
    """Привязка оффера к потоку.

    Хранит два состояния:
    * рабочее (status, share) — то, что видит и правит пользователь;
    * опубликованное (published_status, published_share) — что сейчас лежит в Keitaro
      по данным последнего FETCH/PUSH. published_status = NULL — привязка ещё
      ни разу не публиковалась (добавлена в обёртке).

    Поток «жёлтый» (есть неопубликованные изменения), если хотя бы у одной привязки
    рабочее состояние отличается от опубликованного. CANCEL возвращает рабочее
    состояние к опубликованному, PUSH делает наоборот.
    pinned — локальная настройка обёртки, в Keitaro не уходит.
    """

    __tablename__ = "stream_offers"
    __table_args__ = (
        UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),
        CheckConstraint("share >= 0 AND share <= 100", name="share_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(String(512), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[OfferStatus] = mapped_column(_status_type(), default=OfferStatus.ACTIVE)
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    published_status: Mapped[OfferStatus | None] = mapped_column(_status_type(), nullable=True)
    published_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def is_active(self) -> bool:
        return self.status is OfferStatus.ACTIVE

    @property
    def is_dirty(self) -> bool:
        if self.published_status is None:
            # Новая привязка: неопубликована, пока активна.
            return self.status is OfferStatus.ACTIVE
        if self.status != self.published_status:
            return True
        return self.status is OfferStatus.ACTIVE and self.share != self.published_share
