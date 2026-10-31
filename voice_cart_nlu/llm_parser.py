"""LLM-fallback: структурированный JSON -> Pydantic. Вызывается, только если rules не уверены."""
from __future__ import annotations

import json
import os
import re
from typing import Optional, Protocol

from pydantic import BaseModel, ValidationError

from .menu import Menu
from .schemas import CartContext, Command


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicJSONClient:
    """Ключ берётся из ANTHROPIC_API_KEY, модель — из LLM_MODEL."""

    def __init__(self, model: Optional[str] = None):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model or os.getenv("LLM_MODEL", "claude-haiku-5-5")

    def complete(self, system: str, user: str) -> str:
        r = self.client.messages.create(
            model=self.model, max_tokens=800, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return r.content[0].text


class _Out(BaseModel):
    commands: list[Command]


SYSTEM = """Ты — NLU-модуль голосовой корзины ресторана. Гость говорит по-русски, по-казахски или смешивая языки.
Преобразуй реплику в JSON. Ты НЕ меняешь корзину и НЕ считаешь цены — только описываешь намерение.
Отвечай ТОЛЬКО JSON без markdown и пояснений: {"commands": [Command, ...]}.

Command:
{"intent": "add|remove|modify|cancel|confirm|unknown",
 "items": [{"menu_item_id": str|null, "candidates": [str], "raw_text": str, "quantity": int>=1, "size": "S|M|L"|null,
            "modifiers": [{"modifier_id": str, "op": "add|remove"}]}],      // только для add
 "target": {"ordinal": int|null, "menu_item_id": str|null, "candidates": [str], "is_last": bool} | null,  // remove/modify
 "changes": {"size": "S|M|L"|null, "quantity": int|null, "modifiers": [...], "replace_with": ItemSpec|null} | null, // modify
 "quantity": int|null,    // remove: сколько штук убрать
 "issues": [str]}

Правила:
- cancel = отмена ВСЕГО заказа; убрать одну позицию = remove.
- «второе убери» -> remove, target.ordinal=2 (номер строки корзины, с 1). «последнее» -> is_last=true.
- «колу сделай большой» -> modify, target.menu_item_id=cola, changes.size=L.
- «без лука» -> modifier op=remove; «с сыром»/«добавь сыр» -> op=add.
- Используй ТОЛЬКО id из меню. Если блюда нет в меню — intent=unknown, issues=["unknown_item:<слово>"].
- Если под слово подходит несколько блюд — menu_item_id=null, candidates=[...], issues=["ambiguous_item:<слово>"].
- Если несколько действий в одной фразе — несколько команд по порядку.
- Ничего не выдумывай: не добавляй позиций, которых гость не называл."""


def _menu_prompt(menu: Menu) -> str:
    items = [{"id": i.id, "name": i.name, "sizes": [s.value for s in i.sizes], "modifiers": i.modifiers}
             for i in menu.items]
    mods = [{"id": m.id, "name": m.name} for m in menu.modifiers]
    return json.dumps({"items": items, "modifiers": mods}, ensure_ascii=False)


def _extract_json(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    a, b = raw.find("{"), raw.rfind("}")
    return raw[a:b + 1] if a != -1 and b != -1 else raw


def llm_parse(text: str, menu: Menu, client: LLMClient, cart: Optional[CartContext] = None,
              retries: int = 1) -> list[Command]:
    user = (f"МЕНЮ: {_menu_prompt(menu)}\n"
            f"КОРЗИНА: {json.dumps(cart.model_dump(mode='json') if cart else {'lines': []}, ensure_ascii=False)}\n"
            f"РЕПЛИКА: {text}")
    last_err = ""
    for _ in range(retries + 1):
        raw = client.complete(SYSTEM, user + (f"\nПредыдущий ответ невалиден: {last_err}. Верни только JSON." if last_err else ""))
        try:
            out = _Out.model_validate_json(_extract_json(raw))
            for c in out.commands:
                c.source, c.text = "llm", text
                c.confidence = 0.8
            return out.commands
        except (ValidationError, ValueError) as e:
            last_err = str(e)[:300]
    return []
