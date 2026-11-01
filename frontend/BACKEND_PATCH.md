# Патч для бэка: ручные действия киоска

Чтобы тапы по меню (+/-, удалить, выбор в комбо) шли в корзину напрямую, а не через распознавание текста,
в `voice_cart_nlu/api.py` нужен один эндпоинт. Метод `CartSession.apply(actions)` уже есть, его просто не открыли наружу.

Добавить в конец `voice_cart_nlu/api.py`:

```python
from .actions import Action  # noqa: E402


class ActionsReq(BaseModel):
    actions: list[Action]


@app.post("/cart/{session_id}/actions", response_model=CartStep)
def cart_actions(session_id: str, req: ActionsReq):
    """Кнопки киоска: те же Action, что выдаёт NLU, применяются к той же корзине."""
    s = _session(session_id)
    reply = s.apply(req.actions)
    return CartStep(**reply.model_dump(), transcript="", lang="ru", timings_ms={})
```

Перезапустить `py -m uvicorn voice_cart_nlu.api:app --reload`.

Без патча фронт тоже работает: если `/actions` отвечает 404, кнопки отправляются текстовыми командами
(«бургер», «убери второе», «убери один бургер»). В «Метриках» видно, какой путь используется: «через /actions» или «через текст».

Какие действия шлёт фронт:

| Кнопка | Action |
|---|---|
| Корзина на карточке | `{"type": "add_item", "item_id": "cola", "quantity": 1, "size": "L"}` |
| `+` / `-` | `{"type": "change_quantity", "target": {"ordinal": 2}, "quantity": 3}` |
| `✕` или `-` при 1 шт | `{"type": "remove_item", "target": {"ordinal": 2}}` |
| Кнопка варианта в комбо | `{"type": "set_combo_choice", "choice_id": "side", "value": "fries", "target": {"ordinal": 1}}` |
| Подтвердить / Очистить | `{"type": "confirm"}` / `{"type": "clear_cart"}` |
