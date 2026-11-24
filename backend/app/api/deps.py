from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import session_scope
from app.keitaro import KeitaroClient
from app.services.offer_catalog import OfferCatalog


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.sessionmaker):
        yield session


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_client(request: Request) -> KeitaroClient:
    client: KeitaroClient = request.app.state.keitaro
    return client


def get_catalog(request: Request) -> OfferCatalog:
    catalog: OfferCatalog = request.app.state.catalog
    return catalog


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClientDep = Annotated[KeitaroClient, Depends(get_client)]
CatalogDep = Annotated[OfferCatalog, Depends(get_catalog)]
