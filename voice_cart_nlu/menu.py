"""Меню и индекс для сопоставления произнесённых слов с id блюд/модификаторов."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator
from rapidfuzz import fuzz, process

from .schemas import Size

DEFAULT_MENU_PATH = Path(__file__).parent / "data" / "menu.json"


class ComboChoice(BaseModel):
    """Обязательный выбор в комбо: напиток (id блюд) или размер (S/M/L)."""
    id: str                                   # "drink" | "side" | "size" | ...
    kind: Literal["item", "size"] = "item"
    label: str = ""                           # «напиток» — для «ждёт выбора: напиток»
    question: str                             # «Какой напиток к комбо»
    options: list[str]
    price_delta_cents: dict[str, int] = Field(default_factory=dict)


class MenuItem(BaseModel):
    id: str
    name: str
    name_kk: str = ""
    name_en: str = ""
    category: str = ""
    available: bool = True                    # false - нет в наличии
    aliases: list[str] = Field(default_factory=list)
    sizes: list[Size] = Field(default_factory=list)
    default_size: Optional[Size] = None
    modifiers: list[str] = Field(default_factory=list)
    combo: bool = False
    choices: list[ComboChoice] = Field(default_factory=list)
    price_cents: int = 0                      # целые тиыны (1/100 ₸); float нигде нет
    size_prices_cents: dict[Size, int] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_price(cls, d):
        if isinstance(d, dict) and "price" in d and "price_cents" not in d:   # старый формат: целые ₸
            d = {**d, "price_cents": int(d["price"]) * 100}
        return d

    def choice(self, choice_id: str) -> Optional[ComboChoice]:
        return next((c for c in self.choices if c.id == choice_id), None)


class Modifier(BaseModel):
    id: str
    name: str
    name_kk: str = ""
    name_en: str = ""
    gen: str = ""                             # родительный падеж для «без лука»
    price_cents: int = 0                      # доплата, только когда добавку добавляют
    aliases: list[str] = Field(default_factory=list)


class Menu(BaseModel):
    items: list[MenuItem]
    modifiers: list[Modifier] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Menu":
        # без пути: MENU_PATH из env, иначе data/menu.json
        path = path or os.getenv("MENU_PATH") or DEFAULT_MENU_PATH
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

    def item(self, item_id: str) -> Optional[MenuItem]:
        return next((i for i in self.items if i.id == item_id), None)

    def modifier(self, mod_id: str) -> Optional[Modifier]:
        return next((m for m in self.modifiers if m.id == mod_id), None)


# ---------------------------------------------------------------- нормализация
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    text = re.sub(r"[^\w\s,]", " ", text)
    text = text.replace(",", " , ")
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    n = normalize(text)
    return n.split() if n else []


# Грубый стеммер: срезаем одно окончание (ru падежи + kk септік/көптік).
# Для аккузатива «колу»/«кола»/«колы» -> «кол»; «бургерді»/«бургеры» -> «бургер».
_ENDINGS = sorted(
    {
        # ru
        "ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "ах", "ях", "ов", "ей",
        "ой", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ом", "ем",
        "ам", "ям", "ы", "и", "а", "я", "у", "ю", "е", "о", "ь", "й",
        # kk
        "ның", "нің", "дың", "дің", "тың", "тің", "лар", "лер", "дар", "дер", "тар", "тер",
        "дан", "ден", "тан", "тен", "нан", "нен", "ға", "ге", "қа", "ке", "ны", "ні",
        "ды", "ді", "ты", "ті", "да", "де", "та", "те", "ын", "ін", "мен", "пен", "бен",
    },
    key=len,
    reverse=True,
)


def _stem_once(word: str) -> str:
    for e in _ENDINGS:
        # однобуквенные окончания: остаток >= 2; длинные (в т.ч. kk): остаток >= 3,
        # чтобы «вода» не превращалась в «во» из-за kk-окончания «-да»
        min_rest = 2 if len(e) == 1 else 3
        if word.endswith(e) and len(word) - len(e) >= min_rest:
            return word[: -len(e)]
    return word


def stem(word: str) -> str:
    """Два прохода: kk-падеж + русская/казахская гласная («колаға» -> «кола» -> «кол»)."""
    return _stem_once(_stem_once(word))


class MenuIndex:
    """Сопоставление слов -> блюда/модификаторы (точное по основе + fuzzy для шума STT)."""

    FUZZY_CUTOFF = 85
    FUZZY_MIN_LEN = 4

    def __init__(self, menu: Menu):
        self.menu = menu
        # alias -> (item_id, [stems])
        self._aliases: list[tuple[str, list[str]]] = []
        self._stem_items: dict[str, set[str]] = {}
        for it in menu.items:
            for a in {it.name, *it.aliases}:
                stems = [stem(w) for w in tokenize(a.replace("-", " "))]
                if not stems:
                    continue
                self._aliases.append((it.id, stems))
                for s in stems:
                    self._stem_items.setdefault(s, set()).add(it.id)
        self._item_vocab = list(self._stem_items)

        self._stem_mod: dict[str, str] = {}
        for m in menu.modifiers:
            for a in {m.name, *m.aliases}:
                for w in tokenize(a):
                    self._stem_mod[stem(w)] = m.id
        self._mod_vocab = list(self._stem_mod)

    # ---- слова
    def _lookup(self, word: str, vocab: list[str], table: dict) -> Optional[str]:
        s = stem(word)
        if s in table:
            return s
        if len(word) >= self.FUZZY_MIN_LEN and vocab:
            hit = process.extractOne(s, vocab, scorer=fuzz.ratio, score_cutoff=self.FUZZY_CUTOFF)
            if hit:
                return hit[0]
        return None

    def item_stem(self, word: str) -> Optional[str]:
        return self._lookup(word, self._item_vocab, self._stem_items)

    def items_for_stem(self, s: str) -> set[str]:
        return self._stem_items.get(s, set())

    def is_exact_modifier(self, word: str) -> bool:
        # "с сыром" - это добавка, а не "Сырный соус"
        s = stem(word)
        return s in self._stem_mod and s not in self._stem_items

    def modifier_id(self, word: str) -> Optional[str]:
        s = self._lookup(word, self._mod_vocab, self._stem_mod)
        return self._stem_mod[s] if s else None

    # ---- упоминание (несколько подряд идущих слов) -> блюдо
    def resolve(self, stems: list[str]) -> list[str]:
        """Вернёт список лучших item_id. 1 элемент -> однозначно, >1 -> неоднозначно."""
        best: dict[str, float] = {}
        have = set(stems)
        for item_id, a_stems in self._aliases:
            matched = len(set(a_stems) & have)
            if not matched:
                continue
            score = matched * (matched / len(a_stems))
            best[item_id] = max(best.get(item_id, 0.0), score)
        if not best:
            return []
        top = max(best.values())
        return sorted(i for i, v in best.items() if abs(v - top) < 1e-9)
