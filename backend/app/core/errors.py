"""Доменные ошибки. API-слой превращает их в HTTP-ответы с понятным текстом."""


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class WriteForbiddenError(AppError):
    status_code = 403
    code = "write_forbidden"


class UpstreamError(AppError):
    """Keitaro ответил ошибкой или недоступен."""

    status_code = 502
    code = "keitaro_error"
