class KeitaroError(Exception):
    """Базовая ошибка общения с Keitaro Admin API."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class KeitaroAuthError(KeitaroError):
    """401/403 — неверный или отозванный Api-Key."""


class KeitaroNotFoundError(KeitaroError):
    """404 — сущность не найдена."""


class KeitaroValidationError(KeitaroError):
    """400/406/422 — Keitaro отклонил данные (например, несуществующий оффер)."""


class KeitaroUnavailableError(KeitaroError):
    """Таймаут, сетевой сбой или 5xx после всех повторов."""
