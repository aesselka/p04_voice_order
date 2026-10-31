"""Пост-валидация команд против меню: LLM не может подсунуть несуществующий id."""
from __future__ import annotations

from .menu import Menu
from .schemas import Command, Intent


def validate_commands(cmds: list[Command], menu: Menu) -> list[Command]:
    ok_items = {i.id for i in menu.items}
    ok_mods = {m.id for m in menu.modifiers}

    def bad_item(x): return x is not None and x not in ok_items

    for c in cmds:
        for it in c.items:
            if bad_item(it.menu_item_id):
                c.issues.append(f"unknown_item_id:{it.menu_item_id}")
                it.menu_item_id = None
            it.candidates = [x for x in it.candidates if x in ok_items]
            keep = [m for m in it.modifiers if m.modifier_id in ok_mods]
            if len(keep) != len(it.modifiers):
                c.issues.append("unknown_modifier_dropped")
            it.modifiers = keep
        c.items = [it for it in c.items if it.menu_item_id or it.candidates]
        if c.target:
            if bad_item(c.target.menu_item_id):
                c.issues.append(f"unknown_item_id:{c.target.menu_item_id}")
                c.target.menu_item_id = None
            c.target.candidates = [x for x in c.target.candidates if x in ok_items]
        if c.changes:
            keep = [m for m in c.changes.modifiers if m.modifier_id in ok_mods]
            if len(keep) != len(c.changes.modifiers):
                c.issues.append("unknown_modifier_dropped")
            c.changes.modifiers = keep
            r = c.changes.replace_with
            if r and bad_item(r.menu_item_id):
                c.issues.append(f"unknown_item_id:{r.menu_item_id}")
                c.changes.replace_with = None
        if c.intent == Intent.add and not c.items:
            c.intent, c.confidence = Intent.unknown, min(c.confidence, 0.3)
    return cmds
