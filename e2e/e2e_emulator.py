"""E2E: сценарий из видео через UI обёртки против учебного эмулятора Keitaro.

Запуск (приложение уже работает на :8000, в .env ключ эмулятора):
    uv run --with playwright --with httpx python e2e/e2e_emulator.py demo
    (один раз: uv run --with playwright playwright install chromium)

Скрипт создаёт кампанию test_lebedev_<имя> через создаватор, проходит все шаги из видео
(ADD, PUSH, CANCEL, REMOVE, BRING BACK, удаление прямо в Keitaro + FETCH, PIN) и после
каждого шага сверяет состояние в Keitaro через GET. Скриншоты — в e2e/shots/.
"""
import json, os, re, sys
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
env = dict(l.strip().split("=", 1) for l in open(ROOT / ".env") if "=" in l and not l.startswith("#"))
KT = httpx.Client(base_url=env["KEITARO_API_URL"] + "/", headers={"Api-Key": env["KEITARO_API_KEY"]}, timeout=20)
SHOTS = os.getenv("E2E_SHOTS", str(ROOT / "e2e" / "shots"))
os.makedirs(SHOTS, exist_ok=True)
BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
NAME = sys.argv[1] if len(sys.argv) > 1 else "demo"
log = []

def kt_offers(stream_id):
    s = KT.get(f"streams/{stream_id}").json()
    return {o["offer_id"]: o["share"] for o in s["offers"]}

def step(msg):
    print("•", msg, flush=True); log.append(msg)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    n = [0]
    def shot(name, full=True):
        n[0] += 1
        page.wait_for_timeout(350)
        page.screenshot(path=f"{SHOTS}/{n[0]:02d}-{name}.png", full_page=full)

    try:
        # ---------- Part 1: creator
        page.goto(BASE + "/#/new")
        page.get_by_placeholder("имя кампании").fill(NAME)
        page.get_by_placeholder("MX,AU,RO,...").fill("AU, mx")
        search = page.get_by_placeholder("поиск по офферам: ID или название")
        for oid in ("18001", "18002", "18003"):
            search.click(); search.fill(oid)
            page.locator(".combo-list li", has_text=oid).first.click()
        shot("creator-form")
        page.get_by_role("button", name="Create").click()
        expect(page.get_by_text("Готово")).to_be_visible(timeout=20000)
        shot("creator-done")
        step("Создаватор: кампания создана через UI")

        page.get_by_role("link", name="Открыть в редакторе").click()
        expect(page.locator("section.stream").first).to_be_visible()
        kt_id = int(page.locator(".meta-line b.mono").inner_text())
        camp = KT.get(f"campaigns/{kt_id}").json()
        streams = KT.get(f"campaigns/{kt_id}/streams").json()
        geo, offers = streams
        assert camp["name"] == f"test_lebedev_{NAME}", camp["name"]
        assert (camp["domain_id"], camp["group_id"], camp["traffic_source_id"], camp["type"]) == (1813, 10332, 836, "position"), camp
        assert geo["filters"][0]["payload"] == ["AU", "MX"] and geo["filters"][0]["mode"] == "accept"
        assert geo["action_payload"] == "https://google.com" and geo["schema"] == "redirect"
        assert offers["type"] == "default" and kt_offers(offers["id"]) == {18001: 34, 18002: 33, 18003: 33}
        S = offers["id"]
        step(f"KT проверка: кампания {kt_id}, домен {camp['domain']}, группа {camp['group']}, источник {camp['traffic_source_id']}, гео {geo['filters'][0]['payload']}, офферы {kt_offers(S)}")
        shot("editor-fetched")

        card = page.locator("section.stream", has_text="Offers")
        row = lambda oid: card.locator("tr", has_text=oid)
        share = lambda oid: row(oid).locator(".share-value").inner_text()

        # ---------- ADD
        card.get_by_placeholder("ID или название оффера").click()
        card.get_by_placeholder("ID или название оффера").fill("18004")
        page.locator(".combo-list li", has_text="18004").first.click()
        card.get_by_role("button", name="ADD").click()
        expect(card).to_have_class(re.compile("dirty"))
        assert [share(o) for o in ("18001", "18002", "18003", "18004")] == ["25%"] * 4
        assert kt_offers(S) == {18001: 34, 18002: 33, 18003: 33}
        shot("add-offer-unpublished")
        step("ADD 18004: 4×25%, поток жёлтый, в KT без изменений")

        card.get_by_role("button", name="PUSH TO KT").click()
        expect(card).not_to_have_class(re.compile("dirty"))
        assert kt_offers(S) == {18001: 25, 18002: 25, 18003: 25, 18004: 25}
        shot("after-push")
        step("PUSH: в KT 4×25%")

        # ---------- ADD + CANCEL
        card.get_by_placeholder("ID или название оффера").click()
        card.get_by_placeholder("ID или название оффера").fill("18005")
        page.locator(".combo-list li", has_text="18005").first.click()
        card.get_by_role("button", name="ADD").click()
        expect(row("18005")).to_be_visible()
        assert share("18005") == "20%"
        shot("add-fifth-20")
        card.get_by_role("button", name="CANCEL").click()
        expect(row("18005")).to_have_count(0)
        expect(card).not_to_have_class(re.compile("dirty"))
        shot("after-cancel")
        step("ADD 18005 → 5×20%, CANCEL → привязка исчезла, снова 4×25%")

        # ---------- REMOVE + PUSH
        row("18002").get_by_role("button", name="REMOVE").click()
        expect(row("18002").get_by_role("button", name="BRING BACK")).to_be_visible()
        assert [share(o) for o in ("18001", "18002", "18003", "18004")] == ["34%", "0%", "33%", "33%"]
        shot("remove-offer")
        card.get_by_role("button", name="PUSH TO KT").click()
        expect(card).not_to_have_class(re.compile("dirty"))
        assert kt_offers(S) == {18001: 34, 18003: 33, 18004: 33}, kt_offers(S)
        shot("removed-archived-after-push")
        step("REMOVE 18002 → 34/0/33/33, PUSH → оффер удалён из KT (не share=0), в обёртке архив")

        # ---------- BRING BACK + PUSH
        row("18002").get_by_role("button", name="BRING BACK").click()
        expect(card).to_have_class(re.compile("dirty"))
        card.get_by_role("button", name="PUSH TO KT").click()
        expect(card).not_to_have_class(re.compile("dirty"))
        assert kt_offers(S) == {18001: 25, 18002: 25, 18003: 25, 18004: 25}
        step("BRING BACK 18002 + PUSH → в KT снова 4×25%")

        # ---------- delete directly in KT
        cur = KT.get(f"streams/{S}").json()["offers"]
        keep = [{"offer_id": o["offer_id"], "share": o["share"], "state": o["state"]} for o in cur if o["offer_id"] in (18002, 18004)]
        r = KT.put(f"streams/{S}", json={"offers": keep}); r.raise_for_status()
        page.get_by_role("button", name=re.compile("FETCH STREAMS FROM KT")).click()
        expect(row("18001").get_by_role("button", name="BRING BACK")).to_be_visible()
        expect(row("18003").get_by_role("button", name="BRING BACK")).to_be_visible()
        expect(card.get_by_text("Сумма активных долей не равна 100%")).to_be_visible()
        shot("fetch-after-kt-delete")
        step("Удалили 18001 и 18003 прямо в KT (осталось 25+25=50%) → FETCH: оба в архиве, предупреждение о сумме 50%")

        # ---------- PIN + BRING BACK + PUSH
        row("18002").locator("button.pin").click()
        expect(row("18002").locator("button.pin.on")).to_be_visible()
        row("18001").get_by_role("button", name="BRING BACK").click()
        expect(card).to_have_class(re.compile("dirty"))
        got = {o: share(o) for o in ("18001", "18002", "18004")}
        assert got["18002"] == "25%" and sorted([got["18001"], got["18004"]]) == ["37%", "38%"], got
        shot("pinned-weight")
        card.get_by_role("button", name="PUSH TO KT").click()
        expect(card).not_to_have_class(re.compile("dirty"))
        final = kt_offers(S)
        assert final[18002] == 25 and sorted([final[18001], final[18004]]) == [37, 38] and sum(final.values()) == 100, final
        shot("final-published")
        step(f"PIN 18002=25%, BRING BACK 18001 → 25/38/37, PUSH → в KT {final} (сумма 100)")

        # ---------- validation screenshot of creator
        page.goto(BASE + "/#/new")
        page.get_by_placeholder("имя кампании").fill("x")
        page.get_by_placeholder("MX,AU,RO,...").fill("AU,XX,UK")
        shot("creator-geo-validation")
        page.goto(BASE + "/#/")
        expect(page.get_by_text(f"test_lebedev_{NAME}")).to_be_visible()
        shot("campaign-list")
        json.dump({"kt_campaign_id": kt_id, "offers_stream_id": S, "geo_stream_id": geo["id"], "final": final, "log": log},
                  open(f"{SHOTS}/e2e-result.json", "w"), ensure_ascii=False, indent=1)
        print("OK", kt_id, S)
    except Exception:
        page.screenshot(path=f"{SHOTS}/zz-failure.png", full_page=True)
        raise
    finally:
        browser.close()
