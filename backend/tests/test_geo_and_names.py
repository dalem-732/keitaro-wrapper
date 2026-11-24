import pytest

from app.core.errors import ValidationFailed
from app.services.creator_service import normalize_name
from app.services.geo import parse_geo


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AU", ["AU"]),
        ("mx, au;RO", ["MX", "AU", "RO"]),
        ("MX,AU,RO,", ["MX", "AU", "RO"]),
        (" au  au ", ["AU"]),
        (["de", "FR"], ["DE", "FR"]),
    ],
)
def test_parse_geo(raw: str | list[str], expected: list[str]) -> None:
    assert parse_geo(raw) == expected


@pytest.mark.parametrize("raw", ["XX", "AUS", "UK", "", " , ", "MX,ZZ"])
def test_parse_geo_rejects_non_iso(raw: str) -> None:
    with pytest.raises(ValidationFailed):
        parse_geo(raw)


def test_uk_gets_hint() -> None:
    with pytest.raises(ValidationFailed, match="GB"):
        parse_geo("UK")


def test_name_prefix_added_once() -> None:
    assert normalize_name("demo", "test_lebedev_") == "test_lebedev_demo"
    assert normalize_name("test_lebedev_demo", "test_lebedev_") == "test_lebedev_demo"
    assert normalize_name("  my   campaign ", "test_lebedev_") == "test_lebedev_my campaign"


@pytest.mark.parametrize("raw", ["", "   ", "test_lebedev_"])
def test_empty_name_rejected(raw: str) -> None:
    with pytest.raises(ValidationFailed):
        normalize_name(raw, "test_lebedev_")
