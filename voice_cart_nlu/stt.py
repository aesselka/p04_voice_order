"""STT-провайдеры: ElevenLabs Scribe (основной) и Whisper (локальный fallback)."""
from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from typing import Optional, Protocol

LANG3 = {"ru": "rus", "kk": "kaz"}           # ElevenLabs принимает ISO-639-3
LANG2 = {"rus": "ru", "kaz": "kk", "ru": "ru", "kk": "kk"}


@dataclass
class STTResult:
    text: str
    language: Optional[str]            # "ru" | "kk" | None
    provider: str
    latency_ms: float
    confidence: Optional[float] = None


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, filename: str = "audio.webm", mime: str = "audio/webm",
                   language: Optional[str] = None, hints: Optional[list[str]] = None) -> STTResult: ...


class ElevenLabsSTT:
    URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(self, api_key: Optional[str] = None, model_id: Optional[str] = None, timeout: float = 20.0):
        self.api_key = api_key or os.environ["ELEVENLABS_API_KEY"]
        # актуальный model_id сверьте с докой ElevenLabs STT
        self.model_id = model_id or os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
        self.timeout = timeout

    def transcribe(self, audio, filename="audio.webm", mime="audio/webm", language=None, hints=None):
        import httpx
        t0 = time.perf_counter()
        data = {"model_id": self.model_id, "tag_audio_events": "false"}
        if language in LANG3:                       # язык из переключателя в UI -> точнее и быстрее
            data["language_code"] = LANG3[language]
        r = httpx.post(self.URL, headers={"xi-api-key": self.api_key}, data=data,
                       files={"file": (filename, audio, mime)}, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        return STTResult(
            text=(j.get("text") or "").strip(),
            language=LANG2.get(j.get("language_code", "")),
            provider="elevenlabs",
            latency_ms=(time.perf_counter() - t0) * 1000,
            confidence=j.get("language_probability"),
        )
    

class WhisperSTT:
    """faster-whisper. Для казахского качество заметно ниже, чем для русского —
    используйте как fallback и подсказывайте названия меню через initial_prompt."""

    def __init__(self, model_size: str = "large-v3", device: str = "auto", compute_type: str = "int8"):
        self.model_size, self.device, self.compute_type = model_size, device, compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    def transcribe(self, audio, filename="audio.webm", mime="audio/webm", language=None, hints=None):
        model = self._load()
        t0 = time.perf_counter()
        prompt = ("Заказ в ресторане. Меню: " + ", ".join(hints) + ".") if hints else None

        def run(lang):
            segs, info = model.transcribe(io.BytesIO(audio), language=lang, initial_prompt=prompt,
                                          vad_filter=True, beam_size=5, temperature=0.0)
            return " ".join(s.text.strip() for s in segs).strip(), info

        text, info = run(language if language in ("ru", "kk") else None)
        if language is None and info.language not in ("ru", "kk"):   # ограничиваем набор ru/kk
            probs = dict(getattr(info, "all_language_probs", None) or [])
            lang = "kk" if probs.get("kk", 0) > probs.get("ru", 0) else "ru"
            text, info = run(lang)
        return STTResult(text=text, language=LANG2.get(info.language), provider="whisper",
                         latency_ms=(time.perf_counter() - t0) * 1000,
                         confidence=getattr(info, "language_probability", None))


class FallbackSTT:
    """Пробует провайдеров по очереди (ElevenLabs -> Whisper)."""

    def __init__(self, *providers: STTProvider):
        self.providers = providers

    def transcribe(self, *a, **kw):
        err = None
        for p in self.providers:
            try:
                return p.transcribe(*a, **kw)
            except Exception as e:          # сеть, 5xx, лимиты
                err = e
        raise RuntimeError(f"all STT providers failed: {err}")


def _main() -> int:
    """Transcribe one local audio file from the command line."""
    import argparse
    import mimetypes
    from pathlib import Path

    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        pass
    else:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Transcribe an audio file with ElevenLabs Scribe.")
    parser.add_argument("audio", type=Path, help="Path to an MP3, WAV, M4A, WebM, or other audio file")
    parser.add_argument("--language", "--lang", choices=("ru", "kk"), help="Optional language hint")
    parser.add_argument("--model-id", help="ElevenLabs model ID (default: scribe_v2)")
    args = parser.parse_args()

    if not args.audio.is_file():
        parser.error(f"audio file not found: {args.audio}")
    if not os.getenv("ELEVENLABS_API_KEY"):
        parser.error("ELEVENLABS_API_KEY is not set (set it in PowerShell or in a project .env file)")

    mime = mimetypes.guess_type(args.audio.name)[0] or "application/octet-stream"
    try:
        result = ElevenLabsSTT(model_id=args.model_id).transcribe(
            args.audio.read_bytes(),
            filename=args.audio.name,
            mime=mime,
            language=args.language,
        )
    except Exception as exc:
        print(f"Transcription failed: {exc}")
        return 1

    print(f"Transcript: {result.text}")
    print(f"Language: {result.language or 'unknown'}")
    print(f"Provider: {result.provider}")
    print(f"Latency: {result.latency_ms:.0f} ms")
    if result.confidence is not None:
        print(f"Language confidence: {result.confidence:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
