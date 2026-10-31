"""Command -> Action JSON."""
import json

from voice_cart_nlu.actions import to_actions
from voice_cart_nlu.menu import Menu, MenuIndex
from voice_cart_nlu.rules import parse

MENU = Menu.load()
IDX = MenuIndex(MENU)


def acts(text, pending=None):
    actions, notes = to_actions(parse(text, IDX), MENU, pending)
    return [a.model_dump(mode="json", exclude_defaults=True) for a in actions], notes


def test_add_items_with_size_and_modifiers():
    a, _ = acts("Два бургера без лука и большую колу")
    assert a == [{"type": "add_item", "item_id": "burger", "raw": "бургера", "quantity": 2,
                  "modifiers": [{"modifier_id": "onion", "op": "remove"}]},
                 {"type": "add_item", "item_id": "cola", "raw": "колу", "quantity": 1, "size": "L"}]


def test_edit_actions():
    assert acts("Убери второй кофе")[0] == [{"type": "remove_item", "target": {"ordinal": 2, "menu_item_id": "coffee"}}]
    assert acts("Сделай большой")[0] == [{"type": "change_size", "target": {}, "size": "L"}]
    assert acts("Сделай колу три")[0] == [{"type": "change_quantity", "target": {"menu_item_id": "cola"}, "quantity": 3}]
    assert acts("Добавь сыр в бургер")[0] == [{"type": "add_modifier", "target": {"menu_item_id": "burger"},
                                               "modifier_id": "cheese"}]
    assert acts("Без льда")[0][0]["type"] == "remove_modifier"
    assert [x["type"] for x in acts("Отмени заказ")[0]] == ["clear_cart"]
    assert [x["type"] for x in acts("Подтверждаю")[0]] == ["confirm"]


def test_replace_is_remove_plus_add():
    a, _ = acts("Замени колу на спрайт")
    assert [x["type"] for x in a] == ["remove_item", "add_item"]
    assert a[1]["item_id"] == "sprite" and a[1]["replaces"] is True and "quantity" not in a[1]


def test_combo_choices_from_same_phrase():
    a, _ = acts("Большое комбо с колой и картошкой")
    assert a == [{"type": "add_item", "item_id": "combo", "raw": "комбо", "quantity": 1,
                  "choices": {"size": "L", "drink": "cola", "side": "fries"}}]


def test_answer_to_pending_combo_becomes_choice():
    combo = MENU.item("combo")
    a, _ = acts("Колу", pending=(combo.choices, {}))
    assert a == [{"type": "set_combo_choice", "raw": "колу", "choice_id": "drink", "value": "cola"}]
    a, _ = acts("Большой", pending=(combo.choices, {"drink": "cola", "side": "fries"}))
    assert a == [{"type": "set_combo_choice", "choice_id": "size", "value": "L"}]


def test_unrelated_item_while_combo_pending_is_added():
    a, _ = acts("Бургер", pending=(MENU.item("combo").choices, {}))
    assert [x["type"] for x in a] == ["add_item"]


def test_unknown_item_note_and_json_serialisable():
    a, notes = acts("Хочу пиццу")
    assert a == [] and notes
    actions, _ = to_actions(parse("Два комбо и колу", IDX), MENU)
    json.loads(json.dumps([x.model_dump(mode="json") for x in actions]))
