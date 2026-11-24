import re

from app.core.countries import COUNTRIES
from app.core.errors import ValidationFailed

_SEPARATORS = re.compile(r"[\s,;]+")
_HINTS = {"UK": "GB", "EN": "GB", "XX": None}


def parse_geo(raw: str | list[str]) -> list[str]:
    """«mx, AU;ro» → ["MX", "AU", "RO"]. Проверка по ISO 3166-1 alpha-2, без дублей."""
    parts = raw if isinstance(raw, list) else _SEPARATORS.split(raw)
    codes: list[str] = []
    for part in parts:
        code = part.strip().upper()
        if code and code not in codes:
            codes.append(code)
    if not codes:
        raise ValidationFailed("Укажите хотя бы один код страны, например AU или MX,AU,RO.")
    invalid = [c for c in codes if c not in COUNTRIES]
    if invalid:
        hints = [f"{c} → {_HINTS[c]}" for c in invalid if _HINTS.get(c)]
        message = "Неизвестные коды стран (нужен ISO 3166-1 alpha-2): " + ", ".join(invalid)
        if hints:
            message += ". Возможно, имелось в виду: " + ", ".join(hints)
        raise ValidationFailed(message, details={"invalid_codes": invalid})
    return codes
