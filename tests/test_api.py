"""Integration: FastAPI целиком (pipeline + корзина + сессии) через TestClient, без сети и ключей."""
import importlib
import uuid

import pytest
from fastapi.testclient import TestClient


def U(name: str) -> str:
    # короткие id api отклоняет
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    for k in ("ELEVENLABS_API_KEY", "ANTHROPIC_API_KEY", "STT_PROVIDER", "WHISPER_FALLBACK", "ADMIN_TOKEN"):
        mp.delenv(k, raising=False)
    mp.setenv("CART_DB", str(tmp_path_factory.mktemp("db") / "carts.db"))   # меню из conftest
    mp.setattr("dotenv.load_dotenv", lambda *a, **k: False)   # локальный .env с ключами не подхватываем
    import voice_cart_nlu.api as mod
    mod = importlib.reload(mod)
    yield mod
    mp.undo()


@pytest.fixture
def client(api):
    api.store.clear()
    return TestClient(api.app)


def say(client, sid, text):
    r = client.post(f"/cart/{sid}/text", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def items(cart):
    return [(l["item_id"], l["quantity"], l["size"]) for l in cart["lines"]]


def test_full_dialog_from_task(client):
    say(client, U("g1"), "два бургера и большую колу")
    say(client, U("g1"), "убери один бургер")
    step = say(client, U("g1"), "колу сделай маленькой")
    assert items(step["cart"]) == [("burger", 1, None), ("cola", 1, "S")]
    assert step["cart"]["total_cents"] == 180000 + 50000
    assert client.get(f"/cart/{U('g1')}").json() == step["cart"]


def test_combo_question_then_answers(client):
    step = say(client, U("g2"), "комбо")
    assert step["question"] and step["cart"]["has_pending"]
    assert step["cart"]["total_cents"] == 0                # ожидающее комбо не входит в сумму
    say(client, U("g2"), "спрайт")
    say(client, U("g2"), "наггетсы")
    step = say(client, U("g2"), "большой")
    assert not step["cart"]["has_pending"] and step["question"] is None
    assert step["cart"]["total_cents"] == 290000 + 20000


def test_confirm_flow(client):
    say(client, U("g3"), "кофе")
    step = say(client, U("g3"), "подтверждаю")
    assert step["cart"]["status"] == "confirmed"


def test_sessions_are_isolated(client):
    say(client, U("a"), "бургер")
    say(client, U("b"), "вода")
    assert items(client.get(f"/cart/{U('a')}").json()) == [("burger", 1, None)]
    assert items(client.get(f"/cart/{U('b')}").json()) == [("water", 1, None)]


def test_delete_resets_session(client):
    say(client, U("g4"), "два бургера")
    assert client.delete(f"/cart/{U('g4')}").status_code == 204
    assert client.get(f"/cart/{U('g4')}").json()["lines"] == []


def test_unknown_session_is_empty_cart(client):
    cart = client.get(f"/cart/{U('never-seen')}").json()
    assert cart["lines"] == [] and cart["total_cents"] == 0 and cart["status"] == "open"


def test_unknown_item_explained_cart_untouched(client):
    step = say(client, U("g5"), "хочу пиццу")
    assert step["cart"]["lines"] == [] and (step["notes"] or step["question"])


def test_step_has_transcript_lang_and_timings(client):
    step = say(client, U("g6"), "екі бургер")
    assert step["transcript"] == "екі бургер" and step["lang"] == "kk"
    assert "rules" in step["timings_ms"]


def test_nlu_text_does_not_touch_any_cart(client):
    r = client.post("/nlu/text", json={"text": "два бургера"})
    assert r.status_code == 200 and r.json()["commands"][0]["intent"] == "add"
    assert client.get(f"/cart/{U('g7')}").json()["lines"] == []


@pytest.mark.parametrize("payload", [{}, {"txt": "бургер"}, {"text": None}, {"text": 123}])
def test_bad_text_payload_is_422(client, payload):
    assert client.post(f"/cart/{U('g8')}/text", json=payload).status_code == 422


def test_empty_text_does_not_crash(client):
    step = say(client, U("g9"), "")
    assert step["cart"]["lines"] == []


def test_voice_without_stt_is_503_not_500(client):
    files = {"audio": ("a.webm", b"\x00\x01", "audio/webm")}
    assert client.post(f"/cart/{U('g10')}/voice", files=files).status_code == 503
    assert client.post("/nlu/voice", files=files).status_code == 503


def test_voice_with_fake_stt(client, api, monkeypatch):
    from voice_cart_nlu.stt import STTResult

    class FakeSTT:
        def transcribe(self, audio, **kw):
            return STTResult("два комбо", "ru", "fake", 5.0)

    monkeypatch.setattr(api.pipeline, "stt", FakeSTT())
    r = client.post(f"/cart/{U('g11')}/voice", files={"audio": ("a.webm", b"\x00", "audio/webm")})
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "два комбо" and items(body["cart"]) == [("combo", 2, None)]
    assert "stt" in body["timings_ms"]


def test_voice_stt_failure_is_502(client, api, monkeypatch):
    class BrokenSTT:
        def transcribe(self, audio, **kw):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(api.pipeline, "stt", BrokenSTT())
    r = client.post(f"/cart/{U('g12')}/voice", files={"audio": ("a.webm", b"\x00", "audio/webm")})
    assert r.status_code == 502


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "html" in r.headers["content-type"]
