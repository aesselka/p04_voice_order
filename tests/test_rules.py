import pytest

from voice_cart_nlu.menu import Menu, MenuIndex
from voice_cart_nlu.rules import parse
from voice_cart_nlu.schemas import CartContext, CartLineView

IDX = MenuIndex(Menu.load())


def brief(c):
    d = {"i": c.intent.value}
    if c.items:
        d["items"] = [(i.menu_item_id, i.quantity, i.size.value if i.size else None,
                       tuple(sorted((m.modifier_id, m.op) for m in i.modifiers))) for i in c.items]
    if c.target:
        d["ord"], d["tid"], d["last"] = c.target.ordinal, c.target.menu_item_id, c.target.is_last
    if c.changes:
        d["size"] = c.changes.size.value if c.changes.size else None
        d["q"] = c.changes.quantity
        d["mods"] = tuple(sorted((m.modifier_id, m.op) for m in c.changes.modifiers))
        d["repl"] = c.changes.replace_with.menu_item_id if c.changes.replace_with else None
    d["rq"] = c.quantity
    return d


CASES = [
    # --- ru: ключевые сценарии из ТЗ
    ("Два комбо", [{"i": "add", "items": [("combo", 2, None, ())]}]),
    ("Хочу два комбо и большую колу", [{"i": "add", "items": [("combo", 2, None, ()), ("cola", 1, "L", ())]}]),
    ("Второе убери", [{"i": "remove", "ord": 2}]),
    ("Убери второе", [{"i": "remove", "ord": 2}]),
    ("Колу сделай большой", [{"i": "modify", "tid": "cola", "size": "L"}]),
    ("Сделай колу маленькой", [{"i": "modify", "tid": "cola", "size": "S"}]),
    ("Бургер без лука", [{"i": "add", "items": [("burger", 1, None, (("onion", "remove"),))]}]),
    ("Добавь сыр", [{"i": "modify", "tid": None, "mods": (("cheese", "add"),)}]),
    ("Убери лук", [{"i": "modify", "mods": (("onion", "remove"),)}]),
    ("Без льда", [{"i": "modify", "mods": (("ice", "remove"),)}]),
    ("Замени колу на спрайт", [{"i": "modify", "tid": "cola", "repl": "sprite"}]),
    ("Убери колу и добавь воду", [{"i": "remove", "tid": "cola"}, {"i": "add", "items": [("water", 1, None, ())]}]),
    ("Колу убери, а воду добавь", [{"i": "remove", "tid": "cola"}, {"i": "add", "items": [("water", 1, None, ())]}]),
    ("Не надо колу", [{"i": "remove", "tid": "cola"}]),
    ("Убери последнее", [{"i": "remove", "last": True}]),
    ("Убери одну колу", [{"i": "remove", "tid": "cola", "rq": 1}]),
    ("Сделай второе комбо без лука", [{"i": "modify", "tid": "combo", "ord": 2, "mods": (("onion", "remove"),)}]),
    ("Дайте картошку фри и чикен бургер", [{"i": "add", "items": [("fries", 1, None, ()), ("chicken_burger", 1, None, ())]}]),
    ("Два бургера и большую колу", [{"i": "add", "items": [("burger", 2, None, ()), ("cola", 1, "L", ())]}]),
    ("Сок", [{"i": "add", "items": [(None, 1, None, ())]}]),            # неоднозначно -> candidates
    ("Яблочный сок пожалуйста", [{"i": "add", "items": [("juice_apple", 1, None, ())]}]),
    ("Подтверждаю", [{"i": "confirm"}]),
    ("Да, всё верно", [{"i": "confirm"}]),
    ("Отмени заказ", [{"i": "cancel"}]),
    ("Начни заново", [{"i": "cancel"}]),
    ("Убери всё", [{"i": "cancel"}]),
    ("Отмени колу", [{"i": "remove", "tid": "cola"}]),
    ("Хочу кока колу", [{"i": "add", "items": [("cola", 1, None, ())]}]),     # STT: «кока колу»
    ("Хочу коллу", [{"i": "add", "items": [("cola", 1, None, ())]}]),        # опечатка STT, fuzzy
    # --- kk
    ("Екі комбо беріңіз", [{"i": "add", "items": [("combo", 2, None, ())]}]),
    ("Үлкен кола және бір бургер", [{"i": "add", "items": [("cola", 1, "L", ()), ("burger", 1, None, ())]}]),
    ("Екіншісін алып таста", [{"i": "remove", "ord": 2}]),
    ("Кола үлкен болсын", [{"i": "modify", "tid": "cola", "size": "L"}]),
    ("Бургер пиязсыз", [{"i": "add", "items": [("burger", 1, None, (("onion", "remove"),))]}]),
    ("Тапсырысты растаймын", [{"i": "confirm"}]),
    ("Жарайды", [{"i": "confirm"}]),
    ("Тапсырыстан бас тарту", [{"i": "cancel"}]),
    ("Колаға мұз қос", [{"i": "modify", "tid": "cola", "mods": (("ice", "add"),)}]),
    # --- смешанный ru+kk
    ("Один комбо, кола үлкен", [{"i": "add", "items": [("combo", 1, None, ()), ("cola", 1, "L", ())]}]),
]


@pytest.mark.parametrize("text,expected", CASES, ids=[c[0] for c in CASES])
def test_dialogs(text, expected):
    got = [brief(c) for c in parse(text, IDX)]
    assert len(got) == len(expected), got
    for g, e in zip(got, expected):
        for k, v in e.items():
            assert g.get(k) == v, f"{text!r}: {k}: {g.get(k)!r} != {v!r}  (full: {g})"


def test_ambiguous_issue():
    c = parse("Сок", IDX)[0]
    assert set(c.items[0].candidates) == {"juice_apple", "juice_orange"}
    assert any(i.startswith("ambiguous_item") for i in c.issues)


def test_unknown_item_lowers_confidence():
    c = parse("Хочу пиццу", IDX)[0]
    assert c.intent.value == "unknown" or c.confidence < 0.75


def test_no_verb_modify_when_in_cart():
    cart = CartContext(lines=[CartLineView(index=1, menu_item_id="cola")])
    c = parse("Колу большую", IDX, cart)[0]
    assert c.intent.value == "modify" and c.changes.size.value == "L"
    c2 = parse("Колу большую", IDX)[0]
    assert c2.intent.value == "add"


def test_multi_turn_sequence():
    """Сценарий из ТЗ: два комбо -> второе убери -> колу сделай большой."""
    seq = ["Два комбо", "Второе убери", "Колу сделай большой", "Подтверждаю"]
    intents = [parse(t, IDX)[0].intent.value for t in seq]
    assert intents == ["add", "remove", "modify", "confirm"]


def test_add_to_existing_item():
    c = parse("Добавь сыр в бургер", IDX)[0]
    assert c.intent.value == "modify" and c.target.menu_item_id == "burger"
    assert [(m.modifier_id, m.op) for m in c.changes.modifiers] == [("cheese", "add")]
