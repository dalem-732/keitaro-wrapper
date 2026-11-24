"""Справочники Keitaro для формы создаватора: домены, группы, источники трафика."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.keitaro import KeitaroClient
from app.keitaro.schemas import KtDomain, KtGroup, KtNamed, KtTrafficSource

N = TypeVar("N", bound=KtNamed)


def pick(items: Sequence[N], wanted: int | None, default: str, kind: str) -> N:
    """Выбрать сущность по явному id, иначе по настройке (имя или id), иначе первую."""
    if wanted is not None:
        for item in items:
            if item.id == wanted:
                return item
        raise ValidationFailed(f"{kind} с id {wanted} не найден в Keitaro.")
    if default:
        for item in items:
            if item.name.lower() == default.lower() or str(item.id) == default:
                return item
    if items:
        return items[0]
    raise ValidationFailed(f"В Keitaro нет ни одного значения «{kind}» — создайте его в админке.")


@dataclass(slots=True)
class KeitaroMeta:
    domains: list[KtDomain]
    groups: list[KtGroup]
    traffic_sources: list[KtTrafficSource]
    defaults: dict[str, int | None]


class MetaService:
    def __init__(self, client: KeitaroClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def load(self) -> KeitaroMeta:
        domains = await self.client.list_domains()
        groups = await self.client.list_groups()
        sources = await self.client.list_traffic_sources()

        def default_id(items: Sequence[KtNamed], name: str) -> int | None:
            try:
                return pick(items, None, name, "").id
            except ValidationFailed:
                return None

        return KeitaroMeta(
            domains=domains,
            groups=groups,
            traffic_sources=sources,
            defaults={
                "domain_id": default_id(domains, self.settings.default_domain),
                "group_id": default_id(groups, self.settings.default_group),
                "traffic_source_id": default_id(sources, self.settings.default_traffic_source),
            },
        )
