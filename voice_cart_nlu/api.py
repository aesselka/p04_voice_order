"""uvicorn voice_cart_nlu.api:app --reload   ->   http://127.0.0.1:8000/"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()                                   # ELEVENLABS_API_KEY из .env, до build_pipeline()

from .cart import CartSession, CartView, Reply  # noqa: E402
from .pipeline import build_pipeline  # noqa: E402
from .schemas import CartContext, NLUResult  # noqa: E402

app = FastAPI(title="Voice Cart NLU")
# index.html, открытый как файл, шлёт запросы с Origin "null"; в проде — указать реальный домен
app.add_middleware(CORSMiddleware, allow_origins=["null", "http://127.0.0.1:8000", "http://localhost:8000"],
                   allow_methods=["*"], allow_headers=["*"])
pipeline = build_pipeline()
sessions: dict[str, CartSession] = {}           # в памяти: сбрасывается при перезапуске
INDEX_HTML = Path(__file__).parent / "static" / "index.html"


class TextReq(BaseModel):
    text: str
    cart: Optional[CartContext] = None


class CartTextReq(BaseModel):
    text: str


class CartStep(Reply):
    transcript: str
    lang: str
    timings_ms: dict[str, float]


def _session(session_id: str) -> CartSession:
    return sessions.setdefault(session_id, CartSession(pipeline.menu))


def _step(s: CartSession, res: NLUResult) -> CartStep:
    reply = s.handle(res.commands)
    return CartStep(**reply.model_dump(), transcript=res.transcript, lang=res.lang, timings_ms=res.timings_ms)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(INDEX_HTML)


@app.post("/nlu/text", response_model=NLUResult)
def nlu_text(req: TextReq):
    return pipeline.parse_text(req.text, req.cart)


@app.post("/nlu/voice", response_model=NLUResult)
def nlu_voice(audio: UploadFile = File(...), cart: Optional[str] = Form(None),
              lang: Optional[str] = Form(None)):
    if pipeline.stt is None:
        raise HTTPException(503, "STT is not configured (set ELEVENLABS_API_KEY or STT_PROVIDER=whisper)")
    ctx = CartContext.model_validate_json(cart) if cart else None
    return pipeline.parse_audio(audio.file.read(), ctx, audio.filename or "audio.webm",
                                audio.content_type or "audio/webm", lang)


@app.post("/cart/{session_id}/voice", response_model=CartStep)
def cart_voice(session_id: str, audio: UploadFile = File(...), lang: Optional[str] = Form(None)):
    if pipeline.stt is None:
        raise HTTPException(503, "STT is not configured (set ELEVENLABS_API_KEY or STT_PROVIDER=whisper)")
    s = _session(session_id)
    try:
        res = pipeline.parse_audio(audio.file.read(), s.context(), audio.filename or "audio.webm",
                                   audio.content_type or "audio/webm", lang)
    except Exception as exc:                    # сеть, лимиты, неверный ключ
        raise HTTPException(502, f"STT failed: {exc}")
    return _step(s, res)


@app.post("/cart/{session_id}/text", response_model=CartStep)
def cart_text(session_id: str, req: CartTextReq):
    s = _session(session_id)
    return _step(s, pipeline.parse_text(req.text, s.context()))


@app.get("/cart/{session_id}", response_model=CartView)
def cart_get(session_id: str):
    return _session(session_id).view()


@app.delete("/cart/{session_id}", status_code=204)
def cart_reset(session_id: str):
    sessions.pop(session_id, None)
