"""Расчёт производного состояния потока: неопубликованные изменения и проблемы долей."""

from __future__ import annotations

from app.models import Stream, StreamOffer
from app.services.weights import WeightIssue, WeightItem, rebalance, validate


def weight_items(stream: Stream) -> list[WeightItem]:
    return [
        WeightItem(key=link.offer_id, active=link.is_active, pinned=link.pinned, share=link.share)
        for link in stream.offers
    ]


def is_dirty(stream: Stream) -> bool:
    return any(link.is_dirty for link in stream.offers)


def stream_issues(stream: Stream) -> list[WeightIssue]:
    """Проблемы текущих долей. Пустой список — поток можно публиковать."""
    if not stream.offers:
        return []  # поток без офферов (редирект и т.п.) обёртка не разбирает
    items = weight_items(stream)
    if not validate(items):
        return []
    specific = rebalance(items).issues
    return specific or [WeightIssue.SUM_NOT_100]


def apply_rebalance(stream: Stream) -> None:
    result = rebalance(weight_items(stream))
    by_offer: dict[int, StreamOffer] = {link.offer_id: link for link in stream.offers}
    for offer_id, share in result.shares.items():
        by_offer[offer_id].share = share  # type: ignore[index]
