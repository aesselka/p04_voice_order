"""Cart State Machine: цены в тиынах, добавки, проверки по меню, многошаговые правки."""
from voice_cart_nlu.actions import Action
from voice_cart_nlu.cart import CartLine, CartSession, money, unit_price_cents
from voice_cart_nlu.menu import Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline
from voice_cart_nlu.schemas import LineRef, ModifierOp, Size

MENU = Menu.load()
PIPE = VoiceCommandPipeline(MENU)


def say(s: CartSession, *texts):
    """Прогнать фразы как разговор; вернуть последний ответ и все заметки."""
    notes, reply = [], None
    for t in texts:
        reply = s.handle(PIPE.parse_text(t, s.context()).commands)
        notes += reply.notes
    return reply, notes


def brief(s: CartSession):
    return [(l.item_id, l.quantity, l.size.value if l.size else None,
             tuple(sorted((m.modifier_id, m.op) for m in l.modifiers))) for l in s.lines]


# ---------------------------------------------------------------- математика корзины
def test_prices_are_integer_cents_from_menu():
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id="burger", quantity=2),
             Action(type="add_item", item_id="cola", size=Size.L)])
    v = s.view()
    assert [l.unit_price_cents for l in v.lines] == [180000, 80000]
    assert [l.line_total_cents for l in v.lines] == [360000, 80000]
    assert v.total_cents == 440000
    assert all(isinstance(l.line_total_cents, int) for l in v.lines)


def test_size_price_and_default_size():
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id="coffee")])
    assert s.lines[0].size == Size.M and s.view().total_cents == 80000
    s.apply([Action(type="change_size", size=Size.S)])
    assert s.view().total_cents == 70000


def test_paid_modifier_adds_and_removal_is_free():
    line = CartLine(item_id="burger", quantity=3,
                    modifiers=[ModifierOp(modifier_id="cheese"), ModifierOp(modifier_id="onion", op="remove")])
    assert unit_price_cents(line, MENU) == 180000 + 15000


def test_change_quantity_and_remove_some():
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id="cola", quantity=3),
             Action(type="change_quantity", quantity=5)])
    assert brief(s) == [("cola", 5, "M", ())]
    s.apply([Action(type="remove_item", target=LineRef(menu_item_id="cola"), quantity=2)])
    assert brief(s) == [("cola", 3, "M", ())] and s.view().total_cents == 3 * 60000


def test_identical_items_merge_different_stay_apart():
    s = CartSession(MENU)
    say(s, "Два бургера", "Бургер", "Добавь бургер без лука")
    assert brief(s) == [("burger", 3, None, ()), ("burger", 1, None, (("onion", "remove"),))]


def test_no_verb_with_item_in_cart_edits_it():
    s = CartSession(MENU)
    say(s, "Бургер", "Бургер без лука")                     # без глагола и бургер уже есть -> правка
    assert brief(s) == [("burger", 1, None, (("onion", "remove"),))]


def test_money_format():
    assert money(180000) == "1 800 ₸" and money(5) == "0,05 ₸" and money(-10000) == "−100 ₸"


def test_legacy_menu_price_in_tenge_still_loads():
    m = Menu.model_validate({"items": [{"id": "x", "name": "X", "price": 1800}]})
    assert m.items[0].price_cents == 180000


# ---------------------------------------------------------------- добавки и проверки по меню
def test_modifier_toggle_returns_to_default():
    s = CartSession(MENU)
    say(s, "Бургер", "Добавь сыр")
    assert brief(s) == [("burger", 1, None, (("cheese", "add"),))]
    say(s, "Убери сыр")
    assert brief(s) == [("burger", 1, None, ())]


def test_disallowed_modifier_rejected():
    s = CartSession(MENU)
    _, notes = say(s, "Воду", "Добавь лёд в воду")
    assert brief(s) == [("water", 1, None, ())] and any("нельзя" in n for n in notes)


def test_unknown_modifier_rejected():
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id="burger")])
    r = s.apply([Action(type="add_modifier", modifier_id="bacon")])
    assert brief(s) == [("burger", 1, None, ())] and r.notes


def test_unknown_item_rejected_and_reported():
    s = CartSession(MENU)
    _, notes = say(s, "Хочу пиццу")
    assert not s.lines and any("пицц" in n for n in notes)
    r = s.apply([Action(type="add_item", item_id="pizza")])
    assert not s.lines and r.notes


def test_size_not_allowed():
    s = CartSession(MENU)
    _, notes = say(s, "Большую воду")
    assert brief(s) == [("water", 1, None, ())] and any("размер" in n for n in notes)


def test_ambiguous_item_asks_one_question():
    s = CartSession(MENU)
    r, _ = say(s, "Сок")
    assert not s.lines and "Сок яблочный" in r.question and "Сок апельсиновый" in r.question


def test_remove_missing_item_noted():
    s = CartSession(MENU)
    _, notes = say(s, "Бургер", "Убери колу")
    assert brief(s) == [("burger", 1, None, ())] and notes


# ---------------------------------------------------------------- многошаговые правки
def test_scenario_coffee_edits():
    s = CartSession(MENU)
    say(s, "Два кофе и бургер")
    assert brief(s) == [("coffee", 2, "M", ()), ("burger", 1, None, ())]
    say(s, "Убери второй кофе")
    assert brief(s) == [("coffee", 1, "M", ()), ("burger", 1, None, ())]
    say(s, "Сделай его большим")                              # «его» = оставшийся кофе, не бургер
    assert brief(s)[0] == ("coffee", 1, "L", ())
    say(s, "Бургер без лука", "Добавь сыр")
    assert brief(s)[1] == ("burger", 1, None, (("cheese", "add"), ("onion", "remove")))
    r, _ = say(s, "Подтверждаю")
    assert r.cart.status == "confirmed" and r.cart.total_cents == 100000 + 180000 + 15000


def test_scenario_ordinal_line_and_split():
    s = CartSession(MENU)
    say(s, "Хочу два бургера и большую колу", "Второе убери")
    assert brief(s) == [("burger", 2, None, ())]
    say(s, "Сделай второй бургер без лука")
    assert brief(s) == [("burger", 1, None, ()), ("burger", 1, None, (("onion", "remove"),))]


def test_scenario_replace_keeps_quantity_and_size():
    s = CartSession(MENU)
    say(s, "Две колы", "Колу сделай большой", "Замени колу на спрайт")
    assert brief(s) == [("sprite", 2, "L", ())]
    assert s.view().total_cents == 2 * 80000


def test_scenario_change_quantity_by_voice():
    s = CartSession(MENU)
    say(s, "Колу", "Сделай колу три")
    assert brief(s) == [("cola", 3, "M", ())]


def test_scenario_clear_then_continue():
    s = CartSession(MENU)
    say(s, "Два бургера", "Подтверждаю")
    assert s.status == "confirmed"
    say(s, "Отмени заказ")
    assert s.status == "cancelled" and not s.lines
    say(s, "Бургер")
    assert s.status == "open" and brief(s) == [("burger", 1, None, ())]


def test_confirm_empty_cart():
    s = CartSession(MENU)
    r, notes = say(s, "Подтверждаю")
    assert r.cart.status == "open" and notes
