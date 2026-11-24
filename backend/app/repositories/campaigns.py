from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, campaign_id: int) -> Campaign | None:
        return await self.session.get(Campaign, campaign_id)

    async def get_by_kt_id(self, kt_id: int) -> Campaign | None:
        result = await self.session.execute(select(Campaign).where(Campaign.kt_id == kt_id))
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[Campaign]:
        result = await self.session.execute(select(Campaign).order_by(Campaign.id.desc()))
        return result.scalars().all()

    def add(self, campaign: Campaign) -> None:
        self.session.add(campaign)

    async def delete(self, campaign: Campaign) -> None:
        await self.session.delete(campaign)
