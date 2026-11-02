# запуск: uvicorn voice_cart_nlu.api:app --reload, админка на /admin
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Path as PathParam, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()                                   # ELEVENLABS_API_KEY из .env, до build_pipeline()

from .actions import Action  # noqa: E402
from .cart import CartSession, CartView, Reply  # noqa: E402
from .menu import Menu  # noqa: E402
from .pipeline import build_pipeline  # noqa: E402
from .schemas import CartContext, NLUResult  # noqa: E402
from .store import Store  # noqa: E402
from .upsell import DEFAULT_RULES, UpsellRule, check_rules  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voice_cart")

MAX_AUDIO_BYTES = 5 * 1024 * 1024               # примерно 5 минут webm
MAX_TEXT_LEN = 500
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")          # если задан, админка требует X-Admin-Token
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Voice Cart NLU")
# index.html, открытый как файл, шлёт запросы с Origin "null"; в проде — указать реальный домен
app.add_middleware(CORSMiddleware, allow_origins=["null", "http://127.0.0.1:8000", "http://localhost:8000",
                                                  "http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
pipeline = build_pipeline()
store = Store(os.getenv("CART_DB", "carts.db"))
store.purge_old_carts()

# короткие id вроде "demo" запрещены, их легко угадать
SessionId = PathParam(pattern=r"^[\w.-]{16,64}$")


# стоп-лист и upsell
def _apply_stop_list(menu: Menu, stopped: list[str], base: dict[str, bool]) -> None:
    for item in menu.items:
        item.available = base[item.id] and item.id not in stopped


BASE_AVAILABLE = {i.id: i.available for i in pipeline.menu.items}   # как в menu.json
_apply_stop_list(pipeline.menu, store.stop_list(), BASE_AVAILABLE)


def upsell_rules() -> list[UpsellRule]:
    saved = store.upsell_rules()
    return [UpsellRule(**r) for r in (DEFAULT_RULES if saved is None else saved)]


# модели запросов и ответов
class TextReq(BaseModel):
    text: str = Field(max_length=MAX_TEXT_LEN)
    cart: Optional[CartContext] = None


class CartTextReq(BaseModel):
    text: str = Field(max_length=MAX_TEXT_LEN)


class ActionsReq(BaseModel):
    actions: list[Action] = Field(min_length=1, max_length=20)


class CartStep(Reply):
    transcript: str
    lang: str
    timings_ms: dict[str, float]


class NewCart(BaseModel):
    cart_id: str


class StopList(BaseModel):
    item_ids: list[str]


# корзина
def _load(session_id: str) -> CartSession:
    state = store.load_cart(session_id)
    rules = upsell_rules()
    return CartSession.from_state(pipeline.menu, state, rules) if state else CartSession(pipeline.menu, rules)


def _save(session_id: str, s: CartSession) -> None:
    store.save_cart(session_id, s.to_state())


def _step(session_id: str, s: CartSession, res: NLUResult) -> CartStep:
    reply = s.handle(res.commands, res.transcript)
    _save(session_id, s)
    log.info("cart=%s text=%r actions=%s notes=%s", session_id[:8], res.transcript,
             [a.type for a in reply.actions], reply.notes)
    return CartStep(**reply.model_dump(), transcript=res.transcript, lang=res.lang, timings_ms=res.timings_ms)


def _read_audio(audio: UploadFile) -> bytes:
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Аудио слишком длинное, скажите заказ короче")
    return data


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/menu", response_model=Menu)
def menu():
    # меню с учетом стоп-листа
    return pipeline.menu


@app.post("/cart", response_model=NewCart, status_code=201)
def cart_create():
    store.purge_old_carts()
    return NewCart(cart_id=str(uuid.uuid4()))


@app.post("/nlu/text", response_model=NLUResult)
def nlu_text(req: TextReq):
    return pipeline.parse_text(req.text, req.cart)


@app.post("/nlu/voice", response_model=NLUResult)
def nlu_voice(audio: UploadFile = File(...), cart: Optional[str] = Form(None),
                    lang: Optional[str] = Form(None)):
    if pipeline.stt is None:
        raise HTTPException(503, "STT is not configured (set ELEVENLABS_API_KEY or STT_PROVIDER=whisper)")
    ctx = CartContext.model_validate_json(cart) if cart else None
    return pipeline.parse_audio(_read_audio(audio), ctx, audio.filename or "audio.webm",
                                audio.content_type or "audio/webm", lang)


@app.post("/cart/{session_id}/voice", response_model=CartStep)
def cart_voice(session_id: str = SessionId, audio: UploadFile = File(...), lang: Optional[str] = Form(None)):
    if pipeline.stt is None:
        raise HTTPException(503, "STT is not configured (set ELEVENLABS_API_KEY or STT_PROVIDER=whisper)")
    data = _read_audio(audio)
    s = _load(session_id)
    try:
        res = pipeline.parse_audio(data, s.context(), audio.filename or "audio.webm",
                                   audio.content_type or "audio/webm", lang)
    except Exception as exc:                    # сеть, лимиты, неверный ключ
        log.warning("STT failed: %s", exc)
        raise HTTPException(502, f"STT failed: {exc}")
    return _step(session_id, s, res)


@app.post("/cart/{session_id}/text", response_model=CartStep)
def cart_text(req: CartTextReq, session_id: str = SessionId):
    s = _load(session_id)
    return _step(session_id, s, pipeline.parse_text(req.text, s.context()))


@app.post("/cart/{session_id}/actions", response_model=CartStep)
def cart_actions(req: ActionsReq, session_id: str = SessionId):
    # кнопки киоска, формат как у nlu
    s = _load(session_id)
    reply = s.apply(req.actions)
    _save(session_id, s)
    return CartStep(**reply.model_dump(), transcript="", lang="ru", timings_ms={})


@app.get("/cart/{session_id}", response_model=CartView)
def cart_get(session_id: str = SessionId):
    return _load(session_id).view()


@app.delete("/cart/{session_id}", status_code=204)
def cart_reset(session_id: str = SessionId):
    store.delete_cart(session_id)


# админка
def admin(x_admin_token: Optional[str] = Header(None)) -> None:
    if ADMIN_TOKEN and x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Нужен заголовок X-Admin-Token")


@app.get("/admin/upsell", response_model=list[UpsellRule])
def upsell_get():
    return upsell_rules()


@app.put("/admin/upsell", response_model=list[UpsellRule], dependencies=[Depends(admin)])
def upsell_put(rules: list[UpsellRule]):
    errors = check_rules(rules, pipeline.menu)
    if errors:
        raise HTTPException(422, errors)
    store.save_upsell_rules([r.model_dump() for r in rules])
    log.info("upsell rules saved: %d", len(rules))
    return rules


@app.get("/admin/stop-list", response_model=StopList)
def stop_list_get():
    return StopList(item_ids=store.stop_list())


@app.put("/admin/stop-list", response_model=StopList, dependencies=[Depends(admin)])
def stop_list_put(req: StopList):
    unknown = [i for i in req.item_ids if not pipeline.menu.item(i)]
    if unknown:
        raise HTTPException(422, [f"Нет блюда «{i}»" for i in unknown])
    store.save_stop_list(req.item_ids)
    _apply_stop_list(pipeline.menu, req.item_ids, BASE_AVAILABLE)
    log.info("stop list: %s", req.item_ids)
    return req
