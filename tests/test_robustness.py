"""Неполные / кривые Action: корзина не должна падать и не должна портить сессию.

Такие Action придут не от NLU, а от кнопок киоска (см. frontend/BACKEND_PATCH.md, /cart/{id}/actions),
поэтому схема их не гарантирует. xfail(strict=True) = известный баг: когда его починят, тест
станет XPASS и упадёт — тогда просто удалите маркер.
"""
import pytest

from voice_cart_nlu.actions import Action
from voice_cart_nlu.cart import CartSession
from voice_cart_nlu.menu import Menu

MENU = Menu.load()


def cart_with(item_id: str) -> CartSession:
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id=item_id)])
    return s


def survives(s: CartSession, action: Action) -> None:
    s.apply([action])
    view = s.view()                       # сессия не испорчена: корзину всё ещё можно показать
    assert all(isinstance(l.quantity, int) and l.quantity >= 1 for l in view.lines)


@pytest.mark.xfail(strict=True, reason="BUG: change_quantity без quantity пишет None в строку, view() падает")
@pytest.mark.parametrize("item_id", ["cola", "combo"])
def test_change_quantity_without_quantity(item_id):
    survives(cart_with(item_id), Action(type="change_quantity"))


@pytest.mark.xfail(strict=True, reason="BUG: change_size без size -> AttributeError: None.value")
@pytest.mark.parametrize("item_id", ["cola", "combo"])
def test_change_size_without_size(item_id):
    survives(cart_with(item_id), Action(type="change_size"))


@pytest.mark.parametrize("action", [
    Action(type="add_modifier"),
    Action(type="remove_modifier"),
    Action(type="set_combo_choice", choice_id="drink"),
    Action(type="set_combo_choice", choice_id="drink", value="water"),
    Action(type="add_item"),
    Action(type="add_item", item_id="pizza"),
    Action(type="remove_item"),
], ids=lambda a: a.type + (f"_{a.value or a.item_id}" if (a.value or a.item_id) else ""))
@pytest.mark.parametrize("item_id", ["cola", "combo"])
def test_incomplete_actions_do_not_crash(item_id, action):
    survives(cart_with(item_id), action)


@pytest.mark.parametrize("action_type", ["remove_item", "change_quantity", "change_size", "add_modifier",
                                         "remove_modifier", "set_combo_choice", "confirm"])
def test_actions_on_empty_cart_explain_instead_of_crash(action_type):
    s = CartSession(MENU)
    extra = {"change_quantity": {"quantity": 2}, "change_size": {"size": "L"},
             "add_modifier": {"modifier_id": "cheese"}, "remove_modifier": {"modifier_id": "onion"},
             "set_combo_choice": {"choice_id": "drink", "value": "cola"}}.get(action_type, {})
    reply = s.apply([Action(type=action_type, **extra)])
    assert s.lines == [] and reply.notes, "на пустой корзине гость должен получить объяснение"
