"""Контракт между NLU и Cart State Machine.

NLU НИКОГДА не меняет корзину и не считает цены. Он выдаёт только Command.
Всё остальное (наличие, допустимые модификаторы, цены, уточнение параметров
комбо) делает детерминированный код State Machine.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    add = "add"
    remove = "remove"
    modify = "modify"
    cancel = "cancel"      # отмена ВСЕГО заказа
    confirm = "confirm"
    unknown = "unknown"    # не поняли -> State Machine переспрашивает


class Size(str, Enum):
    S = "S"
    M = "M"
    L = "L"


class ModifierOp(BaseModel):
    modifier_id: str
    op: Literal["add", "remove"] = "add"   # «с сыром» -> add, «без лука» -> remove


class ItemSpec(BaseModel):
    """Позиция, которую гость хочет ДОБАВИТЬ."""
    menu_item_id: Optional[str] = None
    candidates: list[str] = Field(default_factory=list)  # если «сок» -> 2 сока
    raw_text: Optional[str] = None
    quantity: int = Field(1, ge=1, le=20)
    size: Optional[Size] = None
    modifiers: list[ModifierOp] = Field(default_factory=list)


class LineRef(BaseModel):
    """Ссылка на УЖЕ существующую строку корзины.

    - ordinal: «второе убери» -> 2 (нумерация строк корзины с 1).
      Если заданы и ordinal, и menu_item_id («второй бургер»), то ordinal
      считается среди строк этого блюда.
    - is_last: «последнее убери».
    - все поля пустые -> «неявная» ссылка, State Machine берёт строку,
      с которой гость работал последней («без лука»).
    """
    ordinal: Optional[int] = Field(None, ge=1)
    menu_item_id: Optional[str] = None
    candidates: list[str] = Field(default_factory=list)
    is_last: bool = False


class Changes(BaseModel):
    """Что изменить в строке (modify)."""
    size: Optional[Size] = None
    quantity: Optional[int] = Field(None, ge=1, le=20)
    modifiers: list[ModifierOp] = Field(default_factory=list)
    replace_with: Optional[ItemSpec] = None   # «замени колу на спрайт»


class Command(BaseModel):
    intent: Intent
    items: list[ItemSpec] = Field(default_factory=list)       # add
    target: Optional[LineRef] = None                          # remove / modify
    changes: Optional[Changes] = None                         # modify
    quantity: Optional[int] = Field(None, ge=1, le=20)        # remove: «убери одну колу»
    issues: list[str] = Field(default_factory=list)           # ambiguous_item:..., unknown_item:...
    # --- служебное, заполняет пайплайн (LLM может не возвращать) ---
    confidence: float = 1.0
    source: Literal["rules", "llm"] = "rules"
    text: str = ""
    lang: Literal["ru", "kk"] = "ru"


class CartLineView(BaseModel):
    """Срез корзины для NLU (нужен LLM-fallback и эвристикам)."""
    index: int                      # 1-based
    menu_item_id: str
    quantity: int = 1
    size: Optional[Size] = None


class CartContext(BaseModel):
    lines: list[CartLineView] = Field(default_factory=list)


class NLUResult(BaseModel):
    transcript: str
    lang: Literal["ru", "kk"] = "ru"
    commands: list[Command]
    stt_provider: Optional[str] = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
