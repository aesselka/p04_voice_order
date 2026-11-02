"""Синтетические записи через macOS `say` (голос Milena) — быстрый STT-eval без микрофона.

    python -m voice_eval.tts            -> voice_eval/recordings/tts_milena/

Только ru: казахского голоса в macOS нет. Синтез чище живой речи, поэтому WER на нём
оптимистичнее — в отчёте сравнивайте с живыми записями.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from evals.run import load_dialogs

from .recorder import REC, lang_of


def main() -> int:
    if not shutil.which("say"):
        print("нужен macOS (команда say)", file=sys.stderr)
        return 2
    folder = REC / "tts_milena"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for d in load_dialogs():
        if lang_of(d) != "ru":
            continue
        for i, text in enumerate(d["turns"]):
            key = f"{d['id']}__{i}"
            out = folder / f"{key}.wav"
            if not out.exists() or out.stat().st_size == 0:
                for _ in range(3):                   # say иногда подвисает — перезапускаем
                    try:
                        subprocess.run(["say", "-v", "Milena", "-o", str(out), "--data-format=LEI16@16000", text],
                                       check=True, timeout=30)
                        break
                    except subprocess.TimeoutExpired:
                        out.unlink(missing_ok=True)
                else:
                    print(f"пропущено (say завис): {key}", file=sys.stderr)
                    continue
            manifest[key] = {"file": out.name, "text": text, "lang": "ru", "mime": "audio/wav"}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(manifest)} записей -> {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
