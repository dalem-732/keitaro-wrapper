"""Сценарий из видео целиком: FETCH → ADD → PUSH → CANCEL → REMOVE → BRING BACK →
удаление в Keitaro → FETCH → PIN → PUSH. «Keitaro» — stateful-подделка в памяти."""

from typing import Any

import httpx

from tests.fake_keitaro import FakeKeitaro


async def import_campaign(api: httpx.AsyncClient, kt_id: int) -> dict[str, Any]:
    r = await api.post("/api/campaigns/import", json={"kt_id": kt_id})
    assert r.status_code == 200, r.text
    return r.json()


def offers_stream(campaign: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in campaign["streams"] if s["name"] == "Flow 2")


def shares(stream: dict[str, Any]) -> dict[int, int]:
    return {o["offer_id"]: o["share"] for o in stream["offers"]}


def link_id(stream: dict[str, Any], offer_id: int) -> int:
    return next(o["id"] for o in stream["offers"] if o["offer_id"] == offer_id)


def badge(stream: dict[str, Any], offer_id: int) -> str:
    return next(o["badge"] for o in stream["offers"] if o["offer_id"] == offer_id)


async def ok(r: httpx.Response) -> dict[str, Any]:
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_video_scenario(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, s2 = fake.seed_video_campaign()

    # 1. FETCH: два потока, Flow 1 без офферов (не разбирается), Flow 2 — 33/33/34.
    campaign = await import_campaign(api, cid)
    assert [s["name"] for s in campaign["streams"]] == ["Flow 1", "Flow 2"]
    flow1 = campaign["streams"][0]
    assert flow1["offers"] == [] and flow1["accepts_offers"] is False and flow1["issues"] == []
    stream = offers_stream(campaign)
    sid = stream["id"]
    assert shares(stream) == {3749: 33, 3717: 33, 11111: 34}
    assert stream["is_dirty"] is False

    # 2. ADD 11112 → 4 × 25%, поток «жёлтый», Keitaro не тронут.
    stream = await ok(await api.post(f"/api/streams/{sid}/offers", json={"offer_id": 11112}))
    assert shares(stream) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}
    assert stream["is_dirty"] is True and badge(stream, 11112) == "new"
    assert fake.stream_offers(s2) == {3749: 33, 3717: 33, 11111: 34}

    # 3. PUSH TO KT → в Keitaro 4 × 25%, поток снова белый.
    pushed = await ok(await api.post(f"/api/streams/{sid}/push"))
    assert pushed["result"]["changed"] is True and pushed["stream"]["is_dirty"] is False
    assert fake.stream_offers(s2) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}

    # 4. ADD 11105 → 5 × 20%, затем CANCEL → привязка исчезла, снова 4 × 25%.
    stream = await ok(await api.post(f"/api/streams/{sid}/offers", json={"offer_id": 11105}))
    assert set(shares(stream).values()) == {20}
    stream = await ok(await api.post(f"/api/streams/{sid}/cancel"))
    assert shares(stream) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}
    assert stream["is_dirty"] is False
    assert fake.calls[f"PUT streams/{s2}"] == 1

    # 5. REMOVE 3717 → серый 0%, остальные 34/33/33.
    stream = await ok(await api.post(f"/api/streams/{sid}/offers/{link_id(stream, 3717)}/remove"))
    assert shares(stream) == {3749: 34, 3717: 0, 11111: 33, 11112: 33}
    assert badge(stream, 3717) == "removed_pending" and stream["is_dirty"]

    # 6. PUSH → оффер реально удалён из Keitaro (а не share=0), в обёртке — архив.
    await ok(await api.post(f"/api/streams/{sid}/push"))
    assert fake.stream_offers(s2) == {3749: 34, 11111: 33, 11112: 33}
    assert 3717 not in fake.stream_offers(s2)
    stream = await ok(await api.get(f"/api/streams/{sid}"))
    assert badge(stream, 3717) == "archived" and not stream["is_dirty"]

    # 7. BRING BACK → снова 4 × 25% после PUSH.
    stream = await ok(await api.post(f"/api/streams/{sid}/offers/{link_id(stream, 3717)}/restore"))
    assert badge(stream, 3717) == "restored_pending" and set(shares(stream).values()) == {25}
    await ok(await api.post(f"/api/streams/{sid}/push"))
    assert fake.stream_offers(s2) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}

    # 8. Удаляем 3749 и 11111 прямо в Keitaro (там остаётся 25 + 25 = 50%).
    fake.streams[s2]["offers"] = [
        o for o in fake.streams[s2]["offers"] if o["offer_id"] in (3717, 11112)
    ]
    campaign = await ok(await api.post(f"/api/campaigns/{campaign['id']}/fetch"))
    stream = offers_stream(campaign)
    assert badge(stream, 3749) == "archived" and badge(stream, 11111) == "archived"
    assert shares(stream) == {3717: 25, 11112: 25, 3749: 0, 11111: 0}
    # Сумма в Keitaro стала 50% — обёртка это подсвечивает, а не молчит.
    assert [i["code"] for i in stream["issues"]] == ["sum_not_100"]

    # 9. PIN 3717 на 25%, BRING BACK 3749 → 25 закреплено, остальные 38/37.
    stream = await ok(
        await api.patch(f"/api/streams/{sid}/offers/{link_id(stream, 3717)}", json={"pinned": True})
    )
    assert stream["is_dirty"] is False  # закрепление — локальная настройка
    stream = await ok(await api.post(f"/api/streams/{sid}/offers/{link_id(stream, 3749)}/restore"))
    got = shares(stream)
    assert got[3717] == 25 and sorted([got[3749], got[11112]]) == [37, 38] and got[11111] == 0
    assert stream["issues"] == []

    # 10. PUSH → в Keitaro те же доли, сумма 100.
    await ok(await api.post(f"/api/streams/{sid}/push"))
    in_kt = fake.stream_offers(s2)
    assert in_kt[3717] == 25 and sorted([in_kt[3749], in_kt[11112]]) == [37, 38]
    assert sum(in_kt.values()) == 100 and 11111 not in in_kt


async def test_rebalance_fixes_keitaro_sum(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, s2 = fake.seed_video_campaign()
    fake.streams[s2]["offers"] = fake.streams[s2]["offers"][:2]  # 33 + 33 = 66
    stream = offers_stream(await import_campaign(api, cid))
    assert stream["issues"][0]["code"] == "sum_not_100"
    stream = await ok(await api.post(f"/api/streams/{stream['id']}/rebalance"))
    assert shares(stream) == {3749: 50, 3717: 50} and stream["is_dirty"]
    await ok(await api.post(f"/api/streams/{stream['id']}/push"))
    assert fake.stream_offers(s2) == {3749: 50, 3717: 50}


async def test_push_blocked_when_weights_invalid(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, s2 = fake.seed_video_campaign()
    stream = offers_stream(await import_campaign(api, cid))
    sid = stream["id"]
    # Закрепляем 2 оффера на 60 и 40 → третьему не остаётся ничего.
    await ok(
        await api.patch(f"/api/streams/{sid}/offers/{link_id(stream, 3749)}", json={"share": 60})
    )
    stream = await ok(
        await api.patch(f"/api/streams/{sid}/offers/{link_id(stream, 3717)}", json={"share": 40})
    )
    assert [i["code"] for i in stream["issues"]] == ["not_enough_for_unpinned"]
    r = await api.post(f"/api/streams/{sid}/push")
    assert r.status_code == 422 and "1%" in r.json()["error"]["message"]
    assert fake.calls[f"PUT streams/{s2}"] == 0


async def test_manual_share_pins_and_rebalances(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, _ = fake.seed_video_campaign()
    stream = offers_stream(await import_campaign(api, cid))
    stream = await ok(
        await api.patch(
            f"/api/streams/{stream['id']}/offers/{link_id(stream, 11111)}", json={"share": 50}
        )
    )
    assert shares(stream) == {3749: 25, 3717: 25, 11111: 50}
    assert next(o for o in stream["offers"] if o["offer_id"] == 11111)["pinned"] is True


async def test_conflict_when_keitaro_changed_since_fetch(
    api: httpx.AsyncClient, fake: FakeKeitaro
) -> None:
    cid, _, s2 = fake.seed_video_campaign()
    stream = offers_stream(await import_campaign(api, cid))
    await ok(await api.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 11112}))
    fake.streams[s2]["offers"] = fake.streams[s2]["offers"][:1]  # кто-то правит Keitaro
    r = await api.post(f"/api/streams/{stream['id']}/push")
    assert r.status_code == 409
    assert fake.calls[f"PUT streams/{s2}"] == 0
    r = await api.post(f"/api/streams/{stream['id']}/push?force=true")
    assert r.status_code == 200
    assert sum(fake.stream_offers(s2).values()) == 100


async def test_push_is_idempotent(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, s2 = fake.seed_video_campaign()
    campaign = await import_campaign(api, cid)
    sid = offers_stream(campaign)["id"]
    await ok(await api.post(f"/api/streams/{sid}/offers", json={"offer_id": 11112}))
    r1 = await ok(await api.post(f"/api/campaigns/{campaign['id']}/push"))
    r2 = await ok(await api.post(f"/api/campaigns/{campaign['id']}/push"))
    assert [x["changed"] for x in r1["results"]] == [True]
    assert r2["results"] == []  # нечего публиковать — ни одного запроса на запись
    assert fake.calls[f"PUT streams/{s2}"] == 1


async def test_remove_new_offer_before_push_just_drops_it(
    api: httpx.AsyncClient, fake: FakeKeitaro
) -> None:
    cid, _, _ = fake.seed_video_campaign()
    stream = offers_stream(await import_campaign(api, cid))
    stream = await ok(
        await api.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 11112})
    )
    stream = await ok(
        await api.post(f"/api/streams/{stream['id']}/offers/{link_id(stream, 11112)}/remove")
    )
    assert 11112 not in shares(stream)
    assert shares(stream) == {3749: 34, 3717: 33, 11111: 33}  # пересчитано, но отличается от KT
    stream = await ok(await api.post(f"/api/streams/{stream['id']}/cancel"))
    assert shares(stream) == {3749: 33, 3717: 33, 11111: 34} and not stream["is_dirty"]


async def test_add_validation(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, _ = fake.seed_video_campaign()
    campaign = await import_campaign(api, cid)
    flow1, flow2 = campaign["streams"]
    r = await api.post(f"/api/streams/{flow2['id']}/offers", json={"offer_id": 3749})
    assert r.status_code == 409  # уже в потоке
    r = await api.post(f"/api/streams/{flow2['id']}/offers", json={"offer_id": 424242})
    assert r.status_code == 422  # нет в Keitaro
    r = await api.post(f"/api/streams/{flow1['id']}/offers", json={"offer_id": 11112})
    assert r.status_code == 422  # поток-редирект без офферов


async def test_write_guard_for_foreign_campaigns(api: httpx.AsyncClient, fake: FakeKeitaro) -> None:
    cid, _, s2 = fake.seed_video_campaign(name="campaign 2")
    campaign = await import_campaign(api, cid)
    assert campaign["writable"] is False
    stream = offers_stream(campaign)
    await ok(await api.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 11112}))
    r = await api.post(f"/api/streams/{stream['id']}/push")
    assert r.status_code == 403
    assert fake.calls[f"PUT streams/{s2}"] == 0


async def test_streams_deleted_in_keitaro_disappear_on_fetch(
    api: httpx.AsyncClient, fake: FakeKeitaro
) -> None:
    cid, s1, _ = fake.seed_video_campaign()
    campaign = await import_campaign(api, cid)
    assert campaign["last_fetched_at"].endswith(("Z", "+00:00"))  # время всегда с поясом
    del fake.streams[s1]
    campaign = await ok(await api.post(f"/api/campaigns/{campaign['id']}/fetch"))
    assert [s["name"] for s in campaign["streams"]] == ["Flow 2"]


async def test_offer_search(api: httpx.AsyncClient) -> None:
    found = (await api.get("/api/offers/search", params={"q": "1111"})).json()
    assert [o["id"] for o in found][:2] == [11111, 11112]
    assert (await api.get("/api/offers/search", params={"q": "oxys"})).json()[0]["id"] == 11112
