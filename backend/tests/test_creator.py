from typing import Any

import httpx

from tests.fake_keitaro import FakeKeitaro


async def create(api: httpx.AsyncClient, **body: Any) -> httpx.Response:
    payload = {"name": "demo", "geo": "AU", "offer_ids": [3749]} | body
    return await api.post("/api/creator/campaigns", json=payload)


async def test_creates_campaign_with_two_streams(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    r = await create(api, geo="mx, AU,ro", offer_ids=[3749, 3717])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "test_lebedev_demo"
    kt = fake.campaigns[data["kt_id"]]
    assert (kt["domain_id"], kt["group_id"], kt["traffic_source_id"], kt["type"]) == (
        1813,
        10332,
        836,
        "position",
    )

    geo, offers = sorted(
        (s for s in fake.streams.values() if s["campaign_id"] == kt["id"]),
        key=lambda s: s["position"],
    )
    assert geo["type"] == "regular" and geo["schema"] == "redirect"
    assert geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU", "RO"]}]
    assert offers["type"] == "default" and offers["schema"] == "landings"
    assert [(o["offer_id"], o["share"]) for o in offers["offers"]] == [(3749, 50), (3717, 50)]

    # Кампания сразу доступна в редакторе.
    assert [s["position"] for s in data["streams"]] == [1, 2]
    assert data["streams"][1]["offers"][0]["offer_id"] == 3749


async def test_country_comes_from_user_input(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    r = await create(api, geo="DE")
    assert r.status_code == 201
    geo_payloads = [s["filters"][0]["payload"] for s in fake.streams.values() if s["filters"]]
    assert geo_payloads == [["DE"]]


async def test_invalid_geo_rejected_without_touching_keitaro(
    api: httpx.AsyncClient, fake: FakeKeitaro
) -> None:
    r = await create(api, geo="XX")
    assert r.status_code == 422 and "XX" in r.json()["error"]["message"]
    assert fake.calls["POST campaigns"] == 0


async def test_unknown_offer_rejected(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    r = await create(api, offer_ids=[999999])
    assert r.status_code == 422 and "999999" in r.json()["error"]["message"]
    assert fake.calls["POST campaigns"] == 0


async def test_duplicate_name_rejected(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    assert (await create(api)).status_code == 201
    r = await create(api, name="test_lebedev_demo")
    assert r.status_code == 409
    assert fake.calls["POST campaigns"] == 1


async def test_rollback_when_stream_creation_fails(
    api: httpx.AsyncClient, fake: FakeKeitaro
) -> None:
    fake.fail(
        "POST streams",
        httpx.Response(200, json={"id": 1, "name": "x", "campaign_id": 1}),
        httpx.Response(500, json={"error": "boom"}),
    )
    r = await create(api)
    assert r.status_code == 502
    assert fake.campaigns == {}  # полуготовая кампания удалена
    assert any(m == "DELETE" for m, _, _ in fake.log)


async def test_meta_defaults(api: httpx.AsyncClient) -> None:
    meta = (await api.get("/api/meta")).json()
    assert meta["defaults"] == {"domain_id": 1813, "group_id": 10332, "traffic_source_id": 836}
    assert meta["campaign_name_prefix"] == "test_lebedev_"
    assert meta["countries"]["AU"] == "Australia"


async def test_request_validation_message(api: httpx.AsyncClient) -> None:
    r = await api.post("/api/creator/campaigns", json={"name": "x", "geo": "AU", "offer_ids": []})
    assert r.status_code == 422 and r.json()["error"]["code"] == "request_validation"
