from fastapi import APIRouter, Query

from app.api.deps import CatalogDep, ClientDep, SettingsDep
from app.core.countries import COUNTRIES
from app.schemas.api import MetaOut, NamedOut, OfferOut
from app.services.meta_service import MetaService

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaOut)
async def get_meta(client: ClientDep, settings: SettingsDep) -> MetaOut:
    data = await MetaService(client, settings).load()
    return MetaOut(
        domains=[NamedOut.model_validate(d) for d in data.domains],
        groups=[NamedOut.model_validate(g) for g in data.groups],
        traffic_sources=[NamedOut.model_validate(s) for s in data.traffic_sources],
        defaults=data.defaults,
        campaign_name_prefix=settings.campaign_name_prefix,
        write_allowed_prefix=settings.write_allowed_prefix,
        keitaro_admin_url=settings.admin_base_url,
        countries=COUNTRIES,
    )


@router.get("/offers/search", response_model=list[OfferOut])
async def search_offers(
    catalog: CatalogDep,
    q: str = Query(
        "", max_length=100, description="ID оффера (или его начало) либо часть названия"
    ),
    limit: int = Query(20, ge=1, le=100),
) -> list[OfferOut]:
    return [OfferOut.model_validate(o) for o in await catalog.search(q, limit)]
