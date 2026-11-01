// Mock-бэкенд: NLU на правилах + детерминированная Cart State Machine.
// Тот же контракт, что у FastAPI: { reply, lang, actions, cart, pending, latency_ms }.
// Цены и валидация считаются только кодом.

import { MENU, ITEM, MODIFIERS, SIZE_LABELS, COMBO_DRINK_IDS, COMBO_UPSIZE_L, GROUPS, CATEGORIES } from './menu.js'

const L = 'a-zа-яәғқңөұүһі'
const LETTER = `[${L}]`
const KZ_RE = /[әғқңөұүһі]|растай|рақмет|алып|қыл|(?<![а-я])(керек|тағы|жоқ|иә|бер|қос)(?![а-я])/
const RU_RE = /[ыэъ]|подтвер|убер|добав|сдела|хочу|дайте|верно/

const norm = (s) =>
  s.toLowerCase().replace(/ё/g, 'е').replace(/[«»"!?.:()]/g, ' ').replace(/\s+/g, ' ').trim()
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// ---------- словари ----------
const NUM = {
  один: 1, одну: 1, одна: 1, одно: 1, одного: 1, пару: 2, два: 2, две: 2, двух: 2,
  три: 3, трех: 3, четыре: 4, пять: 5, шесть: 6,
  бір: 1, екі: 2, үш: 3, төрт: 4, бес: 5, алты: 6,
}
const ORD_PREFIX = [
  ['перв', 0], ['втор', 1], ['трет', 2], ['четверт', 3],
  ['бірінші', 0], ['екінші', 1], ['үшінші', 2], ['төртінші', 3], ['бесінші', 4],
  ['последн', -1], ['соңғы', -1],
]
const SIZE_RE = {
  S: /маленьк|мален|small|кіші/,
  M: /средн|medium|орта/,
  L: /больш|large|үлкен|макси/,
}
const MOD_RULES = [
  { id: 'cheese_sauce', add: /сырн\S* соус|соус сырн|ірімшік соус/, rem: /без сырн/ },
  { id: 'no_onion', add: /без лук|пиязсыз|без пияз|лук не (надо|нужн)/ },
  { id: 'extra_cheese', add: /доп\S* сыр|двойн\S* сыр|с сыром|больше сыра|экстра сыр|ірімшік қос|қосымша ірімшік/, rem: /без (доп\S* )?сыр/ },
  { id: 'bacon', add: /бекон/, rem: /без бекон|беконсыз|бекон не/ },
  { id: 'spicy', add: /остр|ащы/, rem: /без остр|не остр|ащысыз/ },
  { id: 'no_ice', add: /без льда|без лед|мұзсыз/ },
]
const RE = {
  cancel: /отмен|очист|сброс|заново|бас тарт|тазала|болдырма/,
  confirm: /подтвер|оформ|все верно|все правильно|это все|заказываю|растаймын|растау|дұрыс|болды|тапсырыс бер/,
  remove: /убер|удал|убра|не надо|не нужн|минус|алып таст|алып таста|алыңыз|керек емес|алып тастаңыз|алма(ңыз)?$/,
  modify: /сдела|помен|замен|измен|пусть|вместо|ауыстыр|жаса|өзгерт|қыл/,
  all: /(?<![а-яәі])(все|оба|обе|барлық|екеуін|екеуі)(?![а-яәі])/,
}
const YES_WORDS = new Set(['да', 'ок', 'окей', 'иә', 'ия', 'конечно', 'подтверждаю'])

// ---------- поиск позиций в тексте ----------
function aliasRegex(alias) {
  const parts = alias.split(' ').map((w) =>
    w.startsWith('=') ? `${esc(w.slice(1))}(?!${LETTER})` : `${esc(w)}${LETTER}*`
  )
  return new RegExp(`(?<!${LETTER})${parts.join('[\\s-]+')}`, 'g')
}
const MATCHERS = [
  ...MENU.flatMap((it) => it.aliases.map((a) => ({ re: aliasRegex(a), stem: a.length, itemId: it.id }))),
  ...Object.entries(GROUPS).flatMap(([g, v]) => v.aliases.map((a) => ({ re: aliasRegex(a), stem: a.length, group: g }))),
]

function findMentions(text) {
  const all = []
  for (const m of MATCHERS) {
    m.re.lastIndex = 0
    let r
    while ((r = m.re.exec(text))) {
      all.push({ start: r.index, end: r.index + r[0].length, stem: m.stem, itemId: m.itemId, group: m.group })
    }
  }
  all.sort((a, b) => b.end - b.start - (a.end - a.start) || b.stem - a.stem)
  const picked = []
  for (const m of all) if (!picked.some((p) => m.start < p.end && p.start < m.end)) picked.push(m)
  return picked.sort((a, b) => a.start - b.start)
}
const mask = (text, mentions) =>
  mentions.reduce((t, m) => t.slice(0, m.start) + ' '.repeat(m.end - m.start) + t.slice(m.end), text)
const tokens = (s) => s.split(/[^0-9a-zа-яәғқңөұүһі]+/).filter(Boolean)

function numberBefore(text, pos) {
  const tk = tokens(text.slice(0, pos)).slice(-2).reverse()
  for (const t of tk) {
    if (/^\d+$/.test(t)) return parseInt(t, 10)
    if (NUM[t]) return NUM[t]
  }
  return null
}
function anyNumber(text) {
  for (const t of tokens(text)) {
    if (/^\d+$/.test(t) && +t < 20) return +t
    if (NUM[t]) return NUM[t]
  }
  return null
}
function detectOrdinal(text) {
  const tk = tokens(text)
  for (let i = 0; i < tk.length; i++) {
    const t = tk[i]
    if (/^\d+$/.test(t) && (/^(номер|позиц|пункт|строк)/.test(tk[i - 1] || '') || /^позиц/.test(tk[i + 1] || ''))) return +t - 1
    if (/^пят(ое|ой|ую|ый|ая|ого)/.test(t)) return 4
    for (const [p, idx] of ORD_PREFIX) if (t.startsWith(p)) return idx
  }
  const m = text.match(/(\d+)\s*-\s*(е|ю|й|ую|ое|ой|ші|шы|ші)(?![а-яәғқңөұүһі])/)
  if (m) return +m[1] - 1
  return null
}
const detectSize = (t) => (SIZE_RE.L.test(t) ? 'L' : SIZE_RE.S.test(t) ? 'S' : SIZE_RE.M.test(t) ? 'M' : null)
function detectMods(t) {
  const add = [], remove = []
  for (const r of MOD_RULES) {
    if (r.rem && r.rem.test(t)) remove.push(r.id)
    else if (r.add.test(t)) add.push(r.id)
  }
  return { add, remove }
}

// ---------- тексты ответов ----------
const T = {
  ru: {
    added: (s) => `Добавил: ${s}.`,
    removed: (s) => `Убрал: ${s}.`,
    changed: (s) => `Изменил: ${s}.`,
    unavailable: (n) => `${n} сейчас нет в наличии.`,
    noSize: (n) => `У позиции "${n}" нет выбора размера.`,
    badSize: (n, s) => `${n} не бывает размера ${s}.`,
    badMod: (m, n) => `К позиции "${n}" нельзя добавить: ${m}.`,
    notFound: 'Не нашёл такую позицию в корзине.',
    askRemove: 'Что именно убрать? Назовите позицию или её номер.',
    chooseItem: (q, opts) => `${q} Есть: ${opts}.`,
    comboDrink: (n, opts) => (n > 1 ? `Какие напитки в комбо (${n} шт)? На выбор: ${opts}.` : `Какой напиток в комбо? На выбор: ${opts}.`),
    cancelled: 'Заказ отменён, корзина пуста.',
    confirmed: (t) => `Заказ подтверждён! К оплате ${t} ₸. Спасибо!`,
    empty: 'Корзина пока пустая. Что будем заказывать?',
    needDetails: 'Перед подтверждением нужно уточнить детали.',
    tail: (t) => `Итого ${t} ₸. Что-нибудь ещё или подтверждаем?`,
    unknown: 'Не понял. Скажите, например: "два комбо классик" или "колу сделай большой".',
    replaced: (a, b) => `${a} заменил на ${b}.`,
    drinkFor: (d) => `напиток в комбо: ${d}`,
  },
  kz: {
    added: (s) => `Қостым: ${s}.`,
    removed: (s) => `Алып тастадым: ${s}.`,
    changed: (s) => `Өзгерттім: ${s}.`,
    unavailable: (n) => `${n} қазір жоқ.`,
    noSize: (n) => `"${n}" өлшемі таңдалмайды.`,
    badSize: (n, s) => `${n} үшін ${s} өлшемі жоқ.`,
    badMod: (m, n) => `"${n}" үшін қосуға болмайды: ${m}.`,
    notFound: 'Себеттен ондай позиция таппадым.',
    askRemove: 'Нені алып тастау керек? Атауын немесе нөмірін айтыңыз.',
    chooseItem: (q, opts) => `${q} Бар: ${opts}.`,
    comboDrink: (n, opts) => (n > 1 ? `Комбоға қандай сусындар (${n} дана)? Таңдау: ${opts}.` : `Комбоға қандай сусын? Таңдау: ${opts}.`),
    cancelled: 'Тапсырыс болдырылмады, себет бос.',
    confirmed: (t) => `Тапсырыс расталды! Төлемге ${t} ₸. Рақмет!`,
    empty: 'Себет әзірге бос. Не тапсырыс бересіз?',
    needDetails: 'Растамас бұрын нақтылау керек.',
    tail: (t) => `Барлығы ${t} ₸. Тағы бірдеңе ме, әлде растаймыз ба?`,
    unknown: 'Түсінбедім. Мысалы: "екі классик комбо" немесе "колды үлкен қыл".',
    replaced: (a, b) => `${a} орнына ${b}.`,
    drinkFor: (d) => `комбодағы сусын: ${d}`,
  },
}
const fmt = (n) => n.toLocaleString('ru-RU').replace(/ /g, ' ')

// ---------- корзина ----------
function priceLine(line) {
  const it = ITEM[line.itemId]
  let unit = it.sizes ? it.sizes[line.size] : it.price
  unit += line.mods.reduce((s, m) => s + MODIFIERS[m].price, 0)
  if (it.cat === 'combo' && line.drinkSize === 'L') unit += COMBO_UPSIZE_L
  return { unit, total: unit * line.qty }
}
function lineLabel(line, lang) {
  const it = ITEM[line.itemId]
  let s = `${line.qty > 1 ? line.qty + '× ' : ''}${it[lang]}`
  if (it.sizes) s += ` (${SIZE_LABELS[line.size][lang]})`
  if (line.mods.length) s += `, ${line.mods.map((m) => MODIFIERS[m][lang]).join(', ')}`
  if (it.cat === 'combo' && line.drink) s += ` + ${ITEM[line.drink][lang]}${line.drinkSize === 'L' ? ' ' + SIZE_LABELS.L[lang] : ''}`
  return s
}

export function createSession() {
  return { lines: [], nextId: 1, status: 'open', pending: null, lastLineId: null, stats: { turns: 0, clarifications: 0 } }
}

function cartView(s, lang) {
  const lines = s.lines.map((l, i) => {
    const it = ITEM[l.itemId]
    const p = priceLine(l)
    return {
      position: i + 1,
      line_id: l.id,
      item_id: l.itemId,
      name: it[lang],
      category: it.cat,
      qty: l.qty,
      size: l.size || null,
      size_label: l.size ? SIZE_LABELS[l.size][lang] : null,
      modifiers: l.mods.map((m) => ({ id: m, name: MODIFIERS[m][lang], price: MODIFIERS[m].price })),
      drink: l.drink ? { id: l.drink, name: ITEM[l.drink][lang], size: l.drinkSize || 'M' } : null,
      needs_drink: it.cat === 'combo' && !l.drink,
      unit_price: p.unit,
      line_total: p.total,
    }
  })
  return { lines, total: lines.reduce((a, l) => a + l.line_total, 0), status: s.status }
}

// ---------- обработка одной реплики ----------
export function handleMessage(s, rawText, forceLang) {
  const t0 = performance.now()
  const text = norm(rawText)
  const lang = forceLang || (KZ_RE.test(text) ? 'kz' : RU_RE.test(text) ? 'ru' : s.lang || 'ru')
  s.lang = lang
  const tr = T[lang]
  const out = [] // фразы ответа
  const actions = [] // структурированные намерения для UI/метрик
  let question = null
  s.stats.turns++

  if (s.status === 'confirmed' || s.status === 'cancelled') {
    if (!RE.confirm.test(text)) { s.lines = []; s.status = 'open'; s.pending = null }
  }

  const findTarget = (mention, ordinal, all) => {
    let pool = s.lines
    let viaCombo = false
    if (mention) {
      pool = s.lines.filter((l) => (mention.itemId ? l.itemId === mention.itemId : ITEM[l.itemId].group === mention.group))
      if (!pool.length && mention.itemId && COMBO_DRINK_IDS.includes(mention.itemId)) {
        pool = s.lines.filter((l) => l.drink === mention.itemId)
        viaCombo = pool.length > 0
      }
    }
    if (!pool.length) return { lines: [], viaCombo }
    if (all) return { lines: pool, viaCombo }
    if (ordinal != null) {
      const l = ordinal === -1 ? pool[pool.length - 1] : pool[ordinal]
      return { lines: l ? [l] : [], viaCombo }
    }
    if (!mention) {
      const last = s.lines.find((l) => l.id === s.lastLineId) || s.lines[s.lines.length - 1]
      return { lines: last ? [last] : [], viaCombo }
    }
    return { lines: [pool[pool.length - 1]], viaCombo }
  }

  const askComboDrink = () => {
    const missing = s.lines.filter((l) => ITEM[l.itemId].cat === 'combo' && !l.drink)
    if (!missing.length) { if (s.pending?.type === 'combo_drink') s.pending = null; return }
    s.pending = { type: 'combo_drink', line_ids: missing.map((l) => l.id) }
    question = tr.comboDrink(missing.length, COMBO_DRINK_IDS.map((d) => ITEM[d][lang]).join(', '))
  }

  const addItem = (itemId, qty, size, mods, drink, drinkSize) => {
    const it = ITEM[itemId]
    if (!it.available) { out.push(tr.unavailable(it[lang])); actions.push({ intent: 'add', item: itemId, ok: false, reason: 'unavailable' }); return }
    let sz = null
    if (it.sizes) {
      sz = size && it.sizes[size] ? size : it.defaultSize
      if (size && !it.sizes[size]) out.push(tr.badSize(it[lang], SIZE_LABELS[size][lang]))
    }
    const okMods = []
    for (const m of mods) {
      if (it.mods.includes(m)) okMods.push(m)
      else out.push(tr.badMod(MODIFIERS[m][lang], it[lang]))
    }
    if (it.cat === 'combo') {
      for (let i = 0; i < qty; i++) {
        const l = { id: s.nextId++, itemId, qty: 1, size: null, mods: [...okMods], drink: drink || null, drinkSize: drink ? drinkSize || 'M' : null }
        s.lines.push(l); s.lastLineId = l.id
      }
    } else {
      const same = s.lines.find((l) => l.itemId === itemId && l.size === sz && l.mods.join() === [...okMods].sort().join())
      if (same) { same.qty += qty; s.lastLineId = same.id }
      else { const l = { id: s.nextId++, itemId, qty, size: sz, mods: okMods.sort(), drink: null, drinkSize: null }; s.lines.push(l); s.lastLineId = l.id }
    }
    const preview = { itemId, qty, size: sz, mods: okMods, drink, drinkSize }
    out.push(tr.added(lineLabel(preview, lang)))
    actions.push({ intent: 'add', item: itemId, qty, size: sz, modifiers: okMods, drink: drink || null, ok: true })
  }

  // --- 1. ответ на уточнение ---
  let consumed = false
  if (s.pending) {
    const mentions = findMentions(text)
    if (s.pending.type === 'choose_item') {
      const opts = MENU.filter((i) => i.group === s.pending.group && i.available !== false)
      let pick = mentions.find((m) => m.itemId && ITEM[m.itemId].group === s.pending.group)?.itemId
      if (!pick) {
        // короткий ответ: "чикен", "биг" - ищем по ключевым словам вариантов группы
        const groupWords = new Set(GROUPS[s.pending.group].aliases)
        pick = opts.find((o) => o.aliases.some((a) => a.split(' ').some((w) => {
          const stem = w.replace('=', '')
          return !groupWords.has(stem) && stem.length > 2 && new RegExp(`(?<!${LETTER})${esc(stem)}`).test(text)
        })))?.id
      }
      if (!pick && !mentions.length) { const o = detectOrdinal(text); if (o != null) pick = opts[o === -1 ? opts.length - 1 : o]?.id }
      if (pick) {
        const p = s.pending; s.pending = null; consumed = true
        const drinkM = mentions.find((m) => m.itemId && COMBO_DRINK_IDS.includes(m.itemId))
        addItem(pick, p.qty, p.size, p.mods, ITEM[pick].cat === 'combo' ? drinkM?.itemId : null, detectSize(mask(text, mentions)))
        actions.push({ intent: 'clarify_answer', choice: pick })
      }
    } else if (s.pending.type === 'combo_drink') {
      const drinks = mentions.filter((m) => m.itemId && COMBO_DRINK_IDS.includes(m.itemId))
      const hasOther = mentions.some((m) => !drinks.includes(m)) || RE.remove.test(text) || RE.cancel.test(text)
      if (drinks.length && !hasOther) {
        consumed = true
        const targets = s.pending.line_ids.map((id) => s.lines.find((l) => l.id === id)).filter(Boolean)
        targets.forEach((l, i) => {
          const m = drinks[Math.min(i, drinks.length - 1)]
          const seg = text.slice(i === 0 ? 0 : drinks[Math.min(i, drinks.length - 1) - 1]?.end ?? 0, m.end)
          l.drink = m.itemId
          l.drinkSize = detectSize(seg) === 'L' || (drinks.length === 1 && detectSize(text) === 'L') ? 'L' : 'M'
        })
        out.push(tr.changed(targets.map((l) => lineLabel(l, lang)).join('; ')))
        actions.push({ intent: 'clarify_answer', drinks: drinks.map((d) => d.itemId) })
        s.pending = null
        askComboDrink()
      }
    }
  }

  // --- 2. обычная обработка по фразам ---
  if (!consumed) {
    const words = tokens(text)
    if (words.length <= 2 && words.every((w) => YES_WORDS.has(w))) {
      handleConfirm()
    } else {
      const clauses = text.split(/\s*(?:,|;|\sи\s|\sа\s|\sжәне\s|\sещ[её]\s|\sтағы\s|\sпотом\s|\sплюс\s)\s*/).filter(Boolean)
      for (const c of clauses) handleClause(c)
    }
  }

  function handleConfirm() {
    if (!s.lines.length) { out.push(tr.empty); return }
    askComboDrink()
    if (s.pending) { out.push(tr.needDetails); return }
    s.status = 'confirmed'
    const total = cartView(s, lang).total
    out.push(tr.confirmed(fmt(total)))
    actions.push({ intent: 'confirm', total })
  }

  function handleClause(c) {
    const mentions = findMentions(c)
    const masked = mask(c, mentions)
    const ordinal = detectOrdinal(masked)
    const size = detectSize(masked)
    const mods = detectMods(masked)
    const hasMods = mods.add.length + mods.remove.length > 0
    const all = RE.all.test(masked)
    const first = mentions[0] || null

    if (RE.cancel.test(masked) && !first && ordinal == null) {
      s.lines = []; s.pending = null; s.status = 'cancelled'
      out.push(tr.cancelled); actions.push({ intent: 'cancel' }); return
    }
    if (RE.confirm.test(masked) && !first) { handleConfirm(); return }

    const isRemove = RE.remove.test(masked) && !(hasMods && !first && ordinal == null)
    if (isRemove) {
      if (!first && ordinal == null) { question = tr.askRemove; s.stats.clarifications++; return }
      const { lines, viaCombo } = findTarget(first, ordinal, all)
      if (!lines.length) { out.push(tr.notFound); actions.push({ intent: 'remove', ok: false }); return }
      const n = first ? numberBefore(c, first.start) : null
      for (const l of lines) {
        if (viaCombo) { l.drink = null; l.drinkSize = null; out.push(tr.removed(lineLabel(l, lang))); continue }
        if (n && l.qty > n && !all) { l.qty -= n; out.push(tr.removed(`${n}× ${ITEM[l.itemId][lang]}`)) }
        else { s.lines = s.lines.filter((x) => x !== l); out.push(tr.removed(lineLabel(l, lang))) }
        actions.push({ intent: 'remove', item: l.itemId, line_id: l.id, ok: true })
      }
      if (s.pending?.type === 'combo_drink') askComboDrink()
      return
    }

    const isModify = RE.modify.test(masked) || (!first && (size || hasMods || ordinal != null))
    if (isModify) {
      // замена позиции: "колу замени на спрайт", "вместо колы спрайт"
      let target = first, replacement = null
      if (mentions.length >= 2) {
        const vi = masked.indexOf('вместо') >= 0 ? masked.indexOf('вместо') : masked.indexOf('орнына')
        if (vi >= 0 && masked.indexOf('вместо') >= 0) {
          target = mentions.find((m) => m.start > vi) || mentions[0]
          replacement = mentions.find((m) => m !== target)
        } else if (vi >= 0) { // каз: "колдың орнына спрайт" - объект до орнына
          target = [...mentions].reverse().find((m) => m.end <= vi) || mentions[0]
          replacement = mentions.find((m) => m !== target)
        } else { target = mentions[0]; replacement = mentions[1] }
      }
      const { lines, viaCombo } = findTarget(target, ordinal, all)
      if (!lines.length) { out.push(tr.notFound); actions.push({ intent: 'modify', ok: false }); return }
      for (const l of lines) {
        const before = lineLabel(l, lang)
        const it = ITEM[l.itemId]
        if (replacement?.itemId) {
          const nit = ITEM[replacement.itemId]
          if (!nit.available) { out.push(tr.unavailable(nit[lang])); continue }
          if (viaCombo || (it.cat === 'combo' && COMBO_DRINK_IDS.includes(nit.id))) { l.drink = nit.id; if (size) l.drinkSize = size === 'L' ? 'L' : 'M' }
          else if (nit.cat === 'combo' && it.cat !== 'combo') { out.push(tr.notFound); continue }
          else {
            l.itemId = nit.id
            l.size = nit.sizes ? (size && nit.sizes[size] ? size : nit.sizes[l.size] ? l.size : nit.defaultSize) : null
            l.mods = l.mods.filter((m) => nit.mods.includes(m))
          }
          out.push(tr.replaced(before, lineLabel(l, lang)))
          actions.push({ intent: 'modify', op: 'replace', line_id: l.id, from: it.id, to: nit.id, ok: true })
          s.lastLineId = l.id
          continue
        }
        if (size) {
          if (viaCombo || it.cat === 'combo') l.drinkSize = size === 'L' ? 'L' : 'M'
          else if (!it.sizes) out.push(tr.noSize(it[lang]))
          else if (!it.sizes[size]) out.push(tr.badSize(it[lang], SIZE_LABELS[size][lang]))
          else l.size = size
        }
        for (const m of mods.add) {
          if (viaCombo && m !== 'no_ice') continue
          if (!it.mods.includes(m)) out.push(tr.badMod(MODIFIERS[m][lang], it[lang]))
          else if (!l.mods.includes(m)) l.mods.push(m)
        }
        l.mods = l.mods.filter((m) => !mods.remove.includes(m)).sort()
        const n = anyNumber(masked)
        if (n && it.cat !== 'combo' && ordinal == null) l.qty = n
        const after = lineLabel(l, lang)
        if (after !== before) out.push(tr.changed(after))
        actions.push({ intent: 'modify', line_id: l.id, size, modifiers_add: mods.add, modifiers_remove: mods.remove, ok: after !== before })
        s.lastLineId = l.id
      }
      return
    }

    if (mentions.length) {
      const combo = mentions.find((m) => m.itemId && ITEM[m.itemId].cat === 'combo')
      mentions.forEach((m, i) => {
        // напиток рядом с комбо в той же фразе идёт в комбо
        if (combo && m !== combo && m.itemId && COMBO_DRINK_IDS.includes(m.itemId)) return
        const segStart = i === 0 ? 0 : mentions[i - 1].end
        const segEnd = i === mentions.length - 1 ? c.length : mentions[i + 1].start
        const seg = mask(c.slice(segStart, segEnd), mentions.map((x) => ({ ...x, start: x.start - segStart, end: x.end - segStart })).filter((x) => x.start >= 0 && x.end <= segEnd - segStart))
        const qty = numberBefore(c, m.start) || 1
        const sz = detectSize(seg)
        const md = detectMods(seg)
        if (m.group) {
          s.pending = { type: 'choose_item', group: m.group, qty, size: sz, mods: md.add }
          s.stats.clarifications++
          const opts = MENU.filter((x) => x.group === m.group && x.available !== false).map((x) => x[lang]).join(', ')
          question = tr.chooseItem(GROUPS[m.group][lang], opts)
          actions.push({ intent: 'clarify', group: m.group, qty })
          return
        }
        let drink = null, drinkSize = null
        if (ITEM[m.itemId].cat === 'combo') {
          const d = mentions.find((x) => x.itemId && COMBO_DRINK_IDS.includes(x.itemId))
          if (d) { drink = d.itemId; drinkSize = detectSize(mask(c, mentions.filter((x) => x !== d)).slice(m.end)) === 'L' ? 'L' : 'M' }
        }
        addItem(m.itemId, qty, ITEM[m.itemId].cat === 'combo' ? null : sz, md.add, drink, drinkSize)
      })
      return
    }

    if (!question) out.push(tr.unknown)
    actions.push({ intent: 'unknown', text: c })
  }

  // уточнение по напиткам в комбо
  if (!question && s.status === 'open' && s.lines.some((l) => ITEM[l.itemId].cat === 'combo' && !l.drink)) {
    const before = s.pending
    askComboDrink()
    if (!before && s.pending) s.stats.clarifications++
  }
  if (!question && s.pending?.type === 'choose_item') {
    const opts = MENU.filter((x) => x.group === s.pending.group && x.available !== false).map((x) => x[lang]).join(', ')
    question = tr.chooseItem(GROUPS[s.pending.group][lang], opts)
  }

  const cart = cartView(s, lang)
  const parts = [...new Set(out)]
  if (question) parts.push(question)
  else if (s.status === 'open' && cart.lines.length && actions.some((a) => a.intent !== 'unknown')) parts.push(tr.tail(fmt(cart.total)))
  if (!parts.length) parts.push(tr.unknown)

  return {
    reply: parts.join(' '),
    lang,
    actions,
    cart,
    pending: s.pending,
    stats: { ...s.stats },
    latency_ms: Math.round((performance.now() - t0) * 10) / 10,
  }
}

export function menuView() {
  return {
    categories: CATEGORIES,
    items: MENU.map((i) => ({
      id: i.id, category: i.cat, name_ru: i.ru, name_kz: i.kz, desc: i.desc || null,
      price: i.price ?? null, sizes: i.sizes ?? null, available: i.available !== false,
      modifiers: i.mods.map((m) => ({ id: m, name_ru: MODIFIERS[m].ru, name_kz: MODIFIERS[m].kz, price: MODIFIERS[m].price })),
    })),
  }
}

export function createMockBackend() {
  const sessions = new Map()
  const get = (id) => { if (!sessions.has(id)) sessions.set(id, createSession()); return sessions.get(id) }
  return {
    menu: async () => menuView(),
    message: async (sessionId, text, lang) => {
      await new Promise((r) => setTimeout(r, 120)) // имитация сети
      return handleMessage(get(sessionId), text, lang)
    },
    reset: async (sessionId) => { sessions.set(sessionId, createSession()); return { ok: true } },
  }
}
