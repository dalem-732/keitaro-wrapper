import pytest

from app.services.weights import WeightIssue, WeightItem, rebalance, split_evenly, validate


def items(*specs: tuple[str, bool, bool, int]) -> list[WeightItem]:
    return [WeightItem(key=k, active=a, pinned=p, share=s) for k, a, p, s in specs]


def active(*keys: str) -> list[WeightItem]:
    return [WeightItem(key=k, active=True) for k in keys]


@pytest.mark.parametrize(
    ("total", "count", "expected"),
    [
        (100, 1, [100]),
        (100, 3, [34, 33, 33]),
        (75, 2, [38, 37]),
        (100, 4, [25] * 4),
        (100, 5, [20] * 5),
        (100, 6, [17, 17, 17, 17, 16, 16]),
        (100, 7, [15, 15, 14, 14, 14, 14, 14]),
    ],
)
def test_split_evenly(total: int, count: int, expected: list[int]) -> None:
    assert split_evenly(total, count) == expected
    assert sum(split_evenly(total, count)) == total


def test_video_add_fourth_offer_gives_25_each() -> None:
    result = rebalance(active("a", "b", "c", "d"))
    assert result.ok and list(result.shares.values()) == [25, 25, 25, 25]


def test_video_five_offers_gives_20_each() -> None:
    assert list(rebalance(active(*"abcde")).shares.values()) == [20] * 5


def test_video_remove_one_of_four_gives_34_33_33_and_zero_for_removed() -> None:
    result = rebalance(
        items(
            ("a", True, False, 25),
            ("b", False, False, 25),
            ("c", True, False, 25),
            ("d", True, False, 25),
        )
    )
    assert result.shares == {"a": 34, "b": 0, "c": 33, "d": 33}


def test_video_pinned_25_and_two_free_gives_38_37() -> None:
    result = rebalance(
        items(
            ("miaflow9", True, False, 0),
            ("oxys", True, False, 25),
            ("miaflow8", True, True, 25),
            ("fito", False, False, 0),
        )
    )
    assert result.ok
    assert result.shares == {"miaflow9": 38, "oxys": 37, "miaflow8": 25, "fito": 0}


def test_single_offer_gets_100() -> None:
    assert rebalance(active("a")).shares == {"a": 100}


def test_archived_always_zero_and_sum_of_active_is_100() -> None:
    result = rebalance(
        items(("a", True, False, 10), ("b", False, False, 90), ("c", True, True, 33))
    )
    assert result.shares["b"] == 0
    assert sum(v for k, v in result.shares.items() if k != "b") == 100


def test_all_pinned_summing_to_100_is_ok() -> None:
    result = rebalance(items(("a", True, True, 60), ("b", True, True, 40)))
    assert result.ok and result.shares == {"a": 60, "b": 40}


def test_all_pinned_not_100_is_an_issue() -> None:
    result = rebalance(items(("a", True, True, 60), ("b", True, True, 30)))
    assert result.issues == [WeightIssue.ALL_PINNED_NOT_100]


def test_single_pinned_offer_not_100_is_an_issue() -> None:
    assert rebalance(items(("a", True, True, 40))).issues == [WeightIssue.ALL_PINNED_NOT_100]


def test_pinned_over_100_is_an_issue() -> None:
    result = rebalance(items(("a", True, True, 70), ("b", True, True, 50), ("c", True, False, 0)))
    assert result.issues == [WeightIssue.PINNED_OVER_100]


def test_not_enough_rest_for_unpinned_is_an_issue() -> None:
    result = rebalance(items(("a", True, True, 99), ("b", True, False, 0), ("c", True, False, 0)))
    assert result.issues == [WeightIssue.NOT_ENOUGH_FOR_UNPINNED]


def test_pinned_100_with_free_offer_is_an_issue_not_silent_zero() -> None:
    result = rebalance(items(("a", True, True, 100), ("b", True, False, 0)))
    assert result.issues == [WeightIssue.NOT_ENOUGH_FOR_UNPINNED]


def test_no_active_offers_is_an_issue() -> None:
    assert rebalance(items(("a", False, False, 0))).issues == [WeightIssue.NO_ACTIVE_OFFERS]
    assert rebalance([]).issues == [WeightIssue.NO_ACTIVE_OFFERS]


def test_order_decides_who_gets_the_remainder() -> None:
    assert list(rebalance(active("x", "y", "z")).shares.values()) == [34, 33, 33]


@pytest.mark.parametrize("count", range(1, 30))
def test_any_number_of_free_offers_sums_to_100(count: int) -> None:
    shares = rebalance(active(*[str(i) for i in range(count)])).shares.values()
    assert sum(shares) == 100
    assert max(shares) - min(shares) <= 1


def test_validate_detects_keitaro_sum_after_manual_delete() -> None:
    # В Keitaro удалили 2 из 4 офферов по 25% — осталось 25 + 25 = 50%.
    assert validate(items(("a", True, False, 25), ("b", True, False, 25))) == [
        WeightIssue.SUM_NOT_100
    ]
    assert validate(items(("a", True, False, 50), ("b", True, False, 50))) == []
