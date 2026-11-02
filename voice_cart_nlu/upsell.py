# допродажа: есть trigger в корзине и нет offer - предлагаем offer
# правила по порядку сверху вниз, каждое блюдо предлагаем один раз за заказ
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .menu import Menu

MAX_OFFERS_PER_ORDER = 2   # чтобы не надоедать гостю

DEFAULT_RULES = [
    {"trigger": "burger", "offer": "fries", "text": "Добавить картофель фри к бургеру?"},
    {"trigger": "side", "offer": "cheese_sauce", "text": "Возьмёте сырный соус?"},
    {"trigger": "burger", "offer": "coca_cola", "text": "Что-нибудь попить? Coca-Cola"},
    {"trigger": "combo", "offer": "cherry_pie", "text": "На десерт вишнёвый пирожок?"},
    {"trigger": "americano", "offer": "cinnabon", "text": "К кофе синнабон?"},
    {"trigger": "latte", "offer": "cinnabon", "text": "К кофе синнабон?"},
]


class UpsellRule(BaseModel):
    trigger: str = Field(min_length=1)       # id блюда или категория
    offer: str = Field(min_length=1)         # что предлагаем
    text: Optional[str] = Field(None, max_length=200)


class UpsellView(BaseModel):
    item_id: str
    name: str
    name_kk: str
    name_en: str
    price_cents: int
    text: str


def check_rules(rules: list[UpsellRule], menu: Menu) -> list[str]:
    # неизвестные id, чтобы админка не сохранила опечатку
    categories = {i.category for i in menu.items}
    errors = []
    for n, r in enumerate(rules, 1):
        if not menu.item(r.trigger) and r.trigger not in categories:
            errors.append(f"Правило {n}: нет блюда или категории «{r.trigger}»")
        if not menu.item(r.offer):
            errors.append(f"Правило {n}: нет блюда «{r.offer}»")
    return errors


def pick_offer(rules: list[UpsellRule], menu: Menu, cart_item_ids: list[str],
               already_offered: set[str]) -> Optional[UpsellView]:
    if len(already_offered) >= MAX_OFFERS_PER_ORDER:
        return None
    in_cart = set(cart_item_ids)
    in_cart_categories = {menu.item(i).category for i in in_cart if menu.item(i)}
    for r in rules:
        item = menu.item(r.offer)
        if not item or not item.available or r.offer in in_cart or r.offer in already_offered:
            continue
        if r.trigger in in_cart or r.trigger in in_cart_categories:
            price = item.size_prices_cents.get(item.default_size, item.price_cents) if item.default_size \
                else item.price_cents
            text = r.text or f"Добавить {item.name}?"
            return UpsellView(item_id=item.id, name=item.name, name_kk=item.name_kk or item.name,
                              name_en=item.name_en or item.name, price_cents=price, text=text)
    return None
