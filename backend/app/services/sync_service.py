"""FETCH STREAMS FROM KT: загрузка кампании и потоков из Keitaro в локальную базу."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.keitaro import KeitaroClient, KeitaroNotFoundError
from app.keitaro.schemas import KtCampaign, KtStream
from app.models import Campaign, OfferStatus, Stream, StreamOffer
from app.repositories import CampaignRepository
from app.services.offer_catalog import OfferCatalog


class SyncService:
    def __init__(self, session: AsyncSession, client: KeitaroClient, catalog: OfferCatalog) -> None:
        self.session = session
        self.client = client
        self.catalog = catalog
        self.campaigns = CampaignRepository(session)

    async def fetch(self, kt_campaign_id: int) -> Campaign:
        """Подтянуть кампанию из Keitaro. Неопубликованные локальные правки сбрасываются:
        FETCH означает «взять за основу то, что сейчас в Keitaro»."""
        try:
            kt_campaign = await self.client.get_campaign(kt_campaign_id)
        except KeitaroNotFoundError as exc:
            raise NotFoundError(f"Кампания {kt_campaign_id} не найдена в Keitaro.") from exc
        kt_streams = await self.client.list_streams(kt_campaign_id)

        campaign = await self.campaigns.get_by_kt_id(kt_campaign_id)
        if campaign is None:
            campaign = Campaign(kt_id=kt_campaign_id, name=kt_campaign.name)
            campaign.streams = []
            self.campaigns.add(campaign)
        self._apply_campaign(campaign, kt_campaign)

        by_kt_id = {s.kt_id: s for s in campaign.streams}
        seen: set[int] = set()
        for kt_stream in kt_streams:
            seen.add(kt_stream.id)
            stream = by_kt_id.get(kt_stream.id)
            if stream is None:
                stream = Stream(kt_id=kt_stream.id, name=kt_stream.name)
                stream.offers = []
                campaign.streams.append(stream)
            await self._apply_stream(stream, kt_stream)
        # Потоки, удалённые в самом Keitaro, удаляем и локально.
        for stream in list(campaign.streams):
            if stream.kt_id not in seen:
                campaign.streams.remove(stream)
        campaign.streams.sort(key=lambda s: (s.position, s.kt_id))
        campaign.last_fetched_at = utcnow()
        await self.session.flush()
        return campaign

    @staticmethod
    def _apply_campaign(campaign: Campaign, kt: KtCampaign) -> None:
        campaign.name = kt.name
        campaign.alias = kt.alias
        campaign.domain = kt.domain
        campaign.group_name = kt.group
        extra = kt.model_extra or {}
        source = extra.get("traffic_source") or extra.get("traffic_source_name")
        campaign.traffic_source_name = str(source) if source else None

    async def _apply_stream(self, stream: Stream, kt: KtStream) -> None:
        stream.name = kt.name
        stream.position = kt.position
        stream.type = kt.type
        stream.schema = kt.schema_

        kt_offers = {o.offer_id: o for o in kt.offers}
        existing = {link.offer_id: link for link in stream.offers}

        # Неопубликованные новые привязки, которых нет в Keitaro, сбрасываются.
        for link in list(stream.offers):
            if link.published_status is None and link.offer_id not in kt_offers:
                stream.offers.remove(link)
                existing.pop(link.offer_id, None)

        order = 0
        for kt_offer in kt.offers:
            found = existing.get(kt_offer.offer_id)
            if found is None:
                link = StreamOffer(offer_id=kt_offer.offer_id, pinned=False)
                stream.offers.append(link)
            else:
                link = found
            link.offer_name = await self.catalog.name_of(kt_offer.offer_id)
            link.status = OfferStatus.ACTIVE
            link.share = kt_offer.share
            link.published_status = OfferStatus.ACTIVE
            link.published_share = kt_offer.share
            link.archived_at = None
            link.sort_order = order
            order += 1

        # Офферы, которые обёртка знала, но которых больше нет в Keitaro, уходят в архив.
        for offer_id, link in existing.items():
            if offer_id in kt_offers:
                continue
            if link.published_status is OfferStatus.ACTIVE or link.archived_at is None:
                link.archived_at = utcnow()
            link.status = OfferStatus.ARCHIVED
            link.share = 0
            link.pinned = False
            link.published_status = OfferStatus.ARCHIVED
            link.published_share = 0
            link.sort_order = order
            order += 1
        stream.offers.sort(key=lambda link: link.sort_order)
