"""Кэш справочника офферов Keitaro для поиска с автодополнением.

Эмулятор (как и Keitaro) отдаёт офферы одним списком без серверного поиска,
поэтому список кэшируется на несколько минут, а поиск идёт по ID и названию локально.
"""

from __future__ import annotations

import asyncio
import time

from app.keitaro import KeitaroClient, KeitaroNotFoundError
from app.keitaro.schemas import KtOffer


class OfferCatalog:
    def __init__(self, client: KeitaroClient, ttl_seconds: int = 300) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._offers: dict[int, KtOffer] = {}
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        return bool(self._offers) and time.monotonic() - self._loaded_at < self._ttl

    async def all(self, *, refresh: bool = False) -> list[KtOffer]:
        if refresh or not self._fresh():
            async with self._lock:
                if refresh or not self._fresh():
                    offers = await self._client.list_offers()
                    self._offers = {o.id: o for o in offers}
                    self._loaded_at = time.monotonic()
        return list(self._offers.values())

    async def search(self, query: str, limit: int = 20) -> list[KtOffer]:
        offers = await self.all()
        q = query.strip().lower()
        if not q:
            return sorted(offers, key=lambda o: o.id)[:limit]
        if q.isdigit():
            exact = [o for o in offers if str(o.id) == q]
            prefix = [o for o in offers if str(o.id).startswith(q) and str(o.id) != q]
            by_name = [o for o in offers if q in o.name.lower() and o not in exact + prefix]
            ranked = exact + sorted(prefix, key=lambda o: o.id) + by_name
        else:
            ranked = sorted((o for o in offers if q in o.name.lower()), key=lambda o: o.id)
        return ranked[:limit]

    async def get(self, offer_id: int) -> KtOffer | None:
        await self.all()
        offer = self._offers.get(offer_id)
        if offer is not None:
            return offer
        try:
            offer = await self._client.get_offer(offer_id)
        except KeitaroNotFoundError:
            return None
        self._offers[offer.id] = offer
        return offer

    async def name_of(self, offer_id: int) -> str:
        offer = await self.get(offer_id)
        return offer.name if offer else f"Оффер #{offer_id}"
