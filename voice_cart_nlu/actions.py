"""Command (NLU) -> Action: плоские действия над корзиной в JSON.

NLU (rules / LLM) описывает намерение фразы; здесь оно раскладывается на атомарные
действия, которые Cart State Machine проверяет по меню и применяет по одному.
Цены сюда не попадают никогда.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .menu import ComboChoice, Menu
from .schemas import Command, Intent, ItemSpec, LineRef, ModifierOp, Size

ActionType = Literal["add_item", "remove_item", "change_quantity", "change_size",
                     "add_modifier", "remove_modifier", "set_combo_choice", "clear_cart", "confirm"]


class Action(BaseModel):
    type: ActionType
    target: Optional[LineRef] = None          # к какой строке (remove/change/modifier/choice)
    item_id: Optional[str] = None             # add_item
    candidates: list[str] = Field(default_factory=list)   # неоднозначно -> переспросить
    raw: str = ""                             # как гость назвал блюдо
    quantity: Optional[int] = Field(None, ge=1, le=20)    # add/remove: штук; change_quantity: новое кол-во
    size: Optional[Size] = None
    modifiers: list[ModifierOp] = Field(default_factory=list)   # add_item
    modifier_id: Optional[str] = None         # add_modifier / remove_modifier
    choices: dict[str, str] = Field(default_factory=dict)       # add_item комбо: уже названные выборы
    choice_id: Optional[str] = None           # set_combo_choice
    value: Optional[str] = None               # set_combo_choice: id блюда или S/M/L
    replaces: bool = False                    # add_item после remove_item: «замени колу на спрайт»


def _add_action(spec: ItemSpec, menu: Menu) -> Action:
    a = Action(type="add_item", item_id=spec.menu_item_id, candidates=spec.candidates,
               raw=spec.raw_text or "", quantity=spec.quantity, size=spec.size,
               modifiers=spec.modifiers)
    item = menu.item(spec.menu_item_id) if spec.menu_item_id else None
    if item and item.combo and spec.size and item.choice("size"):
        a.choices["size"], a.size = spec.size.value, None          # «большое комбо» = выбор размера
    return a


def _match_choice(spec: ItemSpec, choices: list[ComboChoice], filled: dict[str, str],
                  menu: Menu, loose: bool) -> Optional[tuple[ComboChoice, Optional[str], list[str]]]:
    """Какой из открытых выборов комбо закрывает это блюдо? -> (выбор, значение, кандидаты)."""
    ids = [spec.menu_item_id] if spec.menu_item_id else spec.candidates
    open_ = [c for c in choices if c.kind == "item" and c.id not in filled]
    for ch in open_:
        hits = [i for i in ids if i in ch.options]
        if len(hits) == 1:
            return ch, hits[0], []
        if hits:
            return ch, None, hits
    if loose and ids:
        # ответ на вопрос («кофе» на «какой напиток?») — та же категория, но не из вариантов:
        # отдаём как выбор, корзина отклонит и переспросит
        cats = {menu.item(i).category for i in ids if menu.item(i)}
        for ch in open_:
            if cats & {menu.item(o).category for o in ch.options if menu.item(o)}:
                return ch, ids[0] if len(ids) == 1 else None, []
    return None


def _notes(c: Command) -> list[str]:
    notes = []
    for i in c.issues:
        kind, _, word = i.partition(":")
        if kind in ("unknown_item", "unknown_item_id"):
            notes.append(f"Такого нет в меню: «{word}»")
        elif kind == "unknown_modifier_dropped":
            notes.append("Такой добавки нет в меню")
    if c.intent == Intent.unknown and not notes:
        words = [i.split(":", 1)[1] for i in c.issues if i.startswith("unrecognized:")]
        notes.append(f"Не нашёл в меню: «{' '.join(words)}»" if words else "Не понял, повторите, пожалуйста")
    return notes


def to_actions(cmds: list[Command], menu: Menu,
               pending: Optional[tuple[list[ComboChoice], dict[str, str]]] = None
               ) -> tuple[list[Action], list[str]]:
    """pending = (выборы комбо, уже заполненные) для комбо, которое ждёт ответа гостя."""
    actions: list[Action] = []
    notes: list[str] = []
    for c in cmds:
        notes += _notes(c)
        if c.intent == Intent.add:
            combo: Optional[Action] = None                      # комбо, добавленное в этой же фразе
            for spec in c.items:
                if combo:
                    item = menu.item(combo.item_id)
                    m = _match_choice(spec, item.choices, combo.choices, menu, loose=False)
                    if m and m[1]:
                        combo.choices[m[0].id] = m[1]
                        if spec.size and item.choice("size") and "size" not in combo.choices:
                            combo.choices["size"] = spec.size.value
                        continue
                if not combo and pending:
                    m = _match_choice(spec, pending[0], pending[1], menu, loose=True)
                    if m:
                        ch, value, cands = m
                        actions.append(Action(type="set_combo_choice", choice_id=ch.id, value=value,
                                              candidates=cands, raw=spec.raw_text or ""))
                        size_open = any(x.kind == "size" and x.id not in pending[1] for x in pending[0])
                        if spec.size and size_open:
                            actions.append(Action(type="set_combo_choice", choice_id="size",
                                                  value=spec.size.value))
                        continue
                a = _add_action(spec, menu)
                actions.append(a)
                if a.item_id and menu.item(a.item_id).combo:
                    combo = a
        elif c.intent == Intent.remove:
            actions.append(Action(type="remove_item", target=c.target, quantity=c.quantity))
        elif c.intent == Intent.modify:
            ch = c.changes
            if ch is None:
                continue
            implicit = c.target is None or not (c.target.ordinal or c.target.menu_item_id
                                                or c.target.candidates or c.target.is_last)
            if ch.replace_with:
                actions.append(Action(type="remove_item", target=c.target))
                a = _add_action(ch.replace_with, menu)
                a.quantity, a.replaces = None, True              # количество берём у заменяемой строки
                actions.append(a)
            if ch.size:
                size_open = pending and any(x.kind == "size" and x.id not in pending[1] for x in pending[0])
                if implicit and size_open:                       # «большой» в ответ на «какой размер?»
                    actions.append(Action(type="set_combo_choice", choice_id="size", value=ch.size.value))
                else:
                    actions.append(Action(type="change_size", target=c.target, size=ch.size))
            if ch.quantity:
                actions.append(Action(type="change_quantity", target=c.target, quantity=ch.quantity))
            for mo in ch.modifiers:
                actions.append(Action(type="add_modifier" if mo.op == "add" else "remove_modifier",
                                      target=c.target, modifier_id=mo.modifier_id))
        elif c.intent == Intent.cancel:
            actions.append(Action(type="clear_cart"))
        elif c.intent == Intent.confirm:
            actions.append(Action(type="confirm"))
    return actions, notes
