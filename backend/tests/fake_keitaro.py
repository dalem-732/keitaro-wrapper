"""Stateful-подделка Keitaro Admin API v1 (повторяет поведение учебного эмулятора).

Используется как httpx.MockTransport: тесты гоняют настоящий KeitaroClient и всё
приложение, а «Keitaro» живёт в памяти. Можно портить ответы, чтобы проверить ошибки.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from typing import Any

import httpx

API_KEY = "test-key"
BASE_URL = "https://kt.test/admin_api/v1"


class FakeKeitaro:
    def __init__(self) -> None:
        self.ids = itertools.count(1000)
        self.offers = {
            oid: {"id": oid, "name": name, "state": "active", "country": []}
            for oid, name in [
                (3749, "Miaflow [BEAUTY-RO-BE_0009] [pl - spin ro -]"),
                (3717, "Miaflow [BEAUTY-RO-BE_0008] [pl - prize ro -]"),
                (11111, "11111 FitoMishki [Weight Loss-CO-DT_0309] [pl es -]"),
                (11112, "11112 Oxys [BEAUTY-CL-BE_0155] [pl es-]"),
                (11105, "11105 Alividerma crema [JOINT-DO-JO_0646] [land es-]"),
            ]
        }
        self.domains = [{"id": 1813, "name": "kt-emulator.test"}]
        self.groups = [{"id": 10332, "name": "FORTESTS", "type": "campaigns"}]
        self.sources = [{"id": 836, "name": "FORTESTS"}]
        self.campaigns: dict[int, dict[str, Any]] = {}
        self.streams: dict[int, dict[str, Any]] = {}
        self.calls: Counter[str] = Counter()
        self.log: list[tuple[str, str, Any]] = []
        self.fail_next: dict[str, list[httpx.Response]] = {}

    # ------------------------------------------------------------------ helpers for tests

    def seed_video_campaign(self, name: str = "test_lebedev_campaign 2") -> tuple[int, int, int]:
        """Кампания из видео: Flow 1 (AU → google), Flow 2 (3 оффера 33/33/34)."""
        cid = self._create_campaign(
            {
                "name": name,
                "domain_id": 1813,
                "group_id": 10332,
                "traffic_source_id": 836,
                "type": "position",
            }
        )["id"]
        s1 = self._create_stream(
            {
                "campaign_id": cid,
                "name": "Flow 1",
                "type": "regular",
                "schema": "redirect",
                "action_payload": "https://google.com",
                "position": 1,
                "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}],
            }
        )
        s2 = self._create_stream(
            {
                "campaign_id": cid,
                "name": "Flow 2",
                "type": "default",
                "schema": "landings",
                "position": 2,
                "offers": [
                    {"offer_id": 3749, "share": 33, "state": "active"},
                    {"offer_id": 3717, "share": 33, "state": "active"},
                    {"offer_id": 11111, "share": 34, "state": "active"},
                ],
            }
        )
        return cid, s1["id"], s2["id"]

    def stream_offers(self, stream_id: int) -> dict[int, int]:
        return {o["offer_id"]: o["share"] for o in self.streams[stream_id]["offers"]}

    def fail(self, key: str, *responses: httpx.Response) -> None:
        """Следующие запросы key ('PUT streams/5') получат эти ответы."""
        self.fail_next.setdefault(key, []).extend(responses)

    # ------------------------------------------------------------------ state

    def _create_campaign(self, body: dict[str, Any]) -> dict[str, Any]:
        cid = next(self.ids)
        domain = next((d for d in self.domains if d["id"] == body.get("domain_id")), None)
        group = next((g for g in self.groups if g["id"] == body.get("group_id")), None)
        campaign = {
            "id": cid,
            "alias": f"a{cid}",
            "name": body["name"],
            "type": body.get("type", "position"),
            "state": body.get("state", "active"),
            "domain_id": body.get("domain_id"),
            "group_id": body.get("group_id"),
            "traffic_source_id": body.get("traffic_source_id"),
            "domain": f"https://{domain['name']}/" if domain else None,
            "group": group["name"] if group else None,
        }
        self.campaigns[cid] = campaign
        return campaign

    def _create_stream(self, body: dict[str, Any]) -> dict[str, Any]:
        sid = next(self.ids)
        stream = {
            "id": sid,
            "campaign_id": body["campaign_id"],
            "name": body["name"],
            "position": body.get("position", len(self.streams) + 1),
            "type": body.get("type", "regular"),
            "schema": body.get("schema", "redirect"),
            "action_type": body.get("action_type", "http"),
            "action_payload": body.get("action_payload"),
            "state": body.get("state", "active"),
            "filters": [dict(f) for f in body.get("filters", [])],
            "offers": [dict(o, stream_id=sid) for o in body.get("offers", [])],
        }
        self.streams[sid] = stream
        return stream

    # ------------------------------------------------------------------ transport

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/admin_api/v1/", 1)[1].strip("/")
        key = f"{request.method} {path}"
        self.calls[key] += 1
        body = json.loads(request.content) if request.content else None
        self.log.append((request.method, path, body))
        if self.fail_next.get(key):
            return self.fail_next[key].pop(0)
        if request.headers.get("Api-Key") != API_KEY:
            return httpx.Response(401, json={"error": "Unauthorized"})
        return self.route(request.method, path.split("/"), body, request)

    def route(
        self, method: str, parts: list[str], body: Any, request: httpx.Request
    ) -> httpx.Response:
        ok = lambda data: httpx.Response(200, json=data)  # noqa: E731
        nf = lambda what: httpx.Response(404, json={"error": f"{what} not found"})  # noqa: E731
        head = parts[0]
        if head == "offers":
            if len(parts) == 1:
                return ok(list(self.offers.values()))
            offer = self.offers.get(int(parts[1]))
            return ok(offer) if offer else nf("Offer")
        if head == "domains":
            return ok(self.domains)
        if head == "groups":
            return ok(self.groups)
        if head == "traffic_sources":
            return ok(self.sources)
        if head == "campaigns":
            if len(parts) == 1:
                if method == "GET":
                    return ok(sorted(self.campaigns.values(), key=lambda c: -c["id"]))
                if not (body or {}).get("name"):
                    return httpx.Response(406, json={"error": "name is required"})
                return ok(self._create_campaign(body))
            cid = int(parts[1])
            campaign = self.campaigns.get(cid)
            if campaign is None:
                return nf("Campaign")
            if len(parts) == 3 and parts[2] == "streams":
                streams = [s for s in self.streams.values() if s["campaign_id"] == cid]
                return ok(sorted(streams, key=lambda s: s["position"]))
            if method == "DELETE":
                del self.campaigns[cid]
                for sid in [s["id"] for s in self.streams.values() if s["campaign_id"] == cid]:
                    del self.streams[sid]
                return ok(dict(campaign, state="deleted"))
            if method == "PUT":
                campaign.update(body or {})
            return ok(campaign)
        if head == "streams":
            if len(parts) == 1:
                if not (body or {}).get("campaign_id") or not body.get("name"):
                    return httpx.Response(406, json={"error": "campaign_id and name are required"})
                if body["campaign_id"] not in self.campaigns:
                    return nf("Campaign")
                for offer in body.get("offers", []):
                    if offer["offer_id"] not in self.offers:
                        return httpx.Response(
                            406, json={"error": f"offers: offer {offer['offer_id']} does not exist"}
                        )
                return ok(self._create_stream(body))
            sid = int(parts[1])
            stream = self.streams.get(sid)
            if stream is None:
                return nf("Stream")
            if method == "DELETE":
                del self.streams[sid]
                return ok(stream)
            if method == "PUT":
                body = body or {}
                if "offers" in body:
                    for offer in body["offers"]:
                        if offer["offer_id"] not in self.offers:
                            return httpx.Response(
                                406,
                                json={"error": f"offers: offer {offer['offer_id']} does not exist"},
                            )
                    stream["offers"] = [dict(o, stream_id=sid) for o in body["offers"]]
                for field in ("name", "position", "filters", "action_payload", "state"):
                    if field in body:
                        stream[field] = body[field]
            return ok(stream)
        return nf("Route")
