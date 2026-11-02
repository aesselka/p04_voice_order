"""Eval: эталонные диалоги -> pipeline -> корзина -> таблица метрик.

    python -m evals.run                         # только rules, без ключей
    python -m evals.run --llm                   # + LLM-fallback (нужен ANTHROPIC_API_KEY)
    python -m evals.run --transcripts evals/reports/voice_elevenlabs.json   # реплики из STT вместо текста
    python -m evals.run --gate                  # exit 1, если есть ошибки цены или точность ниже порога

Пишет evals/reports/<name>.md и <name>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

from voice_cart_nlu.cart import CartSession
from voice_cart_nlu.menu import Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline

from .oracle import PriceOracle

ROOT = Path(__file__).resolve().parent
DIALOGS = ROOT / "dialogs.yaml"
REPORTS = ROOT / "reports"


def load_dialogs(path: Path = DIALOGS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def norm_expected(lines: list[dict], oracle: PriceOracle) -> list[tuple]:
    out = []
    for l in lines:
        item = oracle.items[l["item"]]
        size = l.get("size") or (item.get("default_size") or "M" if item.get("sizes") else None)
        out.append((l["item"], l.get("qty", 1), size, tuple(sorted((l.get("mods") or {}).items())),
                    tuple(sorted((l.get("choices") or {}).items()))))
    return sorted(out)


def norm_actual(s: CartSession) -> list[tuple]:
    return sorted((l.item_id, l.quantity, l.size.value if l.size else None,
                   tuple(sorted((m.modifier_id, m.op) for m in l.modifiers)),
                   tuple(sorted(l.choices.items()))) for l in s.lines)


def oracle_total(s: CartSession, oracle: PriceOracle) -> int:
    return oracle.total([{"item": l.item_id, "qty": l.quantity, "size": l.size.value if l.size else None,
                          "mods": {m.modifier_id: m.op for m in l.modifiers}, "choices": l.choices}
                         for l in s.lines])


def run_dialog(d: dict, pipe: VoiceCommandPipeline, oracle: PriceOracle,
               transcripts: dict[str, list[str]] | None = None) -> dict:
    s = CartSession(pipe.menu)
    turns = (transcripts or {}).get(d["id"], d["turns"])
    asked, price_errors, latencies, log = 0, 0, [], []
    for text in turns:
        t = time.perf_counter()
        res = pipe.parse_text(text, s.context())
        reply = s.handle(res.commands)
        latencies.append((time.perf_counter() - t) * 1000)
        if reply.question:
            asked += 1
        if reply.cart.total_cents != oracle_total(s, oracle):
            price_errors += 1
        log.append({"user": text, "intents": [c.intent.value for c in res.commands],
                    "source": [c.source for c in res.commands], "question": reply.question,
                    "notes": reply.notes, "total_cents": reply.cart.total_cents})
    exp = d["expect"]
    want, got = norm_expected(exp.get("cart", []), oracle), norm_actual(s)
    status_ok = s.status == exp.get("status", "open")
    cart_ok = want == got
    if cart_ok and s.view().total_cents != oracle.total(exp.get("cart", [])):
        price_errors += 1
    need = exp.get("questions")
    return {"id": d["id"], "tags": d.get("tags", []), "ok": cart_ok and status_ok, "cart_ok": cart_ok,
            "status_ok": status_ok, "price_errors": price_errors, "asked": asked, "need": need,
            "extra_questions": max(0, asked - need) if need is not None else 0,
            "missed_questions": max(0, need - asked) if need is not None else 0,
            "latency_ms": latencies, "want": want, "got": got, "status": s.status, "log": log}


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "—"


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def summarize(results: list[dict]) -> dict:
    lat = [x for r in results for x in r["latency_ms"]]
    edits = [r for r in results if {"remove", "modify"} & set(r["tags"])]
    by_tag = defaultdict(list)
    for r in results:
        for t in r["tags"]:
            by_tag[t].append(r["ok"])
    return {
        "dialogs": len(results),
        "turns": len(lat),
        "cart_accuracy": sum(r["ok"] for r in results) / len(results),
        "ok": sum(r["ok"] for r in results),
        "edit_ok": sum(r["ok"] for r in edits), "edit_total": len(edits),
        "price_errors": sum(r["price_errors"] for r in results),
        "extra_questions": sum(r["extra_questions"] for r in results),
        "missed_questions": sum(r["missed_questions"] for r in results),
        "latency_p50_ms": percentile(lat, 50), "latency_p95_ms": percentile(lat, 95),
        "by_tag": {t: (sum(v), len(v)) for t, v in sorted(by_tag.items())},
    }


def render(summary: dict, results: list[dict], title: str) -> str:
    s = summary
    out = [f"# {title}", "",
           "| Метрика | Значение |", "|---|---|",
           f"| Точность итоговой корзины | {pct(s['ok'], s['dialogs'])} |",
           f"| Точность удалений и изменений | {pct(s['edit_ok'], s['edit_total'])} |",
           f"| **Ошибки итоговой стоимости** | **{s['price_errors']}** |",
           f"| Лишние уточнения (всего) | {s['extra_questions']} |",
           f"| Пропущенные уточнения | {s['missed_questions']} |",
           f"| Задержка NLU+корзина p50 / p95 | {s['latency_p50_ms']:.2f} / {s['latency_p95_ms']:.2f} мс |",
           f"| Диалогов / реплик | {s['dialogs']} / {s['turns']} |", "",
           "## По тегам", "", "| Тег | Точность |", "|---|---|"]
    out += [f"| {t} | {pct(ok, n)} |" for t, (ok, n) in s["by_tag"].items()]
    fails = [r for r in results if not r["ok"] or r["extra_questions"] or r["missed_questions"]]
    if fails:
        out += ["", "## Ошибки", ""]
        for r in fails:
            why = []
            if not r["cart_ok"]:
                why.append(f"корзина: ждали `{r['want']}`, получили `{r['got']}`")
            if not r["status_ok"]:
                why.append(f"статус: `{r['status']}`")
            if r["extra_questions"] or r["missed_questions"]:
                why.append(f"уточнений: нужно {r['need']}, задано {r['asked']}")
            out.append(f"- **{r['id']}** ({', '.join(r['tags'])}): " + "; ".join(why))
            for turn in r["log"]:
                q = f" → «{turn['question']}»" if turn["question"] else ""
                n = f" [{'; '.join(turn['notes'])}]" if turn["notes"] else ""
                out.append(f"    - «{turn['user']}» → {turn['intents']}{q}{n}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="включить LLM-fallback (ANTHROPIC_API_KEY)")
    ap.add_argument("--transcripts", type=Path, help="json {dialog_id: [реплика, ...]} из STT")
    ap.add_argument("--name", default=None, help="имя отчёта")
    ap.add_argument("--gate", action="store_true", help="exit 1 при ошибках цены / низкой точности")
    ap.add_argument("--min-accuracy", type=float, default=0.8)
    args = ap.parse_args(argv)

    llm = None
    if args.llm:
        from dotenv import load_dotenv
        from voice_cart_nlu.llm_parser import AnthropicJSONClient
        load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("--llm: нет ANTHROPIC_API_KEY", file=sys.stderr)
            return 2
        llm = AnthropicJSONClient()
    pipe = VoiceCommandPipeline(Menu.load(), llm=llm)
    oracle = PriceOracle()
    transcripts = json.loads(args.transcripts.read_text(encoding="utf-8")) if args.transcripts else None
    dialogs = load_dialogs()
    if transcripts:
        dialogs = [d for d in dialogs if d["id"] in transcripts]

    results = [run_dialog(d, pipe, oracle, transcripts) for d in dialogs]
    summary = summarize(results)
    name = args.name or ("voice_" + args.transcripts.stem if args.transcripts else ("llm" if llm else "rules"))
    title = f"Eval: {name}"
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{name}.md").write_text(render(summary, results, title), encoding="utf-8")
    (REPORTS / f"{name}.json").write_text(json.dumps({"summary": summary, "results": results},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    s = summary
    print(f"{title}: корзина {pct(s['ok'], s['dialogs'])}, правки {pct(s['edit_ok'], s['edit_total'])}, "
          f"ошибки цены {s['price_errors']}, лишних уточнений {s['extra_questions']}, "
          f"p95 {s['latency_p95_ms']:.2f} мс -> evals/reports/{name}.md")
    if args.gate and (s["price_errors"] > 0 or s["cart_accuracy"] < args.min_accuracy):
        print(f"GATE FAILED: price_errors={s['price_errors']}, accuracy={s['cart_accuracy']:.2f} "
              f"< {args.min_accuracy}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
