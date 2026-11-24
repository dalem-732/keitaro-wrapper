"""Типизированные модели ответов Keitaro Admin API v1.

Описаны только поля, которые нужны обёртке; остальные сохраняются (extra="allow"),
чтобы изменения на стороне Keitaro не ломали разбор.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KtModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class KtNamed(KtModel):
    id: int
    name: str


class KtDomain(KtNamed):
    state: str | None = None


class KtGroup(KtNamed):
    type: str | None = None


class KtTrafficSource(KtNamed):
    state: str | None = None


class KtOffer(KtNamed):
    state: str | None = None
    country: list[str] = Field(default_factory=list)


class KtCampaign(KtNamed):
    alias: str | None = None
    type: str | None = None
    state: str | None = None
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None
    domain: str | None = None
    group: str | None = None


class KtFilter(KtModel):
    name: str
    mode: Literal["accept", "reject"] | str
    payload: Any = None


class KtStreamOffer(KtModel):
    offer_id: int
    share: int = 0
    state: str = "active"


class KtStream(KtNamed):
    campaign_id: int
    position: int = 0
    state: str | None = None
    type: str | None = None
    schema_: str | None = Field(default=None, alias="schema")
    action_type: str | None = None
    action_payload: Any = None
    filters: list[KtFilter] = Field(default_factory=list)
    offers: list[KtStreamOffer] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StreamOfferPayload(BaseModel):
    """Элемент поля offers в PUT /streams/{id}: заменяет весь состав офферов потока."""

    offer_id: int
    share: int
    state: Literal["active"] = "active"
