"""Локальное редактирование офферов потока (до публикации в Keitaro).

Все операции меняют только рабочее состояние привязок; Keitaro не трогается до PUSH.
"""

from __future__ import annotations

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.db.base import utcnow
from app.models import OfferStatus, Stream, StreamOffer
from app.services.offer_catalog import OfferCatalog
from app.services.stream_state import apply_rebalance


def _link(stream: Stream, link_id: int) -> StreamOffer:
    for link in stream.offers:
        if link.id == link_id:
            return link
    raise NotFoundError(f"Оффер-привязка {link_id} не найдена в потоке {stream.name}")


class StreamEditor:
    def __init__(self, catalog: OfferCatalog) -> None:
        self.catalog = catalog

    async def add_offer(self, stream: Stream, offer_id: int) -> StreamOffer:
        if not stream.accepts_offers:
            raise ValidationFailed(
                "Это поток без офферов (например, редирект по гео) — офферы в него не добавляются."
            )
        existing = next((link for link in stream.offers if link.offer_id == offer_id), None)
        if existing is not None:
            if existing.is_active:
                raise ConflictError(f"Оффер {offer_id} уже есть в потоке.")
            # Оффер лежит в архиве потока — добавление равносильно BRING BACK.
            return self.restore(stream, existing.id)

        offer = await self.catalog.get(offer_id)
        if offer is None:
            raise ValidationFailed(f"Оффер {offer_id} не найден в Keitaro.")
        link = StreamOffer(
            offer_id=offer.id,
            offer_name=offer.name,
            sort_order=max((link.sort_order for link in stream.offers), default=-1) + 1,
            status=OfferStatus.ACTIVE,
            share=0,
            pinned=False,
            published_status=None,
            published_share=None,
        )
        stream.offers.append(link)
        apply_rebalance(stream)
        return link

    def remove(self, stream: Stream, link_id: int) -> None:
        link = _link(stream, link_id)
        if not link.is_active:
            raise ConflictError("Оффер уже удалён из потока.")
        if link.published_status is None:
            # Привязка ещё не попадала в Keitaro — архивировать нечего, просто убираем.
            stream.offers.remove(link)
        else:
            link.status = OfferStatus.ARCHIVED
            link.share = 0
            link.pinned = False
            link.archived_at = utcnow()
        apply_rebalance(stream)

    def restore(self, stream: Stream, link_id: int) -> StreamOffer:
        link = _link(stream, link_id)
        if link.is_active:
            raise ConflictError("Оффер и так активен.")
        link.status = OfferStatus.ACTIVE
        link.archived_at = None
        apply_rebalance(stream)
        return link

    def set_pinned(self, stream: Stream, link_id: int, pinned: bool) -> None:
        link = _link(stream, link_id)
        if not link.is_active:
            raise ValidationFailed("Закрепить можно только активный оффер.")
        link.pinned = pinned
        if not pinned:
            # Открепленный оффер снова участвует в равном распределении остатка.
            apply_rebalance(stream)

    def set_share(self, stream: Stream, link_id: int, share: int) -> None:
        """Ручная доля: оффер закрепляется на этом значении, остальные пересчитываются."""
        link = _link(stream, link_id)
        if not link.is_active:
            raise ValidationFailed("Долю можно задать только активному офферу.")
        if not 1 <= share <= 100:
            raise ValidationFailed("Доля должна быть от 1 до 100%.")
        link.share = share
        link.pinned = True
        apply_rebalance(stream)

    def rebalance(self, stream: Stream) -> None:
        apply_rebalance(stream)

    def cancel(self, stream: Stream) -> None:
        """CANCEL: вернуть рабочее состояние к опубликованному."""
        for link in list(stream.offers):
            if link.published_status is None:
                stream.offers.remove(link)  # новая привязка — удаляется целиком
                continue
            link.status = link.published_status
            if link.published_status is OfferStatus.ACTIVE:
                link.share = link.published_share or 0
                link.archived_at = None
            else:
                link.share = 0
                link.pinned = False
