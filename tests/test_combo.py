"""Комбо: обязательные выборы из menu.json, один вопрос за раз, pending до полного выбора."""
from voice_cart_nlu.actions import Action
from voice_cart_nlu.cart import CartSession
from voice_cart_nlu.menu import Menu
from voice_cart_nlu.pipeline import VoiceCommandPipeline

MENU = Menu.load()
PIPE = VoiceCommandPipeline(MENU)


def say(s: CartSession, text: str):
    return s.handle(PIPE.parse_text(text, s.context()).commands)


def test_missing_choices_asked_one_by_one_and_never_guessed():
    s = CartSession(MENU)
    r = say(s, "Комбо")
    assert r.question == "Какой напиток к комбо: Кока-кола, Спрайт или Фанта?"
    assert r.cart.lines[0].pending and r.cart.total_cents == 0
    assert s.lines[0].choices == {}                         # ничего не подставлено
    r = say(s, "Колу")
    assert [l.item_id for l in s.lines] == ["combo"]        # кола ушла в комбо, а не отдельной строкой
    assert r.question.startswith("Какой гарнир")
    r = say(s, "Наггетсы")
    assert r.question.startswith("Какой размер")
    r = say(s, "Большой")
    assert r.question is None and not r.cart.lines[0].pending
    assert s.lines[0].choices == {"drink": "cola", "side": "nuggets", "size": "L"}
    assert r.cart.total_cents == 290000 + 20000


def test_all_choices_in_one_phrase():
    s = CartSession(MENU)
    r = say(s, "Большое комбо с колой и картошкой")
    assert r.question is None and [l.item_id for l in s.lines] == ["combo"]
    assert s.lines[0].choices == {"drink": "cola", "side": "fries", "size": "L"}


def test_partial_choices_ask_only_the_rest():
    s = CartSession(MENU)
    r = say(s, "Комбо со спрайтом")
    assert s.lines[0].choices == {"drink": "sprite"} and r.question.startswith("Какой гарнир")


def test_invalid_option_rejected_and_reasked():
    s = CartSession(MENU)
    say(s, "Комбо")
    r = say(s, "Кофе")
    assert [l.item_id for l in s.lines] == ["combo"] and s.lines[0].choices == {}
    assert any("Кофе" in n for n in r.notes)
    assert r.question.startswith("Какой напиток")


def test_ambiguous_answer_reasks_with_options():
    s = CartSession(MENU)
    say(s, "Комбо")
    r = say(s, "Сок")                                       # соков нет среди напитков комбо
    assert s.lines[0].choices == {} and r.question.startswith("Какой напиток")
    r = s.apply([Action(type="set_combo_choice", choice_id="drink", candidates=["cola", "sprite"])])
    assert r.question == "Какой напиток к комбо: Кока-кола или Спрайт?"


def test_pending_blocks_confirm_and_total():
    s = CartSession(MENU)
    say(s, "Бургер")
    r = say(s, "Комбо")
    assert r.cart.total_cents == 180000 and r.cart.has_pending
    r = say(s, "Подтверждаю")
    assert r.cart.status == "open" and r.question.startswith("Какой напиток")


def test_two_combos_share_answers():
    s = CartSession(MENU)
    say(s, "Два комбо со спрайтом")
    say(s, "Картошку")
    r = say(s, "Маленький")
    assert r.question is None and s.lines[0].quantity == 2
    assert r.cart.total_cents == 2 * (290000 - 10000)


def test_combo_size_change_later_is_choice_with_price():
    s = CartSession(MENU)
    say(s, "Комбо с колой и картошкой")
    say(s, "Средний")
    assert s.view().total_cents == 290000
    say(s, "Комбо сделай большим")
    assert s.lines[0].choices["size"] == "L" and s.view().total_cents == 310000


def test_drop_pending_combo():
    s = CartSession(MENU)
    say(s, "Комбо")
    r = say(s, "Не надо комбо")
    assert not s.lines and r.question is None


def test_combo_modifiers_still_apply():
    s = CartSession(MENU)
    say(s, "Комбо с колой и картошкой")
    say(s, "Маленький")
    say(s, "Без лука")
    assert [(m.modifier_id, m.op) for m in s.lines[0].modifiers] == [("onion", "remove")]
