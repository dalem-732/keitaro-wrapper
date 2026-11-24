import httpx
import pytest
import respx

from app.keitaro import (
    KeitaroAuthError,
    KeitaroClient,
    KeitaroNotFoundError,
    KeitaroUnavailableError,
    KeitaroValidationError,
)
from app.keitaro.schemas import StreamOfferPayload

BASE = "https://kt.example/admin_api/v1"


@pytest.fixture
def client() -> KeitaroClient:
    return KeitaroClient(BASE, "secret", max_retries=2, backoff=0)


@respx.mock
async def test_sends_api_key_header(client: KeitaroClient) -> None:
    route = respx.get(f"{BASE}/campaigns").respond(json=[])
    await client.list_campaigns()
    assert route.calls.last.request.headers["Api-Key"] == "secret"
    assert route.calls.last.request.url.params["limit"] == "100"


@respx.mock
async def test_get_is_retried_on_502_then_succeeds(client: KeitaroClient) -> None:
    route = respx.get(f"{BASE}/offers").mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json=[{"id": 1, "name": "x"}])]
    )
    offers = await client.list_offers()
    assert [o.id for o in offers] == [1] and route.call_count == 2


@respx.mock
async def test_get_is_retried_on_timeout_and_gives_up(client: KeitaroClient) -> None:
    route = respx.get(f"{BASE}/domains").mock(side_effect=httpx.ConnectTimeout("boom"))
    with pytest.raises(KeitaroUnavailableError):
        await client.list_domains()
    assert route.call_count == 3  # 1 + 2 повтора


@respx.mock
async def test_post_is_never_retried(client: KeitaroClient) -> None:
    route = respx.post(f"{BASE}/campaigns").respond(503)
    with pytest.raises(KeitaroUnavailableError):
        await client.create_campaign({"name": "x"})
    assert route.call_count == 1


@respx.mock
async def test_put_is_retried(client: KeitaroClient) -> None:
    route = respx.put(f"{BASE}/streams/5").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"id": 5, "name": "s", "campaign_id": 1, "offers": []}),
        ]
    )
    await client.replace_stream_offers(5, [StreamOfferPayload(offer_id=1, share=100)])
    assert route.call_count == 2
    assert (
        route.calls.last.request.content
        == b'{"offers":[{"offer_id":1,"share":100,"state":"active"}]}'
    )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, KeitaroAuthError),
        (404, KeitaroNotFoundError),
        (406, KeitaroValidationError),
        (422, KeitaroValidationError),
    ],
)
@respx.mock
async def test_error_mapping(client: KeitaroClient, status: int, error: type[Exception]) -> None:
    respx.get(f"{BASE}/offers/9").respond(status, json={"error": "Offer not found"})
    with pytest.raises(error, match="Offer not found" if status != 401 else "ключ"):
        await client.get_offer(9)


@respx.mock
async def test_streams_are_sorted_by_position(client: KeitaroClient) -> None:
    respx.get(f"{BASE}/campaigns/1/streams").respond(
        json=[
            {"id": 2, "name": "b", "campaign_id": 1, "position": 2, "schema": "landings"},
            {"id": 1, "name": "a", "campaign_id": 1, "position": 1},
        ]
    )
    streams = await client.list_streams(1)
    assert [s.id for s in streams] == [1, 2]
    assert streams[1].schema_ == "landings"
