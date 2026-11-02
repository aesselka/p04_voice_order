"""Студия записи: читаешь реплики эталонных диалогов вслух, они сохраняются как аудио для STT-eval.

    python -m voice_eval.recorder            ->  http://127.0.0.1:8765

Записи: voice_eval/recordings/<speaker>/<dialog_id>__<turn>.webm (+ manifest.json).
Реплики берутся из evals/dialogs.yaml, так что голос проверяется на тех же диалогах, что и текст.
"""
from __future__ import annotations

import json
import re
import sys
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from evals.run import load_dialogs

ROOT = Path(__file__).resolve().parent
REC = ROOT / "recordings"
PAGE = ROOT / "static" / "recorder.html"
SAFE = re.compile(r"^[\w-]{1,40}$")

app = FastAPI(title="Voice eval recorder")


def lang_of(d: dict) -> str:
    tags = d.get("tags", [])
    return "kk" if "kk" in tags else "mixed" if "mixed" in tags else "ru"


def prompts() -> list[dict]:
    return [{"dialog_id": d["id"], "turn": i, "text": t, "lang": lang_of(d), "n_turns": len(d["turns"])}
            for d in load_dialogs() for i, t in enumerate(d["turns"])]


def check(*parts: str) -> None:
    if not all(SAFE.match(p) for p in parts):
        raise HTTPException(400, "bad name")


def manifest(speaker: str) -> dict:
    f = REC / speaker / "manifest.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


@app.get("/", include_in_schema=False)
def page():
    return FileResponse(PAGE)


@app.get("/api/prompts")
def api_prompts(speaker: str):
    check(speaker)
    done = manifest(speaker)
    return [{**p, "recorded": f"{p['dialog_id']}__{p['turn']}" in done} for p in prompts()]


@app.post("/api/record/{speaker}/{dialog_id}/{turn}")
def api_record(speaker: str, dialog_id: str, turn: int, audio: UploadFile = File(...)):
    check(speaker, dialog_id)
    p = next((p for p in prompts() if p["dialog_id"] == dialog_id and p["turn"] == turn), None)
    if not p:
        raise HTTPException(404, "no such prompt")
    folder = REC / speaker
    folder.mkdir(parents=True, exist_ok=True)
    key = f"{dialog_id}__{turn}"
    ext = ".mp4" if "mp4" in (audio.content_type or "") else ".webm"
    (folder / f"{key}{ext}").write_bytes(audio.file.read())
    m = manifest(speaker)
    m[key] = {"file": f"{key}{ext}", "text": p["text"], "lang": p["lang"], "mime": audio.content_type}
    (folder / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"saved": key, "total": len(m)}


@app.get("/api/audio/{speaker}/{dialog_id}/{turn}")
def api_audio(speaker: str, dialog_id: str, turn: int):
    check(speaker, dialog_id)
    entry = manifest(speaker).get(f"{dialog_id}__{turn}")
    if not entry:
        raise HTTPException(404)
    return FileResponse(REC / speaker / entry["file"])


def main() -> int:
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    webbrowser.open(f"http://127.0.0.1:{port}/")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
