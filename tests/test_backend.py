# меню IM, наличие, допродажа, sqlite, новые эндпоинты
import importlib
import uuid

import pytest
from fastapi.testclient import TestClient

from voice_cart_nlu.actions import Action
from voice_cart_nlu.cart import CartSession
from voice_cart_nlu.menu import DEFAULT_MENU_PATH, Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline
from voice_cart_nlu.schemas import LineRef
from voice_cart_nlu.store import Store
from voice_cart_nlu.upsell import DEFAULT_RULES, UpsellRule, check_rules

IM = Menu.load(DEFAULT_MENU_PATH)                  # настоящее меню, не тестовое
RULES = [UpsellRule(**r) for r in DEFAULT_RULES]


def im_menu() -> Menu:
    return Menu.load(DEFAULT_MENU_PATH)            # копия, тесты меняют available


def add(item_id, **kw):
    return Action(type="add_item", item_id=item_id, **kw)


# меню i'm
def test_im_menu_has_20_to_30_items_with_kazakh_and_english_names():
    assert 20 <= len(IM.items) <= 30
    assert len({i.id for i in IM.items}) == len(IM.items)
    assert all(i.name_kk and i.name_en and i.price_cents > 0 and i.aliases for i in IM.items)
    assert all(m.name_kk and m.name_en for m in IM.modifiers)


def test_im_menu_references_are_consistent():
    mod_ids = {m.id for m in IM.modifiers}
    for item in IM.items:
        assert set(item.modifiers) <= mod_ids, item.id
        assert set(item.size_prices_cents) == set(item.sizes), item.id
        for ch in item.choices:
            assert ch.kind == "size" or all(IM.item(o) for o in ch.options), (item.id, ch.id)
    assert check_rules(RULES, IM) == []


@pytest.mark.parametrize("text, expected", [
    ("два чизбургера и большую колу", [("cheeseburger", 2, None), ("coca_cola", 1, "L")]),
    ("free", [("fries", 1, "M")]),                      # b12: "фри" латиницей
    ("кофе", [("americano", 1, None)]),
    ("латте с сиропом", [("latte", 1, None)]),
])
def test_nlu_understands_im_menu(text, expected):
    s = CartSession(IM)
    s.handle(VoiceCommandPipeline(IM).parse_text(text).commands)
    assert [(l.item_id, l.quantity, l.size.value if l.size else None) for l in s.lines] == expected


def test_with_cheese_is_modifier_not_cheese_sauce():
    s = CartSession(IM)
    s.handle(VoiceCommandPipeline(IM).parse_text("чизбургер с сыром").commands)
    assert [(l.item_id, [(m.modifier_id, m.op) for m in l.modifiers]) for l in s.lines] == \
           [("cheeseburger", [("cheese", "add")])]


def test_im_prices():
    s = CartSession(IM)
    r = s.apply([add("cheeseburger", quantity=2), add("coca_cola", size="L"), add("fries")])
    assert r.cart.total_cents == 2 * 95000 + 60000 + 65000


# наличие
def test_unavailable_item_is_not_added():
    menu = im_menu()
    menu.item("milkshake").available = False
    s = CartSession(menu)
    r = s.apply([add("milkshake")])
    assert s.lines == [] and r.notes == ["Извините, «Молочный коктейль ванильный» сейчас нет в наличии"]


def test_unavailable_combo_option_is_reasked_without_it():
    menu = im_menu()
    menu.item("sprite").available = False
    s = CartSession(menu)
    s.apply([add("combo_big_burger")])
    r = s.apply([Action(type="set_combo_choice", choice_id="drink", value="sprite")])
    assert s.lines[0].choices == {}
    assert "нет в наличии" in r.notes[0] and "Sprite" not in r.question


def test_confirm_blocked_when_item_ran_out():
    menu = im_menu()
    s = CartSession(menu)
    s.apply([add("cinnabon")])
    menu.item("cinnabon").available = False
    r = s.apply([Action(type="confirm")])
    assert s.status == "open" and r.notes[0].startswith("Закончилось: Синнабон")


# upsell
def test_upsell_after_burger_and_yes_adds_it():
    s = CartSession(IM, RULES)
    r = s.apply([add("cheeseburger")])
    assert r.upsell.item_id == "fries" and r.upsell.price_cents == 65000

    pipe = VoiceCommandPipeline(IM)
    r = s.handle(pipe.parse_text("да").commands, "да")
    assert [l.item_id for l in s.lines] == ["cheeseburger", "fries"]
    assert s.status == "open"                           # "да" на допродажу не подтверждает заказ


def test_upsell_no_keeps_cart():
    s = CartSession(IM, RULES)
    s.apply([add("cheeseburger")])
    pipe = VoiceCommandPipeline(IM)
    r = s.handle(pipe.parse_text("нет").commands, "нет")
    assert [l.item_id for l in s.lines] == ["cheeseburger"] and r.notes == [] and r.upsell is None


def test_upsell_offers_each_item_once_and_skips_what_is_in_cart():
    s = CartSession(IM, RULES)
    assert s.apply([add("cheeseburger")]).upsell.item_id == "fries"
    assert s.apply([add("hamburger")]).upsell.item_id == "coca_cola"     # фри уже предлагали
    assert s.apply([add("cinnabon")]).upsell is None                     # не больше двух за заказ


def test_upsell_skips_unavailable_and_waits_for_combo_question():
    menu = im_menu()
    menu.item("fries").available = False
    s = CartSession(menu, RULES)
    assert s.apply([add("cheeseburger")]).upsell.item_id == "coca_cola"
    r = s.apply([add("combo_nuggets")])
    assert r.question and r.upsell is None              # сначала вопрос про комбо


# хранение
def test_cart_state_roundtrip_keeps_last_line_and_offers():
    s = CartSession(IM, RULES)
    s.apply([add("americano", quantity=2), add("cheeseburger"),
             Action(type="change_quantity", target=LineRef(menu_item_id="americano"), quantity=3)])
    restored = CartSession.from_state(IM, s.to_state(), RULES)
    assert restored.view() == s.view()
    restored.apply([Action(type="add_modifier", modifier_id="sugar")])      # неявная ссылка -> американо
    assert [m.modifier_id for m in restored.lines[0].modifiers] == ["sugar"]
    assert restored.offered == s.offered


def test_store_survives_reopen(tmp_path):
    path = tmp_path / "carts.db"
    Store(path).save_cart("cart-1", {"lines": [], "status": "open"})
    Store(path).save_upsell_rules([])
    reopened = Store(path)
    assert reopened.load_cart("cart-1") == {"lines": [], "status": "open"}
    assert reopened.upsell_rules() == []                # пустой список не заменяется дефолтом


def test_store_purges_old_carts(tmp_path):
    store = Store(tmp_path / "carts.db")
    store.save_cart("old", {})
    assert store.purge_old_carts(ttl_s=-1) == 1 and store.load_cart("old") is None


# api
@pytest.fixture(scope="module")
def api(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    for k in ("ELEVENLABS_API_KEY", "ANTHROPIC_API_KEY", "STT_PROVIDER", "WHISPER_FALLBACK", "ADMIN_TOKEN"):
        mp.delenv(k, raising=False)
    mp.setenv("MENU_PATH", str(DEFAULT_MENU_PATH))
    mp.setenv("CART_DB", str(tmp_path_factory.mktemp("db") / "carts.db"))
    mp.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    import voice_cart_nlu.api as mod
    mod = importlib.reload(mod)
    yield mod
    mp.undo()


@pytest.fixture
def client(api):
    api.store.clear()
    api.store.save_stop_list([])
    api._apply_stop_list(api.pipeline.menu, [], api.BASE_AVAILABLE)
    api.store.save_upsell_rules(DEFAULT_RULES)
    return TestClient(api.app)


def cart(client) -> str:
    r = client.post("/cart")
    assert r.status_code == 201
    return r.json()["cart_id"]


def actions(client, cid, *acts):
    r = client.post(f"/cart/{cid}/actions", json={"actions": list(acts)})
    assert r.status_code == 200, r.text
    return r.json()


def test_new_cart_id_is_server_uuid(client):
    assert uuid.UUID(cart(client))


def test_short_guessable_session_id_is_rejected(client):
    assert client.get("/cart/demo").status_code == 422
    assert client.post("/cart/1/text", json={"text": "бургер"}).status_code == 422


def test_menu_endpoint(client):
    body = client.get("/menu").json()
    assert len(body["items"]) == 30 and body["items"][0]["name_kk"]


def test_buttons_send_actions_and_get_upsell(client):
    cid = cart(client)
    r = actions(client, cid, {"type": "add_item", "item_id": "cheeseburger", "quantity": 2})
    assert r["cart"]["total_cents"] == 190000
    assert r["upsell"]["item_id"] == "fries" and r["upsell"]["text"]
    r = actions(client, cid, {"type": "change_quantity", "target": {"ordinal": 1}})     # b1: без quantity
    assert r["notes"] == ["Не понял, сколько штук"] and r["cart"]["lines"][0]["quantity"] == 2


def test_cart_is_saved_between_requests(client, api):
    cid = cart(client)
    actions(client, cid, {"type": "add_item", "item_id": "latte"})
    assert api.store.load_cart(cid)["lines"][0]["item_id"] == "latte"
    assert client.get(f"/cart/{cid}").json()["lines"][0]["item_id"] == "latte"


def test_voice_yes_accepts_upsell(client):
    cid = cart(client)
    r = client.post(f"/cart/{cid}/text", json={"text": "чизбургер"}).json()
    assert r["upsell"]["item_id"] == "fries"
    r = client.post(f"/cart/{cid}/text", json={"text": "да"}).json()
    assert [l["item_id"] for l in r["cart"]["lines"]] == ["cheeseburger", "fries"]


def test_stop_list_from_admin(client):
    assert client.put("/admin/stop-list", json={"item_ids": ["cinnabon"]}).status_code == 200
    assert client.get("/admin/stop-list").json() == {"item_ids": ["cinnabon"]}
    assert next(i for i in client.get("/menu").json()["items"] if i["id"] == "cinnabon")["available"] is False
    r = actions(client, cart(client), {"type": "add_item", "item_id": "cinnabon"})
    assert r["cart"]["lines"] == [] and "нет в наличии" in r["notes"][0]
    assert client.put("/admin/stop-list", json={"item_ids": ["pizza"]}).status_code == 422


def test_upsell_rules_from_admin(client):
    rules = [{"trigger": "drink", "offer": "cherry_pie", "text": "Пирожок к напитку?"}]
    assert client.put("/admin/upsell", json=rules).status_code == 200
    assert client.get("/admin/upsell").json() == rules
    r = actions(client, cart(client), {"type": "add_item", "item_id": "tea"})
    assert r["upsell"]["item_id"] == "cherry_pie" and r["upsell"]["text"] == "Пирожок к напитку?"
    bad = client.put("/admin/upsell", json=[{"trigger": "pizza", "offer": "fries"}])
    assert bad.status_code == 422


def test_admin_token_required_when_set(client, api, monkeypatch):
    monkeypatch.setattr(api, "ADMIN_TOKEN", "secret")
    assert client.put("/admin/stop-list", json={"item_ids": []}).status_code == 401
    ok = client.put("/admin/stop-list", json={"item_ids": []}, headers={"X-Admin-Token": "secret"})
    assert ok.status_code == 200


def test_limits_on_text_and_audio(client, api, monkeypatch):
    cid = cart(client)
    assert client.post(f"/cart/{cid}/text", json={"text": "бургер " * 100}).status_code == 422

    class FakeSTT:
        def transcribe(self, audio, **kw):
            raise AssertionError("слишком большой файл не должен уходить в STT")

    monkeypatch.setattr(api.pipeline, "stt", FakeSTT())
    big = b"\x00" * (api.MAX_AUDIO_BYTES + 1)
    r = client.post(f"/cart/{cid}/voice", files={"audio": ("a.webm", big, "audio/webm")})
    assert r.status_code == 413


def test_admin_page_served(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "Стоп-лист" in r.text
