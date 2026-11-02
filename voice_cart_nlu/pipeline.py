"""Речь/текст -> NLUResult (список Command). Дальше — Cart State Machine."""
from __future__ import annotations

import os
import time
from typing import Optional

from . import rules
from .llm_parser import LLMClient, llm_parse
from .menu import Menu, MenuIndex
from .schemas import CartContext, Command, Intent, NLUResult
from .stt import STTProvider
from .validate import validate_commands


class VoiceCommandPipeline:
    def __init__(self, menu: Menu, stt: Optional[STTProvider] = None,
                 llm: Optional[LLMClient] = None, llm_threshold: float = 0.75):
        self.menu, self.idx = menu, MenuIndex(menu)
        self.stt, self.llm, self.threshold = stt, llm, llm_threshold
        self.hints = [i.name for i in menu.items]          # подсказки для STT

    def parse_text(self, text: str, cart: Optional[CartContext] = None,
                   transcript_meta: Optional[dict] = None) -> NLUResult:
        t = time.perf_counter()
        cmds = rules.parse(text, self.idx, cart)
        timings = {"rules": (time.perf_counter() - t) * 1000}
        if self.llm and any(c.intent == Intent.unknown or c.confidence < self.threshold for c in cmds):
            t = time.perf_counter()
            try:
                alt = llm_parse(text, self.menu, self.llm, cart)
            except Exception:                              # сеть/лимиты: остаёмся на rules
                alt = []
            timings["llm"] = (time.perf_counter() - t) * 1000
            if alt and not all(c.intent == Intent.unknown for c in alt):
                cmds = alt
        cmds = validate_commands(cmds, self.menu)
        lang = cmds[0].lang if cmds else rules.detect_lang(text)
        return NLUResult(transcript=text, lang=lang, commands=cmds, timings_ms=timings)

    def parse_audio(self, audio: bytes, cart: Optional[CartContext] = None, filename="audio.webm",
                    mime="audio/webm", language: Optional[str] = None) -> NLUResult:
        if not self.stt:
            raise RuntimeError("STT provider is not configured")
        s = self.stt.transcribe(audio, filename=filename, mime=mime, language=language, hints=self.hints)
        res = self.parse_text(s.text, cart)
        res.stt_provider = s.provider
        res.timings_ms["stt"] = s.latency_ms
        res.timings_ms["total"] = sum(res.timings_ms.values())
        if s.language:
            res.lang = s.language
            for c in res.commands:
                c.lang = s.language
        return res


def build_pipeline() -> VoiceCommandPipeline:
    """Конфигурация из env: ELEVENLABS_API_KEY / STT_PROVIDER=whisper, ANTHROPIC_API_KEY, MENU_PATH."""
    from .stt import ElevenLabsSTT, FallbackSTT, WhisperSTT
    menu = Menu.load()
    stt = None
    if os.getenv("STT_PROVIDER", "elevenlabs") == "whisper":
        stt = WhisperSTT(os.getenv("WHISPER_MODEL", "large-v3"))
    elif os.getenv("ELEVENLABS_API_KEY"):
        stt = FallbackSTT(ElevenLabsSTT(), WhisperSTT(os.getenv("WHISPER_MODEL", "small"))) \
            if os.getenv("WHISPER_FALLBACK") else ElevenLabsSTT()
    llm = None
    if os.getenv("ANTHROPIC_API_KEY"):
        from .llm_parser import AnthropicJSONClient
        llm = AnthropicJSONClient()
    return VoiceCommandPipeline(menu, stt=stt, llm=llm)
