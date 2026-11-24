"""Создаватор кампаний (часть 1 задания).

Кампания создаётся с ротацией потоков «по позиции», доменом, группой и источником.
Поток 1: все посетители из указанных стран → редирект на Google.
Поток 2 (default): все остальные → выбранный оффер (или несколько, доли поровну).
Если что-то пошло не так после создания кампании, она удаляется (компенсация),
чтобы в Keitaro не оставалось полуготовых кампаний.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.errors import ConflictError, UpstreamError, ValidationFailed
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro.schemas import KtCampaign
from app.services.geo import parse_geo
from app.services.meta_service import pick
from app.services.offer_catalog import OfferCatalog
from app.services.weights import split_evenly

logger = logging.getLogger(__name__)

NAME_MAX = 255


@dataclass(slots=True)
class CreateCampaignCommand:
    name: str
    geo: str | list[str]
    offer_ids: list[int]
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


def normalize_name(raw: str, prefix: str) -> str:
    name = " ".join(raw.split())
    if prefix and not name.startswith(prefix):
        name = prefix + name
    if not name or name == prefix:
        raise ValidationFailed("Введите название кампании.")
    if len(name) > NAME_MAX:
        raise ValidationFailed(f"Название длиннее {NAME_MAX} символов.")
    return name


class CreatorService:
    def __init__(self, client: KeitaroClient, catalog: OfferCatalog, settings: Settings) -> None:
        self.client = client
        self.catalog = catalog
        self.settings = settings

    async def create(self, cmd: CreateCampaignCommand) -> KtCampaign:
        name = normalize_name(cmd.name, self.settings.campaign_name_prefix)
        countries = parse_geo(cmd.geo)
        offer_ids = list(dict.fromkeys(cmd.offer_ids))
        if not offer_ids:
            raise ValidationFailed("Выберите оффер.")
        for offer_id in offer_ids:
            if await self.catalog.get(offer_id) is None:
                raise ValidationFailed(f"Оффер {offer_id} не найден в Keitaro.")

        domain = pick(
            await self.client.list_domains(), cmd.domain_id, self.settings.default_domain, "Домен"
        )
        group = pick(
            await self.client.list_groups(), cmd.group_id, self.settings.default_group, "Группа"
        )
        source = pick(
            await self.client.list_traffic_sources(),
            cmd.traffic_source_id,
            self.settings.default_traffic_source,
            "Источник",
        )

        existing = await self.client.list_campaigns(limit=1000)
        if any(c.name == name for c in existing):
            raise ConflictError(f"Кампания «{name}» уже существует в Keitaro.")

        campaign = await self.client.create_campaign(
            {
                "name": name,
                "type": "position",  # ротация потоков «По позиции»
                "state": "active",
                "domain_id": domain.id,
                "group_id": group.id,
                "traffic_source_id": source.id,
            }
        )
        try:
            await self._create_streams(campaign.id, countries, offer_ids)
            await self._verify(campaign.id, domain.id, group.id, source.id, countries, offer_ids)
        except Exception:
            logger.exception("Creator failed, rolling back campaign %s", campaign.id)
            try:
                await self.client.delete_campaign(campaign.id)
            except KeitaroError:
                logger.exception("Rollback of campaign %s failed", campaign.id)
            raise
        return campaign

    def stream_payloads(
        self, campaign_id: int, countries: list[str], offer_ids: list[int]
    ) -> list[dict[str, Any]]:
        shares = split_evenly(100, len(offer_ids))
        return [
            {
                "campaign_id": campaign_id,
                "name": f"Flow 1 · {','.join(countries)} → Google",
                "type": "regular",
                "schema": "redirect",
                "action_type": "http",
                "action_payload": self.settings.geo_redirect_url,
                "position": 1,
                "state": "active",
                "filter_or": False,
                "filters": [{"name": "country", "mode": "accept", "payload": countries}],
            },
            {
                "campaign_id": campaign_id,
                "name": "Flow 2 · Offers",
                "type": "default",
                "schema": "landings",
                "position": 2,
                "state": "active",
                "offers": [
                    {"offer_id": offer_id, "share": share, "state": "active"}
                    for offer_id, share in zip(offer_ids, shares, strict=True)
                ],
            },
        ]

    async def _create_streams(
        self, campaign_id: int, countries: list[str], offer_ids: list[int]
    ) -> None:
        for payload in self.stream_payloads(campaign_id, countries, offer_ids):
            await self.client.create_stream(payload)

    async def _verify(
        self,
        campaign_id: int,
        domain_id: int,
        group_id: int,
        source_id: int,
        countries: list[str],
        offer_ids: list[int],
    ) -> None:
        """Перечитываем созданное из Keitaro и сверяем с тем, что отправляли."""
        campaign = await self.client.get_campaign(campaign_id)
        streams = await self.client.list_streams(campaign_id)
        problems: list[str] = []
        if (campaign.domain_id, campaign.group_id, campaign.traffic_source_id) != (
            domain_id,
            group_id,
            source_id,
        ):
            problems.append("домен/группа/источник не сохранились")
        if len(streams) != 2:
            problems.append(f"ожидалось 2 потока, получено {len(streams)}")
        else:
            geo, offers = streams
            country_filters = [f for f in geo.filters if f.name == "country"]
            if not country_filters or sorted(country_filters[0].payload or []) != sorted(countries):
                problems.append("фильтр стран в потоке 1 не совпадает")
            if geo.action_payload != self.settings.geo_redirect_url:
                problems.append("редирект потока 1 не совпадает")
            if sorted(o.offer_id for o in offers.offers) != sorted(offer_ids):
                problems.append("офферы в потоке 2 не совпадают")
            if sum(o.share for o in offers.offers) != 100:
                problems.append("сумма долей в потоке 2 не 100%")
        if problems:
            raise UpstreamError(
                "Keitaro сохранил кампанию не так, как ожидалось: " + "; ".join(problems)
            )
