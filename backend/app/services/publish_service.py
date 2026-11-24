"""PUSH TO KT: публикация локальных изменений потока в Keitaro."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import ConflictError, UpstreamError, ValidationFailed, WriteForbiddenError
from app.db.base import utcnow
from app.keitaro import KeitaroClient
from app.keitaro.schemas import KtStream, StreamOfferPayload
from app.models import Campaign, OfferStatus, Stream
from app.services.stream_state import is_dirty, stream_issues
from app.services.weights import ISSUE_MESSAGES

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PushResult:
    stream_id: int
    changed: bool  # был ли реальный PUT в Keitaro
    message: str


def _offer_set(pairs: list[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    return frozenset(pairs)


class PublishService:
    def __init__(self, client: KeitaroClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def ensure_writable(self, campaign: Campaign) -> None:
        prefix = self.settings.write_allowed_prefix
        if prefix and not campaign.name.startswith(prefix):
            raise WriteForbiddenError(
                f"Публикация разрешена только в кампании с префиксом «{prefix}». "
                "Это защита от случайной правки чужих кампаний в общем аккаунте "
                "(настройка WRITE_ALLOWED_PREFIX)."
            )

    @staticmethod
    def desired_offers(stream: Stream) -> list[StreamOfferPayload]:
        return [
            StreamOfferPayload(offer_id=link.offer_id, share=link.share)
            for link in stream.offers
            if link.is_active
        ]

    @staticmethod
    def published_pairs(stream: Stream) -> list[tuple[int, int]]:
        return [
            (link.offer_id, link.published_share or 0)
            for link in stream.offers
            if link.published_status is OfferStatus.ACTIVE
        ]

    async def push_stream(
        self, campaign: Campaign, stream: Stream, *, force: bool = False
    ) -> PushResult:
        self.ensure_writable(campaign)
        if not is_dirty(stream):
            return PushResult(stream.id, False, "Нет неопубликованных изменений.")
        issues = stream_issues(stream)
        if issues:
            raise ValidationFailed(
                " ".join(ISSUE_MESSAGES[i] for i in issues),
                details={"issues": [i.value for i in issues]},
            )
        desired = self.desired_offers(stream)
        desired_pairs = [(o.offer_id, o.share) for o in desired]
        if sum(share for _, share in desired_pairs) != 100:  # последняя страховка
            raise ValidationFailed("Сумма долей не равна 100% — публикация остановлена.")

        current = await self.client.get_stream(stream.kt_id)
        current_pairs = [(o.offer_id, o.share) for o in current.offers]
        if not force and _offer_set(current_pairs) != _offer_set(self.published_pairs(stream)):
            raise ConflictError(
                "Поток изменили в Keitaro после последнего FETCH. "
                "Сделайте FETCH STREAMS FROM KT, чтобы не затереть чужие правки, "
                "или опубликуйте принудительно.",
                details={"keitaro_offers": current_pairs},
            )

        changed = _offer_set(current_pairs) != _offer_set(desired_pairs)
        if changed:
            updated = await self.client.replace_stream_offers(stream.kt_id, desired)
            self._verify(updated, desired_pairs)
            logger.info("Pushed stream %s: %s", stream.kt_id, desired_pairs)
        self._mark_published(stream)
        return PushResult(
            stream.id,
            changed,
            "Опубликовано в Keitaro." if changed else "В Keitaro уже актуальное состояние.",
        )

    async def push_campaign(self, campaign: Campaign, *, force: bool = False) -> list[PushResult]:
        self.ensure_writable(campaign)
        return [
            await self.push_stream(campaign, stream, force=force)
            for stream in campaign.streams
            if is_dirty(stream)
        ]

    @staticmethod
    def _verify(updated: KtStream, desired_pairs: list[tuple[int, int]]) -> None:
        got = _offer_set([(o.offer_id, o.share) for o in updated.offers])
        if got != _offer_set(desired_pairs):
            raise UpstreamError(
                "Keitaro принял запрос, но сохранил другой состав офферов.",
                details={"expected": desired_pairs, "got": sorted(got)},
            )

    @staticmethod
    def _mark_published(stream: Stream) -> None:
        now = utcnow()
        for link in stream.offers:
            link.published_status = link.status
            link.published_share = link.share if link.is_active else 0
            if not link.is_active and link.archived_at is None:
                link.archived_at = now
        stream.last_pushed_at = now
