"""STT-eval: записи -> распознавание -> WER по языкам -> те же диалоги, но из распознанного текста.

    python -m voice_eval.stt_eval --speaker nurasyl --provider elevenlabs
    python -m voice_eval.stt_eval --speaker nurasyl --provider whisper      # pip install faster-whisper
    python -m voice_eval.stt_eval --speaker tts_milena --provider elevenlabs

Пишет evals/reports/stt_<speaker>_<provider>.md и прогоняет evals.run по диалогам,
у которых записаны ВСЕ реплики (отчёт voice_<speaker>_<provider>.md).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from evals.run import REPORTS, load_dialogs
from evals.run import main as run_eval

REC = Path(__file__).resolve().parent / "recordings"
MIME = {".webm": "audio/webm", ".mp4": "audio/mp4", ".wav": "audio/wav", ".m4a": "audio/mp4"}


def words(s: str) -> list[str]:
    s = s.lower().replace("ё", "е")
    return re.findall(r"[\w]+", s)


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def make_provider(name: str):
    from voice_cart_nlu.stt import ElevenLabsSTT, WhisperSTT
    if name == "elevenlabs":
        return ElevenLabsSTT()
    if name == "whisper":
        import os
        return WhisperSTT(os.getenv("WHISPER_MODEL", "small"))
    raise SystemExit(f"неизвестный provider: {name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", required=True, help="папка в voice_eval/recordings")
    ap.add_argument("--provider", default="elevenlabs", choices=["elevenlabs", "whisper"])
    ap.add_argument("--lang-hint", action="store_true", help="передавать язык реплики в STT (ru/kk)")
    ap.add_argument("--no-hints", action="store_true", help="не передавать названия блюд как подсказку STT")
    args = ap.parse_args(argv)
    load_dotenv()

    folder = REC / args.speaker
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    stt = make_provider(args.provider)
    from voice_cart_nlu.menu import Menu
    hints = None if args.no_hints else [i.name for i in Menu.load().items]

    rows = []
    for key, e in sorted(manifest.items()):
        audio = (folder / e["file"]).read_bytes()
        hint = e["lang"] if args.lang_hint and e["lang"] in ("ru", "kk") else None
        t = time.perf_counter()
        try:
            r = stt.transcribe(audio, filename=e["file"], mime=MIME.get(Path(e["file"]).suffix, "audio/webm"),
                               language=hint, hints=hints)
            hyp, err = r.text, None
        except Exception as exc:                     # сеть / лимиты — фиксируем и идём дальше
            hyp, err = "", str(exc)[:120]
        ms = (time.perf_counter() - t) * 1000
        ref_w, hyp_w = words(e["text"]), words(hyp)
        rows.append({"key": key, "lang": e["lang"], "ref": e["text"], "hyp": hyp, "error": err, "ms": ms,
                     "errors": edit_distance(ref_w, hyp_w), "n": len(ref_w)})
        print(f"{key:40s} {e['lang']:5s} {ms:7.0f} мс  «{hyp}»", file=sys.stderr)

    by_lang = defaultdict(lambda: [0, 0, []])
    for r in rows:
        for k in (r["lang"], "all"):
            by_lang[k][0] += r["errors"]
            by_lang[k][1] += r["n"]
            by_lang[k][2].append(r["ms"])
    import os
    model = os.getenv("WHISPER_MODEL", "small") if args.provider == "whisper" else \
        os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
    name = f"{args.speaker}_{args.provider}-{model}" + ("_langhint" if args.lang_hint else "") + ("_nohints" if args.no_hints else "")
    md = [f"# STT: {args.provider} ({model}{', язык подсказан' if args.lang_hint else ''}{', без подсказок меню' if args.no_hints else ''}), диктор {args.speaker}", "",
          "| Язык | WER | Реплик | Задержка STT p50 |", "|---|---|---|---|"]
    for lang in ("ru", "kk", "mixed", "all"):
        if lang in by_lang:
            e, n, ms = by_lang[lang]
            md.append(f"| {lang} | {100 * e / max(n, 1):.1f}% | {len(ms)} | {statistics.median(ms):.0f} мс |")
    md += ["", "WER = (замены + вставки + удаления слов) / слов в эталоне.", "",
           "## Худшие реплики", "", "| Эталон | Распознано | Ошибок |", "|---|---|---|"]
    for r in sorted(rows, key=lambda r: -r["errors"] / max(r["n"], 1))[:15]:
        md.append(f"| {r['ref']} | {r['hyp'] or '(' + (r['error'] or 'пусто') + ')'} | {r['errors']}/{r['n']} |")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"stt_{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # диалоги, у которых записаны все реплики -> транскрипты -> eval корзины по голосу
    hyp_by = {r["key"]: r["hyp"] for r in rows}
    transcripts = {}
    for d in load_dialogs():
        keys = [f"{d['id']}__{i}" for i in range(len(d["turns"]))]
        if all(k in hyp_by for k in keys):
            transcripts[d["id"]] = [hyp_by[k] for k in keys]
    tr_file = REPORTS / f"transcripts_{name}.json"
    tr_file.write_text(json.dumps(transcripts, ensure_ascii=False, indent=1), encoding="utf-8")
    e, n, _ = by_lang["all"]
    print(f"WER {100 * e / max(n, 1):.1f}% -> evals/reports/stt_{name}.md; полных диалогов: {len(transcripts)}")
    if transcripts:
        run_eval(["--transcripts", str(tr_file), "--name", f"voice_{name}"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
