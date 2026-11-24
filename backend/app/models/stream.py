from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.stream_offer import StreamOffer

OFFER_SCHEMAS = frozenset({"landings", "offers"})


class Stream(TimestampMixin, Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    kt_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str | None] = mapped_column(String(32))
    schema: Mapped[str | None] = mapped_column(String(32))
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[Campaign] = relationship(back_populates="streams", lazy="joined")
    offers: Mapped[list[StreamOffer]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.sort_order",
        lazy="selectin",
    )

    @property
    def accepts_offers(self) -> bool:
        """Поток с офферами (схема landings/offers) или уже содержащий привязки офферов."""
        return (self.schema or "") in OFFER_SCHEMAS or bool(self.offers)
