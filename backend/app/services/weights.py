"""Алгоритм распределения долей (весов) офферов в потоке.

Чистая функция без I/O, покрывается юнит-тестами.

Правила (повторяют поведение из видео и закрывают крайние случаи):

1. Архивные (removed) офферы всегда получают 0% и в Keitaro не отправляются.
2. Закреплённые (pinned) активные офферы сохраняют свою долю как есть.
3. Остаток R = 100 − сумма закреплённых делится поровну между незакреплёнными
   активными офферами. Доли — целые числа; остаток от деления раздаётся по 1%
   первым в порядке отображения (метод наибольшего остатка при равных весах):
   3 оффера → 34/33/33, закреплён 25% + 2 оффера → 38/37 — ровно как в видео.
4. Сумма активных долей всегда 100%, иначе поток помечается проблемой и
   публикация блокируется (в Keitaro никогда не уходит сумма ≠ 100):
   * сумма закреплённых > 100%;
   * все активные закреплены, а сумма ≠ 100%;
   * остатка не хватает, чтобы дать каждому незакреплённому хотя бы 1%
     (оффер с долей 0% в активном потоке — это скрытое отключение, а не распределение);
   * в потоке нет ни одного активного оффера.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

TOTAL = 100


class WeightIssue(StrEnum):
    NO_ACTIVE_OFFERS = "no_active_offers"
    PINNED_OVER_100 = "pinned_over_100"
    ALL_PINNED_NOT_100 = "all_pinned_not_100"
    NOT_ENOUGH_FOR_UNPINNED = "not_enough_for_unpinned"
    SUM_NOT_100 = "sum_not_100"


ISSUE_MESSAGES: dict[WeightIssue, str] = {
    WeightIssue.NO_ACTIVE_OFFERS: "В потоке нет активных офферов — публиковать нечего.",
    WeightIssue.PINNED_OVER_100: (
        "Сумма закреплённых долей больше 100%. Открепите или уменьшите доли."
    ),
    WeightIssue.ALL_PINNED_NOT_100: (
        "Все активные офферы закреплены, но их сумма не равна 100%. "
        "Открепите хотя бы один оффер или поправьте доли."
    ),
    WeightIssue.NOT_ENOUGH_FOR_UNPINNED: (
        "После закреплённых долей не хватает хотя бы 1% на каждый незакреплённый оффер."
    ),
    WeightIssue.SUM_NOT_100: "Сумма активных долей не равна 100%. Нажмите «Выровнять».",
}


@dataclass(frozen=True, slots=True)
class WeightItem:
    key: Hashable
    active: bool
    pinned: bool = False
    share: int = 0  # текущая доля; для закреплённых — фиксированное значение


@dataclass(slots=True)
class WeightResult:
    shares: dict[Hashable, int]
    issues: list[WeightIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def split_evenly(total: int, count: int) -> list[int]:
    """Делит целое total на count целых частей, остаток — первым по порядку."""
    if count <= 0:
        return []
    base, remainder = divmod(total, count)
    return [base + (1 if i < remainder else 0) for i in range(count)]


def rebalance(items: Sequence[WeightItem]) -> WeightResult:
    shares: dict[Hashable, int] = {item.key: 0 for item in items}
    active = [i for i in items if i.active]
    if not active:
        return WeightResult(shares, [WeightIssue.NO_ACTIVE_OFFERS])

    pinned = [i for i in active if i.pinned]
    free = [i for i in active if not i.pinned]
    pinned_sum = sum(max(0, i.share) for i in pinned)
    for item in pinned:
        shares[item.key] = max(0, item.share)

    issues: list[WeightIssue] = []
    if pinned_sum > TOTAL:
        issues.append(WeightIssue.PINNED_OVER_100)
    elif not free:
        if pinned_sum != TOTAL:
            issues.append(WeightIssue.ALL_PINNED_NOT_100)
    else:
        rest = TOTAL - pinned_sum
        if rest < len(free):
            issues.append(WeightIssue.NOT_ENOUGH_FOR_UNPINNED)
        for item, value in zip(free, split_evenly(rest, len(free)), strict=True):
            shares[item.key] = value
    return WeightResult(shares, issues)


def validate(items: Sequence[WeightItem]) -> list[WeightIssue]:
    """Проверка уже рассчитанных долей (например, пришедших из Keitaro) без пересчёта."""
    active = [i for i in items if i.active]
    if not active:
        return [WeightIssue.NO_ACTIVE_OFFERS]
    if sum(i.share for i in active) != TOTAL:
        return [WeightIssue.SUM_NOT_100]
    if any(i.share <= 0 for i in active):
        return [WeightIssue.NOT_ENOUGH_FOR_UNPINNED]
    return []
