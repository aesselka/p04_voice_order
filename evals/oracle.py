"""Независимый пересчёт цены прямо из menu.json — без кода voice_cart_nlu.

Им пользуются property-тесты и eval: если cart.py посчитает иначе, это ошибка цены.
"""
from __future__ import annotations

import json
from pathlib import Path

MENU_JSON = Path(__file__).resolve().parent.parent / "voice_cart_nlu" / "data" / "menu.json"


class PriceOracle:
    def __init__(self, path: Path = MENU_JSON):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.items = {i["id"]: i for i in raw["items"]}
        self.mods = {m["id"]: m for m in raw["modifiers"]}

    def unit(self, item_id: str, size: str | None = None, mods: dict[str, str] | None = None,
             choices: dict[str, str] | None = None) -> int:
        item = self.items[item_id]
        if size:
            base = item.get("size_prices_cents", {}).get(size, item["price_cents"])
        elif item.get("sizes"):
            base = item["size_prices_cents"][item.get("default_size") or "M"]
        else:
            base = item["price_cents"]
        extra = sum(self.mods[m]["price_cents"] for m, op in (mods or {}).items() if op == "add")
        deltas = sum(c.get("price_delta_cents", {}).get((choices or {})[c["id"]], 0)
                     for c in item.get("choices", []) if c["id"] in (choices or {}))
        return base + extra + deltas

    def is_pending(self, item_id: str, choices: dict[str, str] | None) -> bool:
        return any(c["id"] not in (choices or {}) for c in self.items[item_id].get("choices", []))

    def total(self, lines: list[dict]) -> int:
        """lines: [{item, qty, size?, mods?, choices?}] — формат эталонных диалогов."""
        return sum(self.unit(l["item"], l.get("size"), l.get("mods"), l.get("choices")) * l.get("qty", 1)
                   for l in lines if not self.is_pending(l["item"], l.get("choices")))
