"""Асинхронный клиент Keitaro Admin API v1.

* Таймауты на каждый запрос.
* Повторы с экспоненциальной паузой только для идемпотентных методов (GET/PUT/DELETE)
  и только при сетевых сбоях, 429 и 5xx. POST не повторяется, чтобы не создать дубль.
* Ошибки Keitaro превращаются в типизированные исключения.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter

from app.keitaro.errors import (
    KeitaroAuthError,
    KeitaroError,
    KeitaroNotFoundError,
    KeitaroUnavailableError,
    KeitaroValidationError,
)
from app.keitaro.schemas import (
    KtCampaign,
    KtDomain,
    KtGroup,
    KtOffer,
    KtStream,
    KtTrafficSource,
    StreamOfferPayload,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

IDEMPOTENT_METHODS = frozenset({"GET", "PUT", "DELETE"})
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_retries = max(0, max_retries)
        self._backoff = backoff
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> KeitaroClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ transport

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        method = method.upper()
        attempts = 1 + (self._max_retries if method in IDEMPOTENT_METHODS else 0)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self._http.request(method, path.lstrip("/"), **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning("Keitaro %s %s failed (%s), attempt %s", method, path, exc, attempt)
            else:
                if response.status_code in RETRY_STATUSES and attempt < attempts:
                    logger.warning(
                        "Keitaro %s %s -> %s, retrying", method, path, response.status_code
                    )
                    last_error = KeitaroUnavailableError(
                        f"Keitaro вернул {response.status_code}: {_error_text(response)}",
                        status_code=response.status_code,
                    )
                else:
                    return self._handle(response)
            if attempt < attempts:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        if isinstance(last_error, KeitaroError):
            raise last_error
        raise KeitaroUnavailableError(f"Keitaro недоступен: {last_error!s}") from last_error

    @staticmethod
    def _handle(response: httpx.Response) -> Any:
        status = response.status_code
        if status < 400:
            if not response.content:
                return None
            return response.json()
        text = _error_text(response)
        if status in (401, 403):
            raise KeitaroAuthError(f"Keitaro отклонил ключ API: {text}", status_code=status)
        if status == 404:
            raise KeitaroNotFoundError(text, status_code=status)
        if status in (400, 406, 409, 422):
            raise KeitaroValidationError(text, status_code=status)
        raise KeitaroUnavailableError(f"Keitaro вернул {status}: {text}", status_code=status)

    async def _get_list(self, path: str, model: type[T], **params: Any) -> list[T]:
        data = await self._request("GET", path, params=params or None)
        return TypeAdapter(list[model]).validate_python(data or [])  # type: ignore[valid-type]

    async def _get_one(self, path: str, model: type[T]) -> T:
        return model.model_validate(await self._request("GET", path))

    # ------------------------------------------------------------------ campaigns

    async def list_campaigns(self, *, offset: int = 0, limit: int = 100) -> list[KtCampaign]:
        return await self._get_list("campaigns", KtCampaign, offset=offset, limit=limit)

    async def get_campaign(self, campaign_id: int) -> KtCampaign:
        return await self._get_one(f"campaigns/{campaign_id}", KtCampaign)

    async def create_campaign(self, payload: dict[str, Any]) -> KtCampaign:
        return KtCampaign.model_validate(await self._request("POST", "campaigns", json=payload))

    async def update_campaign(self, campaign_id: int, payload: dict[str, Any]) -> KtCampaign:
        data = await self._request("PUT", f"campaigns/{campaign_id}", json=payload)
        return KtCampaign.model_validate(data)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"campaigns/{campaign_id}")

    # ------------------------------------------------------------------ streams

    async def list_streams(self, campaign_id: int) -> list[KtStream]:
        streams = await self._get_list(f"campaigns/{campaign_id}/streams", KtStream)
        return sorted(streams, key=lambda s: (s.position, s.id))

    async def get_stream(self, stream_id: int) -> KtStream:
        return await self._get_one(f"streams/{stream_id}", KtStream)

    async def create_stream(self, payload: dict[str, Any]) -> KtStream:
        return KtStream.model_validate(await self._request("POST", "streams", json=payload))

    async def replace_stream_offers(
        self, stream_id: int, offers: Sequence[StreamOfferPayload]
    ) -> KtStream:
        """PUT /streams/{id} с полем offers: Keitaro заменяет весь состав офферов потока."""
        body = {"offers": [o.model_dump() for o in offers]}
        return KtStream.model_validate(
            await self._request("PUT", f"streams/{stream_id}", json=body)
        )

    async def delete_stream(self, stream_id: int) -> None:
        await self._request("DELETE", f"streams/{stream_id}")

    # ------------------------------------------------------------------ dictionaries

    async def list_offers(self) -> list[KtOffer]:
        return await self._get_list("offers", KtOffer)

    async def get_offer(self, offer_id: int) -> KtOffer:
        return await self._get_one(f"offers/{offer_id}", KtOffer)

    async def list_domains(self) -> list[KtDomain]:
        return await self._get_list("domains", KtDomain)

    async def list_groups(self) -> list[KtGroup]:
        return await self._get_list("groups", KtGroup, type="campaigns")

    async def list_traffic_sources(self) -> list[KtTrafficSource]:
        return await self._get_list("traffic_sources", KtTrafficSource)


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(data, dict):
        for key in ("error", "message", "errors"):
            if key in data:
                return str(data[key])
    return str(data)[:300]
