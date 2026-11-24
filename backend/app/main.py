"""Точка входа FastAPI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import campaigns, meta, streams
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import create_engine, create_sessionmaker
from app.keitaro import (
    KeitaroAuthError,
    KeitaroClient,
    KeitaroError,
    KeitaroNotFoundError,
    KeitaroValidationError,
)
from app.services.offer_catalog import OfferCatalog

logger = logging.getLogger("app")


def _error(status: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details  # type: ignore[index]
    return JSONResponse(status_code=status, content=body)


def create_app(
    settings: Settings | None = None, *, keitaro_client: KeitaroClient | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        client = keitaro_client or KeitaroClient(
            settings.api_base_url,
            settings.keitaro_api_key.get_secret_value(),
            timeout=settings.keitaro_timeout_seconds,
            max_retries=settings.keitaro_max_retries,
            backoff=settings.keitaro_retry_backoff_seconds,
        )
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.keitaro = client
        app.state.catalog = OfferCatalog(client, settings.offers_cache_ttl_seconds)
        if not settings.keitaro_api_key.get_secret_value():
            logger.warning("KEITARO_API_KEY не задан — запросы к Keitaro будут отклонены")
        try:
            yield
        finally:
            await client.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Keitaro Wrapper",
        version="1.0.0",
        description="Создаватор кампаний и редактор офферов в потоках Keitaro.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(KeitaroError)
    async def _kt_error(_: Request, exc: KeitaroError) -> JSONResponse:
        if isinstance(exc, KeitaroAuthError):
            return _error(
                502, "keitaro_auth", "Keitaro не принял API-ключ. Проверьте KEITARO_API_KEY."
            )
        if isinstance(exc, KeitaroNotFoundError):
            return _error(404, "keitaro_not_found", f"Не найдено в Keitaro: {exc.message}")
        if isinstance(exc, KeitaroValidationError):
            return _error(422, "keitaro_validation", f"Keitaro отклонил данные: {exc.message}")
        return _error(502, "keitaro_unavailable", f"Keitaro недоступен: {exc.message}")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'неверные данные')}" if where else "Неверные данные"
        return _error(422, "request_validation", message, details=jsonable(exc.errors()))

    for router in (meta.router, campaigns.router, streams.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def jsonable(errors: object) -> object:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(errors)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
