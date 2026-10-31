"""Быстрый детерминированный парсер ru/kk -> Command.

Идея: токенизация -> классификация токенов -> разбиение на сегменты по глаголам
(«убери колу и добавь воду») -> сборка Command из упоминаний блюд и атрибутов.
Если что-то непонятно (лишние слова, неизвестное блюдо) — confidence снижается,
и пайплайн отдаёт фразу в LLM-fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import lexicon as L
from .menu import MenuIndex, normalize, tokenize
from .schemas import (CartContext, Changes, Command, Intent, ItemSpec, LineRef,
                      ModifierOp, Size)

L.STOP.discard("еще")


@dataclass
class Tok:
    w: str
    kind: str
    val: Any = None


@dataclass
class Mention:
    stems: list[str]
    raw: list[str]
    cands: set[str]
    qty: Optional[int] = None
    size: Optional[Size] = None
    ordn: Any = None                       # int | "last" | None
    mods: list[ModifierOp] = field(default_factory=list)
    dest: bool = False                     # «в бургер», «колаға» — к чему добавляем


@dataclass
class Loose:
    qty: Optional[int] = None
    size: Optional[Size] = None
    ordn: Any = None
    mods: list[ModifierOp] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.qty or self.size or self.ordn or self.mods)


def detect_lang(text: str) -> str:
    return "kk" if any(ch in L.KK_LETTERS for ch in text.lower()) else "ru"


# ------------------------------------------------------------ классификация
def classify(words: list[str], idx: MenuIndex) -> list[Tok]:
    toks: list[Tok] = []
    n = len(words)
    for i, w in enumerate(words):
        prev = words[i - 1] if i else ""
        nxt = words[i + 1] if i + 1 < n else ""
        if w in L.CONJ:
            toks.append(Tok(w, "conj"))
        elif w.isdigit():
            toks.append(Tok(w, "num", int(w)))
        elif w in L.NUMBERS:
            toks.append(Tok(w, "num", L.NUMBERS[w]))
        elif L.ordinal(w) is not None:
            toks.append(Tok(w, "ord", L.ordinal(w)))
        elif w in L.ALL_WORDS:
            toks.append(Tok(w, "all"))
        elif w == "не" and nxt in L.NEG_NEXT:
            toks.append(Tok(w, "v_remove"))
        elif prev == "не" and w in L.NEG_NEXT:
            toks.append(Tok(w, "stop"))
        elif w in L.KK_NEG_PRE and nxt == "емес":
            toks.append(Tok(w, "v_remove"))
        elif L.size_of(w):
            toks.append(Tok(w, "size", L.size_of(w)))
        elif w in L.WITHOUT:
            toks.append(Tok(w, "without"))
        elif w.startswith(L.MODIFY_STEMS):
            toks.append(Tok(w, "v_modify", "replace" if w.startswith(L.REPLACE_STEMS) else None))
        elif w.startswith(L.REMOVE_STEMS):
            toks.append(Tok(w, "v_remove"))
        elif w.startswith(L.ADD_STEMS) or w in L.ADD_EXACT:
            toks.append(Tok(w, "v_add"))
        elif w in L.STOP:
            toks.append(Tok(w, "stop"))
        else:
            s = idx.item_stem(w)
            if s:
                toks.append(Tok(w, "item", s))
                continue
            neg = False
            base = w
            if len(w) > 5 and w.endswith(("сыз", "сіз")):      # «пиязсыз» = без лука
                base, neg = w[:-3], True
            m = idx.modifier_id(base)
            if m:
                toks.append(Tok(w, "mod", (m, neg)))
            else:
                toks.append(Tok(w, "other"))
    return toks


# ------------------------------------------------------------ сегментация
def _verb_intent(t: Tok) -> Optional[str]:
    return {"v_add": "add", "v_remove": "remove", "v_modify": "modify"}.get(t.kind)


def split_segments(toks: list[Tok]) -> list[list[Tok]]:
    verbs = [(i, _verb_intent(t)) for i, t in enumerate(toks) if _verb_intent(t)]
    cuts: list[int] = []
    for (p1, i1), (p2, i2) in zip(verbs, verbs[1:]):
        if i1 == i2:
            continue
        if p2 - 1 > p1 and toks[p2 - 1].kind == "conj":
            cuts.append(p2 - 1)
            continue
        conj = next((j for j in range(p1 + 1, p2) if toks[j].kind == "conj"), None)
        cuts.append(conj if conj is not None else p2)
    segs, start = [], 0
    for c in cuts:
        segs.append(toks[start:c])
        start = c + 1 if toks[c].kind == "conj" else c
    segs.append(toks[start:])
    return [s for s in segs if s]


# ------------------------------------------------------------ сегмент -> Command(s)
def _forward(seg: list[Tok], i: int) -> bool:
    """Относится ли атрибут seg[i] к СЛЕДУЮЩЕМУ блюду («большую колу», «два комбо»)?"""
    for j in range(i + 1, len(seg)):
        k = seg[j].kind
        if k == "item":
            return True
        if k in ("conj", "v_add", "v_remove", "v_modify", "without"):
            return False
    return False


def _collect(seg: list[Tok], idx: MenuIndex):
    mentions: list[Mention] = []
    loose = Loose()
    pre = Loose()
    cur: Optional[Mention] = None
    neg = False
    leftover: list[str] = []

    def put(target, tok: Tok):
        if tok.kind == "num":
            target.qty = tok.val
        elif tok.kind == "size":
            target.size = tok.val
        elif tok.kind == "ord":
            target.ordn = tok.val

    for i, t in enumerate(seg):
        if t.kind == "item":
            if cur and seg[i - 1].kind == "item" and (cur.cands & idx.items_for_stem(t.val)):
                cur.stems.append(t.val)
                cur.raw.append(t.w)
                cur.cands |= idx.items_for_stem(t.val)
            else:
                cur = Mention([t.val], [t.w], set(idx.items_for_stem(t.val)),
                              pre.qty, pre.size, pre.ordn, list(pre.mods))
                cur.dest = (i > 0 and seg[i - 1].w in ("в", "во")) or t.w.endswith(("ға", "ге", "қа", "ке"))
                mentions.append(cur)
                pre = Loose()
            neg = False
        elif t.kind in ("num", "size", "ord"):
            if _forward(seg, i):
                put(pre, t)
            else:
                put(cur if cur else loose, t)
        elif t.kind == "without":
            neg = True
        elif t.kind == "mod":
            mod_id, suffix_neg = t.val
            op = ModifierOp(modifier_id=mod_id, op="remove" if (neg or suffix_neg) else "add")
            (cur if cur else loose).mods.append(op)
        elif t.kind == "other":
            leftover.append(t.w)
    if not pre.empty():       # атрибут «в никуда» («два» в конце) -> в loose
        loose = pre if loose.empty() else loose
    return mentions, loose, leftover


def _spec(m: Mention, ids: list[str]) -> ItemSpec:
    one = len(ids) == 1
    return ItemSpec(
        menu_item_id=ids[0] if one else None,
        candidates=[] if one else ids,
        raw_text=" ".join(m.raw),
        quantity=m.qty or 1,
        size=m.size,
        modifiers=m.mods,
    )


def _ref(ids: list[str], ordn) -> LineRef:
    return LineRef(
        ordinal=ordn if isinstance(ordn, int) else None,
        is_last=(ordn == "last"),
        menu_item_id=ids[0] if len(ids) == 1 else None,
        candidates=ids if len(ids) > 1 else [],
    )


def _segment_commands(seg: list[Tok], idx: MenuIndex, cart: Optional[CartContext]) -> list[Command]:
    mentions, loose, leftover = _collect(seg, idx)
    kinds = {t.kind for t in seg}
    replace = any(t.kind == "v_modify" and t.val == "replace" for t in seg)
    resolved = [(m, idx.resolve(m.stems)) for m in mentions]
    conf = 0.95 if not leftover else 0.6
    issues = [f"unrecognized:{w}" for w in leftover]

    if "v_modify" in kinds:
        intent = "modify"
    elif "v_remove" in kinds:
        intent = "remove"
    elif "v_add" in kinds:
        intent = "add"
    else:
        intent = None

    has_target = bool(resolved) or loose.ordn is not None
    mods_only = (not resolved) and loose.ordn is None and loose.mods

    # без глагола: «колу большую» -> modify, если блюдо уже в корзине; «без лука» -> modify
    if intent is None:
        in_cart = {l.menu_item_id for l in cart.lines} if cart else set()
        if resolved:
            attrs = any(m.size or m.mods for m, _ in resolved)
            if attrs and all(ids and ids[0] in in_cart for _, ids in resolved) and not any(
                    m.qty for m, _ in resolved):
                intent = "modify"
            else:
                intent = "add"
        elif not loose.empty() and not loose.qty and loose.ordn is None:
            intent = "modify"
        else:
            return []

    if intent == "remove" and mods_only:
        intent = "modify"                      # «убери лук» = без лука
        for mo in loose.mods:
            mo.op = "remove"
    if intent == "add" and mods_only:
        intent = "modify"                      # «добавь сыр»
    if intent == "add" and resolved and any(m.dest for m, _ in resolved) and (
            loose.mods or any(m.mods for m, _ in resolved)):
        intent = "modify"                      # «добавь сыр в бургер», «колаға мұз қос»

    # ---------------------------------------------------------------- add
    if intent == "add":
        if not resolved:
            return [Command(intent=Intent.unknown, confidence=0.3, issues=issues or ["no_item"])]
        items = []
        for m, ids in resolved:
            if not ids:
                issues.append(f"unknown_item:{' '.join(m.raw)}")
                continue
            if len(ids) > 1:
                issues.append(f"ambiguous_item:{' '.join(m.raw)}")
            items.append(_spec(m, ids))
        if not items:
            return [Command(intent=Intent.unknown, confidence=0.3, issues=issues)]
        return [Command(intent=Intent.add, items=items, confidence=conf, issues=issues)]

    # ---------------------------------------------------------------- remove
    if intent == "remove":
        if resolved:
            out = []
            for m, ids in resolved:
                iss = list(issues)
                if len(ids) > 1:
                    iss.append(f"ambiguous_item:{' '.join(m.raw)}")
                out.append(Command(intent=Intent.remove, target=_ref(ids, m.ordn),
                                   quantity=m.qty, confidence=conf, issues=iss))
            return out
        iss = list(issues)
        if loose.ordn is None:
            iss.append("no_target")
        return [Command(intent=Intent.remove, target=_ref([], loose.ordn),
                        quantity=loose.qty, confidence=conf, issues=iss)]

    # ---------------------------------------------------------------- modify
    if replace and len(resolved) >= 2:
        (m0, ids0), (m1, ids1) = resolved[0], resolved[1]
        return [Command(intent=Intent.modify, target=_ref(ids0, m0.ordn),
                        changes=Changes(replace_with=_spec(m1, ids1)),
                        confidence=conf, issues=issues)]

    if resolved:
        out = []
        for m, ids in resolved:
            iss = list(issues)
            if len(ids) > 1:
                iss.append(f"ambiguous_item:{' '.join(m.raw)}")
            ch = Changes(size=m.size or loose.size, quantity=m.qty or loose.qty,
                         modifiers=m.mods + loose.mods)
            out.append(Command(intent=Intent.modify, target=_ref(ids, m.ordn or loose.ordn),
                               changes=ch, confidence=conf, issues=iss))
        return out

    ch = Changes(size=loose.size, quantity=loose.qty, modifiers=loose.mods)
    iss = list(issues)
    if not (ch.size or ch.quantity or ch.modifiers):
        iss.append("empty_modify")
    return [Command(intent=Intent.modify, target=_ref([], loose.ordn), changes=ch,
                    confidence=conf if "empty_modify" not in iss else 0.3, issues=iss)]


# ------------------------------------------------------------ вход
def parse(text: str, idx: MenuIndex, cart: Optional[CartContext] = None) -> list[Command]:
    norm = normalize(text)
    lang = detect_lang(text)
    toks = classify(norm.split(), idx)
    kinds = {t.kind for t in toks}
    has_target = bool(kinds & {"item", "ord", "mod"})

    def done(cmds: list[Command]) -> list[Command]:
        for c in cmds:
            c.text, c.lang = text, lang
        return cmds

    # 1) отмена всего заказа / подтверждение — только если нет ссылки на конкретную позицию
    if not has_target:
        if L.CANCEL_RE.search(norm) or ("v_remove" in kinds and "all" in kinds):
            return done([Command(intent=Intent.cancel, confidence=0.95)])
        if L.CONFIRM_RE.search(norm) and not (kinds & {"v_remove", "v_modify", "size", "num"}):
            return done([Command(intent=Intent.confirm, confidence=0.95)])

    # 2) остальное
    cmds: list[Command] = []
    for seg in split_segments(toks):
        cmds.extend(_segment_commands(seg, idx, cart))
    if not cmds:
        cmds = [Command(intent=Intent.unknown, confidence=0.1, issues=["not_understood"])]
    return done(cmds)
