"""Property-based: случайные последовательности действий над корзиной не ломают её инварианты.

Цена здесь пересчитывается НЕЗАВИСИМО от cart.py — прямо из сырого menu.json (evals/oracle.py).
Если cart.py и этот оракул разойдутся хоть на тиын, тест упадёт и hypothesis покажет
минимальную последовательность действий, которая к этому привела.
"""
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from voice_cart_nlu.actions import Action
from voice_cart_nlu.cart import CartSession
from evals.oracle import PriceOracle
from voice_cart_nlu.menu import Menu
from voice_cart_nlu.schemas import LineRef, ModifierOp, Size

MENU = Menu.load()
ORACLE = PriceOracle()
RAW_ITEMS, RAW_MODS = ORACLE.items, ORACLE.mods

ITEM_IDS = list(RAW_ITEMS)
MOD_IDS = list(RAW_MODS)
CHOICE_IDS = sorted({c["id"] for i in RAW_ITEMS.values() for c in i.get("choices", [])})
CHOICE_VALUES = sorted({o for i in RAW_ITEMS.values() for c in i.get("choices", []) for o in c["options"]})


def oracle_unit_price(line) -> int:
    """Цена одной штуки строки — по сырому JSON, без кода из voice_cart_nlu."""
    return ORACLE.unit(line.item_id, line.size.value if line.size else None,
                       {m.modifier_id: m.op for m in line.modifiers}, line.choices)


# ---------------------------------------------------------------- генераторы действий
refs = st.one_of(
    st.none(),
    st.builds(LineRef, ordinal=st.integers(1, 6)),
    st.builds(LineRef, is_last=st.just(True)),
    st.builds(LineRef, menu_item_id=st.sampled_from(ITEM_IDS)),
    st.builds(LineRef, menu_item_id=st.sampled_from(ITEM_IDS), ordinal=st.integers(1, 4)),
)
sizes = st.sampled_from(list(Size))
qty = st.integers(1, 20)
mod_ops = st.builds(ModifierOp, modifier_id=st.sampled_from(MOD_IDS), op=st.sampled_from(["add", "remove"]))

actions = st.one_of(
    st.builds(Action, type=st.just("add_item"), item_id=st.sampled_from(ITEM_IDS), quantity=qty,
              size=st.none() | sizes, modifiers=st.lists(mod_ops, max_size=3),
              choices=st.dictionaries(st.sampled_from(CHOICE_IDS), st.sampled_from(CHOICE_VALUES), max_size=3)),
    st.builds(Action, type=st.just("add_item"), item_id=st.just("no_such_item"), quantity=qty),
    st.builds(Action, type=st.just("remove_item"), target=refs, quantity=st.none() | qty),
    st.builds(Action, type=st.just("change_quantity"), target=refs, quantity=qty),
    st.builds(Action, type=st.just("change_size"), target=refs, size=sizes),
    st.builds(Action, type=st.just("add_modifier"), target=refs, modifier_id=st.sampled_from(MOD_IDS)),
    st.builds(Action, type=st.just("remove_modifier"), target=refs, modifier_id=st.sampled_from(MOD_IDS)),
    st.builds(Action, type=st.just("set_combo_choice"), target=refs, choice_id=st.sampled_from(CHOICE_IDS),
              value=st.sampled_from(CHOICE_VALUES)),
    st.builds(Action, type=st.just("clear_cart")),
    st.builds(Action, type=st.just("confirm")),
)
dialogs = st.lists(st.lists(actions, min_size=1, max_size=4), min_size=1, max_size=12)

PROP = settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def check_invariants(s: CartSession) -> None:
    view = s.view()
    for line, lv in zip(s.lines, view.lines):
        item = RAW_ITEMS.get(line.item_id)
        assert item is not None, f"в корзине блюдо не из меню: {line.item_id}"
        assert 1 <= line.quantity, f"количество {line.quantity} у {line.item_id}"
        if line.size:
            assert line.size.value in item.get("sizes", []), f"размер {line.size} недопустим для {line.item_id}"
        for m in line.modifiers:
            assert m.modifier_id in item.get("modifiers", []), f"добавка {m.modifier_id} недопустима для {line.item_id}"
        allowed = {c["id"]: c["options"] for c in item.get("choices", [])}
        for cid, val in line.choices.items():
            assert val in allowed.get(cid, []), f"выбор {cid}={val} недопустим для {line.item_id}"
        assert isinstance(lv.unit_price_cents, int) and lv.unit_price_cents >= 0
        assert lv.unit_price_cents == oracle_unit_price(line), f"цена строки {lv.line} расходится с меню"
        assert lv.line_total_cents == lv.unit_price_cents * lv.quantity
    expected_total = sum(lv.line_total_cents for lv in view.lines if not lv.pending)
    assert view.total_cents == expected_total
    assert view.has_pending == any(lv.pending for lv in view.lines)


@PROP
@given(dialogs)
def test_random_dialogs_keep_cart_and_price_consistent(turns):
    s = CartSession(MENU)
    for turn in turns:
        reply = s.apply(turn)
        assert reply.cart == s.view()
        check_invariants(s)


@PROP
@given(dialogs)
def test_confirmed_cart_has_no_pending_combo(turns):
    s = CartSession(MENU)
    for turn in turns:
        s.apply(turn)
        if s.status == "confirmed":
            assert s.lines and not s.view().has_pending


@PROP
@given(dialogs)
def test_clear_always_empties_cart(turns):
    s = CartSession(MENU)
    for turn in turns:
        s.apply(turn)
    s.apply([Action(type="clear_cart")])
    assert s.lines == [] and s.view().total_cents == 0 and s.status == "cancelled"


@PROP
@given(st.sampled_from(ITEM_IDS), qty, qty)
def test_adding_same_item_twice_merges_quantity(item_id, a, b):
    s = CartSession(MENU)
    s.apply([Action(type="add_item", item_id=item_id, quantity=a)])
    s.apply([Action(type="add_item", item_id=item_id, quantity=b)])
    assert len(s.lines) == 1 and s.lines[0].quantity == a + b
