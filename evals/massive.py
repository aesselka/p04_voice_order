"""Внешняя проверка на реальных русских фразах Amazon MASSIVE (ru-RU, CC BY 4.0).

    python -m evals.massive

- takeaway_order (177): гость хочет заказать -> интент add, а блюда не из нашего меню не выдумываются.
- takeaway_query (181): вопросы («сколько стоит», «где заказать») -> корзина НЕ должна меняться.

Источник: FitzGerald et al., 2022, "MASSIVE: A 1M-Example Multilingual Natural Language Understanding
Dataset with 51 Typologically-Diverse Languages", https://github.com/alexa/massive
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from voice_cart_nlu.cart import CartSession
from voice_cart_nlu.menu import Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def load(intent: str) -> list[dict]:
    return [json.loads(l) for l in (DATA / f"{intent}.jsonl").open(encoding="utf-8")]


def food_slots(row: dict) -> list[str]:
    return [v.strip() for k, v in re.findall(r"\[(\w+) : ([^\]]+)\]", row["annot_utt"]) if k == "food_type"]


def run(pipe: VoiceCommandPipeline, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        s = CartSession(pipe.menu)
        res = pipe.parse_text(r["utt"], s.context())
        s.handle(res.commands)
        out.append({"utt": r["utt"], "food": food_slots(r), "intents": [c.intent.value for c in res.commands],
                    "added": [l.item_id for l in s.lines]})
    return out


def main() -> int:
    pipe = VoiceCommandPipeline(Menu.load())
    orders, queries = run(pipe, load("takeaway_order")), run(pipe, load("takeaway_query"))

    as_add = sum("add" in o["intents"] for o in orders)
    mutated_q = [q for q in queries if q["added"]]
    added = Counter(i for o in orders for i in o["added"])
    # «пицца/суши/китайская» нет в меню — если что-то добавилось, смотрим глазами, не выдумка ли это
    suspicious = [o for o in orders if o["added"] and o["food"]]

    lines = [
        "# Eval: Amazon MASSIVE ru-RU (takeaway)", "",
        "| Метрика | Значение |", "|---|---|",
        f"| Заказы распознаны как add | {100 * as_add / len(orders):.1f}% ({as_add}/{len(orders)}) |",
        f"| Заказы, после которых корзина не пуста | {sum(bool(o['added']) for o in orders)}/{len(orders)} |",
        f"| **Ложные изменения корзины на вопросах** | **{100 * len(mutated_q) / len(queries):.1f}% "
        f"({len(mutated_q)}/{len(queries)})** |", "",
        "Большинство блюд в MASSIVE (пицца, суши, китайская кухня) отсутствуют в нашем меню, поэтому",
        "пустая корзина после заказа — ожидаемо. Главное: ничего не выдумано и вопросы не меняют корзину.", "",
        "## Что добавлялось из заказов", "",
        "| Блюдо | Раз |", "|---|---|", *[f"| {k} | {v} |" for k, v in added.most_common()], "",
        "## Проверить глазами: добавлено блюдо при food_type из MASSIVE", "",
        *[f"- «{o['utt']}» (food_type: {', '.join(o['food'])}) → {o['added']}" for o in suspicious], "",
        "## Вопросы, которые изменили корзину (ошибки)", "",
        *[f"- «{q['utt']}» → {q['added']}" for q in mutated_q],
    ]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "massive.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MASSIVE: add {as_add}/{len(orders)}, ложные изменения на вопросах {len(mutated_q)}/{len(queries)} "
          f"-> evals/reports/massive.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
