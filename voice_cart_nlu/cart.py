"""Cart State Machine: применяет Action к корзине.

Здесь то, что NLU не делает: проверка блюд, размеров, добавок и выборов комбо по меню,
разрешение ссылок на строки («второе», «последнее», неявная), цены — только целыми
тиынами (1/100 ₸) из menu.json, без float и без LLM.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .actions import Action, to_actions
from .menu import ComboChoice, Menu, MenuItem
from .schemas import CartContext, CartLineView, Command, Intent, LineRef, ModifierOp, Size
from .upsell import UpsellRule, UpsellView, pick_offer

SIZE_LABEL = {"S": "маленький", "M": "средний", "L": "большой"}
_MUTATING = {"add_item", "remove_item", "change_quantity", "change_size",
             "add_modifier", "remove_modifier", "set_combo_choice"}
# ответ "нет" на допродажу
_NO_RE = re.compile(r"^(нет|не надо|не нужно|не хочу|нет спасибо|спасибо нет|не|жоқ|керек емес|рахмет жоқ)[.!]?$")


class CartLine(BaseModel):
    item_id: str
    quantity: int = 1
    size: Optional[Size] = None
    modifiers: list[ModifierOp] = Field(default_factory=list)
    choices: dict[str, str] = Field(default_factory=dict)       # комбо: drink -> cola, size -> L


# ---------------------------------------------------------------- ответ для UI/API
class ModifierView(BaseModel):
    id: str
    name: str
    op: Literal["add", "remove"]
    price_cents: int


class ChoiceView(BaseModel):
    id: str
    label: str
    value: str
    name: str
    price_delta_cents: int


class LineView(BaseModel):
    line: int                                   # номер строки, с 1
    item_id: str
    name: str
    quantity: int
    size: Optional[Size]
    modifiers: list[ModifierView]
    choices: list[ChoiceView]
    missing: list[str]                          # невыбранные обязательные выборы комбо
    pending: bool
    unit_price_cents: int
    line_total_cents: int


class CartView(BaseModel):
    lines: list[LineView]
    status: Literal["open", "confirmed", "cancelled"]
    total_cents: int                            # без строк, ожидающих выбора
    has_pending: bool


class Reply(BaseModel):
    actions: list[Action]
    notes: list[str]                            # отказы и предупреждения
    question: Optional[str]                     # ОДИН короткий уточняющий вопрос гостю
    cart: CartView
    upsell: Optional[UpsellView] = None         # допродажа


# ---------------------------------------------------------------- цены
def unit_price_cents(line: CartLine, menu: Menu) -> int:
    item = menu.item(line.item_id)
    base = item.size_prices_cents.get(line.size, item.price_cents) if line.size else item.price_cents
    mods = sum(menu.modifier(m.modifier_id).price_cents for m in line.modifiers if m.op == "add")
    deltas = sum(ch.price_delta_cents.get(line.choices[ch.id], 0) for ch in item.choices if ch.id in line.choices)
    return base + mods + deltas


def money(cents: int) -> str:
    sign, cents = ("−" if cents < 0 else ""), abs(cents)
    whole = f"{cents // 100:,}".replace(",", " ")
    return f"{sign}{whole}{f',{cents % 100:02d}' if cents % 100 else ''} ₸"


def _same(a: CartLine, b: CartLine) -> bool:
    key = lambda l: (l.item_id, l.size, frozenset((m.modifier_id, m.op) for m in l.modifiers),
                     tuple(sorted(l.choices.items())))
    return key(a) == key(b)


class CartSession:
    """Корзина одного гостя."""

    def __init__(self, menu: Menu, upsell_rules: Optional[list[UpsellRule]] = None):
        self.menu = menu
        self.upsell_rules = upsell_rules or []
        self.lines: list[CartLine] = []
        self.status: Literal["open", "confirmed", "cancelled"] = "open"
        self._last: Optional[CartLine] = None       # строка, с которой гость работал последней
        self.offered: set[str] = set()              # что уже предлагали в этом заказе
        self.upsell_offer: Optional[str] = None     # ждем "да" или "нет"

    # ------------------------------------------------------------ вход
    def handle(self, cmds: list[Command], text: str = "") -> Reply:
        # text нужен, чтобы понять "нет" на допродажу
        offer, self.upsell_offer = self.upsell_offer, None
        if offer:
            if len(cmds) == 1 and cmds[0].intent == Intent.confirm:     # "да" на допродажу
                return self.apply([Action(type="add_item", item_id=offer)])
            if _NO_RE.match(text.strip().lower()):                      # "нет" - ничего не меняем
                return Reply(actions=[], notes=[], question=None, cart=self.view())
        actions, notes = to_actions(cmds, self.menu, self.pending_state())
        reply = self.apply(actions)
        reply.notes = notes + reply.notes
        return reply

    def apply(self, actions: list[Action]) -> Reply:
        self.upsell_offer = None
        self._notes: list[str] = []
        self._asks: list[str] = []
        self._removed: Optional[tuple[int, CartLine]] = None
        self._added = False
        for a in actions:
            if a.type in _MUTATING and self.status != "open":
                self.status = "open"                 # после confirm/clear гость продолжает заказ
            getattr(self, f"_{a.type}")(a)
        question = self._asks[0] if self._asks else self._combo_question()
        upsell = None
        if self._added and question is None and self.status == "open":
            upsell = pick_offer(self.upsell_rules, self.menu, [l.item_id for l in self.lines], self.offered)
            if upsell:
                self.offered.add(upsell.item_id)
                self.upsell_offer = upsell.item_id
        return Reply(actions=actions, notes=self._notes + self._asks[1:], question=question, cart=self.view(),
                     upsell=upsell)

    # хранение в sqlite
    def to_state(self) -> dict:
        last = next((i for i, l in enumerate(self.lines) if l is self._last), None)
        return {"lines": [l.model_dump(mode="json") for l in self.lines], "status": self.status, "last": last,
                "offered": sorted(self.offered), "upsell_offer": self.upsell_offer}

    @classmethod
    def from_state(cls, menu: Menu, state: dict, upsell_rules: Optional[list[UpsellRule]] = None) -> "CartSession":
        s = cls(menu, upsell_rules)
        s.lines = [CartLine.model_validate(l) for l in state.get("lines", [])]
        s.status = state.get("status", "open")
        last = state.get("last")
        s._last = s.lines[last] if last is not None and last < len(s.lines) else None
        s.offered = set(state.get("offered", []))
        s.upsell_offer = state.get("upsell_offer")
        return s

    def context(self) -> CartContext:
        return CartContext(lines=[CartLineView(index=i, menu_item_id=l.item_id, quantity=l.quantity, size=l.size)
                                  for i, l in enumerate(self.lines, 1)])

    # ------------------------------------------------------------ комбо
    def missing(self, line: CartLine) -> list[ComboChoice]:
        return [c for c in self.menu.item(line.item_id).choices if c.id not in line.choices]

    def pending_line(self) -> Optional[CartLine]:
        return next((l for l in self.lines if self.missing(l)), None)

    def pending_state(self) -> Optional[tuple[list[ComboChoice], dict[str, str]]]:
        line = self.pending_line()
        return (self.menu.item(line.item_id).choices, dict(line.choices)) if line else None

    def _combo_question(self) -> Optional[str]:
        line = self.pending_line()
        return self._ask_text(self.missing(line)[0]) if line else None

    def _ask_text(self, ch: ComboChoice, options: Optional[list[str]] = None) -> str:
        options = [o for o in options or ch.options
                   if ch.kind != "item" or (self.menu.item(o) and self.menu.item(o).available)] or ch.options
        return f"{ch.question}: {self._or([self._label(ch, o) for o in options])}?"

    # ------------------------------------------------------------ действия
    def _add_item(self, a: Action) -> None:
        if not a.item_id:
            if a.candidates:
                self._asks.append(f"Уточните, какой: {self._or([self._name(i) for i in a.candidates])}?")
            return
        item = self.menu.item(a.item_id)
        if not item:
            self._notes.append(f"Такого нет в меню: «{a.raw or a.item_id}»")
            return
        if not item.available:
            self._notes.append(f"Извините, «{item.name}» сейчас нет в наличии")
            return
        self._added = True
        line = CartLine(item_id=item.id, quantity=a.quantity or 1)
        old = self._removed[1] if a.replaces and self._removed else None
        if old:                                      # «замени колу на спрайт»: кол-во/размер/добавки от старой
            line.quantity = a.quantity or old.quantity
            line.size = old.size if old.size in item.sizes else None
            line.modifiers = [m for m in old.modifiers if m.modifier_id in item.modifiers]
        if a.size:
            self._set_size(line, item, a.size)
        elif not line.size and item.sizes:
            line.size = item.default_size
        for op in a.modifiers:
            self._set_mod(line, item, op.modifier_id, op.op)
        for cid, value in a.choices.items():
            self._set_choice(line, item, cid, value)
        if old:
            self.lines.insert(self._removed[0], line)
        else:
            same = next((l for l in self.lines if _same(l, line)), None)
            if same:
                same.quantity += line.quantity
                line = same
            else:
                self.lines.append(line)
        self._last = line

    def _remove_item(self, a: Action) -> None:
        line = self._resolve(a.target)
        if not line:
            return
        if a.quantity and a.quantity < line.quantity:
            line.quantity -= a.quantity
            self._last = line
            return
        i = self._index(line)
        self.lines.pop(i)
        self._removed = (i, line)
        # «убери второй кофе» -> «сделай его большим» относится к оставшемуся кофе
        rest = [l for l in self.lines if l.item_id == line.item_id]
        if rest:
            self._last = rest[-1]
        elif self._last is line:
            self._last = None

    def _change_quantity(self, a: Action) -> None:
        if not a.quantity:                           # неполное действие от кнопки
            self._notes.append("Не понял, сколько штук")
            return
        line = self._resolve(a.target)
        if line:
            line.quantity = a.quantity
            self._last = line

    def _change_size(self, a: Action) -> None:
        if a.size is None:
            self._notes.append("Не понял, какой размер")
            return
        line = self._resolve(a.target)
        if not line:
            return
        item = self.menu.item(line.item_id)
        if item.choice("size"):                      # размер комбо — это выбор комбо
            self._set_choice(line, item, "size", a.size.value)
        else:
            self._set_size(line, item, a.size)
        self._last = line

    def _add_modifier(self, a: Action) -> None:
        self._modifier(a, "add")

    def _remove_modifier(self, a: Action) -> None:
        self._modifier(a, "remove")

    def _modifier(self, a: Action, op: str) -> None:
        line = self._resolve(a.target)
        if line:
            self._set_mod(line, self.menu.item(line.item_id), a.modifier_id, op)
            self._last = line

    def _set_combo_choice(self, a: Action) -> None:
        line = self._resolve(a.target) if a.target else self.pending_line()
        if not line or not self.menu.item(line.item_id).choices:
            self._notes.append("Нет комбо, к которому это относится")
            return
        item = self.menu.item(line.item_id)
        ch = item.choice(a.choice_id)
        if ch and a.candidates:                      # «сок» — какой именно из вариантов комбо
            self._asks.append(self._ask_text(ch, [c for c in a.candidates if c in ch.options]))
            return
        self._set_choice(line, item, a.choice_id, a.value, a.raw)
        self._last = line

    def _clear_cart(self, a: Action) -> None:
        self.lines, self.status, self._last = [], "cancelled", None
        self._notes.append("Корзина очищена")

    def _confirm(self, a: Action) -> None:
        gone = [self.menu.item(l.item_id).name for l in self.lines if not self.menu.item(l.item_id).available]
        if not self.lines:
            self._notes.append("Корзина пуста, нечего подтверждать")
        elif gone:                                   # блюдо закончилось, пока гость думал
            self._notes.append(f"Закончилось: {', '.join(gone)}. Уберите из заказа или замените")
        elif self.pending_line():
            self._notes.append("Сначала завершите выбор в комбо")
        else:
            self.status = "confirmed"
            self._notes.append("Заказ подтверждён")

    # ------------------------------------------------------------ проверки по меню
    def _set_size(self, line: CartLine, item: MenuItem, size: Size) -> None:
        if size in item.sizes:
            line.size = size
        else:
            self._notes.append(f"У «{item.name}» нет размеров" if not item.sizes
                               else f"У «{item.name}» нет размера {size.value}")

    def _set_mod(self, line: CartLine, item: MenuItem, mod_id: str, op: str) -> None:
        mod = self.menu.modifier(mod_id)
        if not mod:
            self._notes.append("Такой добавки нет в меню")
            return
        if mod_id not in item.modifiers:
            self._notes.append(f"Для «{item.name}» нельзя: {mod.name.lower()}")
            return
        cur = next((m for m in line.modifiers if m.modifier_id == mod_id), None)
        if cur and cur.op != op:                     # «добавь сыр», потом «убери сыр» -> как было
            line.modifiers.remove(cur)
        elif not cur:
            line.modifiers.append(ModifierOp(modifier_id=mod_id, op=op))

    def _set_choice(self, line: CartLine, item: MenuItem, cid: str, value: Optional[str],
                    raw: str = "") -> None:
        ch = item.choice(cid)
        if not ch:
            self._notes.append(f"В «{item.name}» нечего выбирать")
            return
        if value in ch.options and ch.kind == "item" and not self.menu.item(value).available:
            self._notes.append(f"Извините, «{self._name(value)}» сейчас нет в наличии")
            self._asks.append(self._ask_text(ch))
            return
        if value not in ch.options:
            if value or raw:
                said = self._label(ch, value) if value else raw
                self._notes.append(f"«{said}» нельзя выбрать в «{item.name}»")
            self._asks.append(self._ask_text(ch))
            return
        line.choices[cid] = value

    # ------------------------------------------------------------ ссылки на строки
    def _resolve(self, ref: Optional[LineRef]) -> Optional[CartLine]:
        line = self._find(ref)
        if line is None:
            self._notes.append(self._miss(ref))
        return line

    def _find(self, ref: Optional[LineRef]) -> Optional[CartLine]:
        lines = self.lines
        if not lines:
            return None
        if ref is None or not (ref.ordinal or ref.menu_item_id or ref.candidates or ref.is_last):
            # неявная ссылка («без лука», «сделай его большим») -> последняя тронутая строка
            return self._last if any(l is self._last for l in lines) else lines[-1]
        if ref.is_last:
            return lines[-1]
        ids = [ref.menu_item_id] if ref.menu_item_id else ref.candidates
        pool = [l for l in lines if l.item_id in ids] if ids else lines
        if not pool:
            return None
        if ref.ordinal:
            if ref.ordinal <= len(pool):
                return pool[ref.ordinal - 1]
            # «второй кофе» при одной строке «2 × Кофе» -> отделяем одну штуку
            n = 0
            for l in pool:
                if ref.ordinal <= n + l.quantity:
                    return self._split(l) if l.quantity > 1 else l
                n += l.quantity
            return None
        if len({l.item_id for l in pool}) > 1:      # «сок» при двух разных соках
            return None
        return next((l for l in pool if l is self._last), pool[-1])

    def _split(self, line: CartLine) -> CartLine:
        line.quantity -= 1
        one = line.model_copy(deep=True, update={"quantity": 1})
        self.lines.insert(self._index(line) + 1, one)
        return one

    def _index(self, line: CartLine) -> int:
        return next(i for i, l in enumerate(self.lines) if l is line)

    def _miss(self, ref: Optional[LineRef]) -> str:
        if not self.lines:
            return "Корзина пуста"
        if ref and ref.menu_item_id:
            return f"В корзине нет: {self._name(ref.menu_item_id)}"
        if ref and ref.candidates:
            return f"Уточните, какой: {self._or([self._name(i) for i in ref.candidates])}?"
        if ref and ref.ordinal:
            return f"В корзине нет позиции №{ref.ordinal}"
        return "Не понял, какую позицию изменить"

    # ------------------------------------------------------------ вид
    def _name(self, item_id: str) -> str:
        item = self.menu.item(item_id)
        return item.name if item else item_id

    def _label(self, ch: ComboChoice, value: str) -> str:
        return SIZE_LABEL.get(value, value) if ch.kind == "size" else self._name(value)

    @staticmethod
    def _or(names: list[str]) -> str:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " или " + names[-1]

    def view(self) -> CartView:
        out = []
        for i, l in enumerate(self.lines, 1):
            item = self.menu.item(l.item_id)
            unit = unit_price_cents(l, self.menu)
            mods = [ModifierView(id=m.modifier_id, name=self.menu.modifier(m.modifier_id).name, op=m.op,
                                 price_cents=self.menu.modifier(m.modifier_id).price_cents if m.op == "add" else 0)
                    for m in l.modifiers]
            chs = [ChoiceView(id=c.id, label=c.label or c.id, value=l.choices[c.id], name=self._label(c, l.choices[c.id]),
                              price_delta_cents=c.price_delta_cents.get(l.choices[c.id], 0))
                   for c in item.choices if c.id in l.choices]
            missing = [c.label or c.id for c in self.missing(l)]
            out.append(LineView(line=i, item_id=l.item_id, name=item.name, quantity=l.quantity, size=l.size,
                                modifiers=mods, choices=chs, missing=missing, pending=bool(missing),
                                unit_price_cents=unit, line_total_cents=unit * l.quantity))
        return CartView(lines=out, status=self.status, has_pending=any(v.pending for v in out),
                        total_cents=sum(v.line_total_cents for v in out if not v.pending))


def format_cart(view: CartView, menu: Menu) -> str:
    if not view.lines:
        return f"(корзина пуста)  [{view.status}]"
    rows = []
    for l in view.lines:
        desc = l.name + (f" ({l.size.value})" if l.size else "")
        parts = [c.name for c in l.choices]
        parts += [f"+{m.name.lower()}" if m.op == "add" else f"без {menu.modifier(m.id).gen or m.name.lower()}"
                  for m in l.modifiers]
        if parts:
            desc += ": " + ", ".join(parts)
        price = f"ждёт выбора: {', '.join(l.missing)}" if l.pending else money(l.line_total_cents)
        rows.append(f"{l.line}. {l.quantity} × {desc}  —  {price}")
    rows.append(f"Итого: {money(view.total_cents)}  [{view.status}]")
    return "\n".join(rows)


def _main() -> int:
    """Собрать корзину из одной или нескольких аудиозаписей (по порядку, как один разговор)."""
    import argparse
    import mimetypes
    from pathlib import Path

    from dotenv import load_dotenv

    from .pipeline import build_pipeline

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")    # кириллица и «₸» в cp1252-консоли/при перенаправлении
    parser = argparse.ArgumentParser(description="Audio files -> cart (ElevenLabs STT + NLU).")
    parser.add_argument("audio", type=Path, nargs="+", help="Audio files, in conversation order")
    parser.add_argument("--language", "--lang", choices=("ru", "kk"), help="Optional language hint")
    args = parser.parse_args()

    missing = [str(p) for p in args.audio if not p.is_file()]
    if missing:
        parser.error(f"audio file not found: {', '.join(missing)}")
    if not os.getenv("ELEVENLABS_API_KEY") and os.getenv("STT_PROVIDER") != "whisper":
        parser.error("ELEVENLABS_API_KEY is not set (set it in PowerShell or in a project .env file)")

    pipeline = build_pipeline()
    session = CartSession(pipeline.menu)
    for path in args.audio:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            res = pipeline.parse_audio(path.read_bytes(), session.context(), path.name, mime, args.language)
        except Exception as exc:
            print(f"[{path.name}] transcription failed: {exc}")
            return 1
        reply = session.handle(res.commands)
        print(f"[{path.name}] «{res.transcript}»")
        for note in reply.notes:
            print(f"  ! {note}")
        if reply.question:
            print(f"  ? {reply.question}")
        print(format_cart(reply.cart, pipeline.menu))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
