from fastapi import APIRouter, status

from app.api.deps import CatalogDep, ClientDep, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.errors import NotFoundError, WriteForbiddenError
from app.models import Campaign
from app.repositories import CampaignRepository
from app.schemas.api import (
    CampaignOut,
    CampaignSummaryOut,
    CreateCampaignIn,
    ImportIn,
    KtCampaignOut,
    PushOut,
    PushResultOut,
)
from app.services.creator_service import CreateCampaignCommand, CreatorService
from app.services.publish_service import PublishService
from app.services.sync_service import SyncService

router = APIRouter(tags=["campaigns"])


def campaign_out(campaign: Campaign, settings: Settings) -> CampaignOut:
    prefix = settings.write_allowed_prefix
    return CampaignOut.build(
        campaign,
        writable=not prefix or campaign.name.startswith(prefix),
        admin_url=settings.admin_base_url,
    )


async def load_campaign(session: SessionDep, campaign_id: int) -> Campaign:
    campaign = await CampaignRepository(session).get(campaign_id)
    if campaign is None:
        raise NotFoundError(f"Кампания {campaign_id} не найдена в обёртке.")
    return campaign


@router.post("/creator/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CreateCampaignIn,
    session: SessionDep,
    client: ClientDep,
    catalog: CatalogDep,
    settings: SettingsDep,
) -> CampaignOut:
    """Часть 1: создать кампанию с двумя потоками (гео → Google, остальные → оффер)."""
    kt_campaign = await CreatorService(client, catalog, settings).create(
        CreateCampaignCommand(**body.model_dump())
    )
    campaign = await SyncService(session, client, catalog).fetch(kt_campaign.id)
    return campaign_out(campaign, settings)


@router.get("/keitaro/campaigns", response_model=list[KtCampaignOut])
async def list_keitaro_campaigns(session: SessionDep, client: ClientDep) -> list[KtCampaignOut]:
    local = {c.kt_id: c.id for c in await CampaignRepository(session).list()}
    return [
        KtCampaignOut(
            kt_id=c.id,
            name=c.name,
            domain=c.domain,
            group=c.group,
            state=c.state,
            local_id=local.get(c.id),
        )
        for c in await client.list_campaigns(limit=500)
    ]


@router.get("/campaigns", response_model=list[CampaignSummaryOut])
async def list_campaigns(session: SessionDep) -> list[CampaignSummaryOut]:
    return [CampaignSummaryOut.model_validate(c) for c in await CampaignRepository(session).list()]


@router.post("/campaigns/import", response_model=CampaignOut)
async def import_campaign(
    body: ImportIn,
    session: SessionDep,
    client: ClientDep,
    catalog: CatalogDep,
    settings: SettingsDep,
) -> CampaignOut:
    """Подключить существующую кампанию Keitaro к редактору (первый FETCH)."""
    campaign = await SyncService(session, client, catalog).fetch(body.kt_id)
    return campaign_out(campaign, settings)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: int, session: SessionDep, settings: SettingsDep) -> CampaignOut:
    return campaign_out(await load_campaign(session, campaign_id), settings)


@router.post("/campaigns/{campaign_id}/fetch", response_model=CampaignOut)
async def fetch_campaign(
    campaign_id: int,
    session: SessionDep,
    client: ClientDep,
    catalog: CatalogDep,
    settings: SettingsDep,
) -> CampaignOut:
    """FETCH STREAMS FROM KT."""
    campaign = await load_campaign(session, campaign_id)
    campaign = await SyncService(session, client, catalog).fetch(campaign.kt_id)
    return campaign_out(campaign, settings)


@router.post("/campaigns/{campaign_id}/push", response_model=PushOut)
async def push_campaign(
    campaign_id: int,
    session: SessionDep,
    client: ClientDep,
    settings: SettingsDep,
    force: bool = False,
) -> PushOut:
    """PUSH TO KT для всех потоков с неопубликованными изменениями."""
    campaign = await load_campaign(session, campaign_id)
    results = await PublishService(client, settings).push_campaign(campaign, force=force)
    return PushOut(
        results=[
            PushResultOut(stream_id=r.stream_id, changed=r.changed, message=r.message)
            for r in results
        ],
        campaign=campaign_out(campaign, settings),
    )


@router.delete("/campaigns/{campaign_id}/keitaro", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign_everywhere(
    campaign_id: int, session: SessionDep, client: ClientDep, settings: SettingsDep
) -> None:
    """Удалить тестовую кампанию из Keitaro и из обёртки (только с разрешённым префиксом)."""
    campaign = await load_campaign(session, campaign_id)
    if settings.write_allowed_prefix and not campaign.name.startswith(
        settings.write_allowed_prefix
    ):
        raise WriteForbiddenError("Удалять можно только свои тестовые кампании.")
    await client.delete_campaign(campaign.kt_id)
    await CampaignRepository(session).delete(campaign)
