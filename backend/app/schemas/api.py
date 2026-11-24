"""Pydantic-схемы HTTP API обёртки."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Campaign, OfferStatus, Stream, StreamOffer
from app.services.stream_state import is_dirty, stream_issues
from app.services.weights import ISSUE_MESSAGES


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NamedOut(ORM):
    id: int
    name: str


class OfferOut(NamedOut):
    country: list[str] = []


class MetaOut(BaseModel):
    domains: list[NamedOut]
    groups: list[NamedOut]
    traffic_sources: list[NamedOut]
    defaults: dict[str, int | None]
    campaign_name_prefix: str
    write_allowed_prefix: str
    keitaro_admin_url: str
    countries: dict[str, str]


OfferBadge = Literal["active", "new", "removed_pending", "restored_pending", "archived"]


class StreamOfferOut(BaseModel):
    id: int
    offer_id: int
    offer_name: str
    status: OfferStatus
    share: int
    pinned: bool
    published_status: OfferStatus | None
    published_share: int | None
    is_dirty: bool
    badge: OfferBadge

    @classmethod
    def build(cls, link: StreamOffer) -> StreamOfferOut:
        if link.published_status is None:
            badge: OfferBadge = "new"
        elif link.status is OfferStatus.ARCHIVED:
            badge = "removed_pending" if link.published_status is OfferStatus.ACTIVE else "archived"
        elif link.published_status is OfferStatus.ARCHIVED:
            badge = "restored_pending"
        else:
            badge = "active"
        return cls(
            id=link.id,
            offer_id=link.offer_id,
            offer_name=link.offer_name,
            status=link.status,
            share=link.share,
            pinned=link.pinned,
            published_status=link.published_status,
            published_share=link.published_share,
            is_dirty=link.is_dirty,
            badge=badge,
        )


class IssueOut(BaseModel):
    code: str
    message: str


class StreamOut(BaseModel):
    id: int
    kt_id: int
    name: str
    position: int
    type: str | None
    schema_: str | None = Field(serialization_alias="schema")
    accepts_offers: bool
    is_dirty: bool
    issues: list[IssueOut]
    active_share_sum: int
    last_pushed_at: datetime | None
    offers: list[StreamOfferOut]

    @classmethod
    def build(cls, stream: Stream) -> StreamOut:
        return cls(
            id=stream.id,
            kt_id=stream.kt_id,
            name=stream.name,
            position=stream.position,
            type=stream.type,
            schema_=stream.schema,
            accepts_offers=stream.accepts_offers,
            is_dirty=is_dirty(stream),
            issues=[
                IssueOut(code=i.value, message=ISSUE_MESSAGES[i]) for i in stream_issues(stream)
            ],
            active_share_sum=sum(link.share for link in stream.offers if link.is_active),
            last_pushed_at=stream.last_pushed_at,
            offers=[StreamOfferOut.build(link) for link in stream.offers],
        )


class CampaignSummaryOut(ORM):
    id: int
    kt_id: int
    name: str
    domain: str | None
    group_name: str | None
    last_fetched_at: datetime | None


class CampaignOut(BaseModel):
    id: int
    kt_id: int
    name: str
    alias: str | None
    domain: str | None
    group_name: str | None
    last_fetched_at: datetime | None
    writable: bool
    keitaro_url: str
    streams: list[StreamOut]

    @classmethod
    def build(cls, campaign: Campaign, *, writable: bool, admin_url: str) -> CampaignOut:
        return cls(
            id=campaign.id,
            kt_id=campaign.kt_id,
            name=campaign.name,
            alias=campaign.alias,
            domain=campaign.domain,
            group_name=campaign.group_name,
            last_fetched_at=campaign.last_fetched_at,
            writable=writable,
            keitaro_url=f"{admin_url}/#!/campaigns/{campaign.kt_id}",
            streams=[StreamOut.build(s) for s in campaign.streams],
        )


class KtCampaignOut(BaseModel):
    kt_id: int
    name: str
    domain: str | None
    group: str | None
    state: str | None
    local_id: int | None


class CreateCampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["demo"])
    geo: str = Field(min_length=2, examples=["MX,AU,RO"])
    offer_ids: list[int] = Field(min_length=1, max_length=20, examples=[[18001]])
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None

    @field_validator("offer_ids")
    @classmethod
    def _positive(cls, value: list[int]) -> list[int]:
        if any(v <= 0 for v in value):
            raise ValueError("ID оффера должен быть положительным")
        return value


class ImportIn(BaseModel):
    kt_id: int = Field(gt=0)


class AddOfferIn(BaseModel):
    offer_id: int = Field(gt=0)


class UpdateOfferIn(BaseModel):
    pinned: bool | None = None
    share: int | None = Field(default=None, ge=1, le=100)


class PushResultOut(BaseModel):
    stream_id: int
    changed: bool
    message: str


class StreamPushOut(BaseModel):
    result: PushResultOut
    stream: StreamOut


class PushOut(BaseModel):
    results: list[PushResultOut]
    campaign: CampaignOut
