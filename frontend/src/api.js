import { createMockBackend } from './mock/engine.js'
import BACK_MENU from './backendMenu.json'

// mock = встроенный движок, python = бэк voice_cart_nlu (FastAPI) через прокси Vite
export const MODE = import.meta.env.VITE_API_URL ? 'python' : 'mock'
export const STT_MODE = import.meta.env.VITE_STT === 'server' && MODE === 'python' ? 'server' : 'browser'

const mock = createMockBackend()
const tg = (cents) => Math.round(cents / 100)
const SIZE_RU = { S: 'маленький', M: 'средний', L: 'большой' }
const SIZE_KZ = { S: 'кіші', M: 'орта', L: 'үлкен' }
const SIZE_EN = { S: 'small', M: 'medium', L: 'large' }
const SIZES = { ru: SIZE_RU, kz: SIZE_KZ, en: SIZE_EN }
const MOD = Object.fromEntries(BACK_MENU.modifiers.map((m) => [m.id, m]))

// казахские названия: в menu.json бэка их нет, поэтому словарь на фронте (id -> название)
const KZ_ITEM = {
  burger: 'Бургер', chicken_burger: 'Тауық бургері', combo: 'Комбо', fries: 'Фри картобы', nuggets: 'Наггетстер',
  salad: 'Салат', cola: 'Кока-кола', sprite: 'Спрайт', fanta: 'Фанта', water: 'Су', juice_apple: 'Алма шырыны',
  juice_orange: 'Апельсин шырыны', latte: 'Латте', coffee: 'Кофе', tea: 'Шай', ice_cream: 'Балмұздақ',
}
const KZ_MOD = { onion: 'Пияз', cheese: 'Ірімшік', ketchup: 'Кетчуп', garlic_sauce: 'Сарымсақ соусы', mayo: 'Майонез', ice: 'Мұз', sugar: 'Қант' }
const LABELS = {
  kz: { напиток: 'сусын', гарнир: 'гарнир', размер: 'өлшем' },
  en: { напиток: 'drink', гарнир: 'side', размер: 'size' },
}
// name_kk и name_en из menu.json бэка, KZ_ITEM и KZ_MOD запасные
const ITEM = Object.fromEntries(BACK_MENU.items.map((i) => [i.id, i]))
const itemName = (id, fallback, lang) =>
  (lang === 'kz' && (ITEM[id]?.name_kk || KZ_ITEM[id])) || (lang === 'en' && ITEM[id]?.name_en) || fallback
const modName = (id, fallback, lang) =>
  (lang === 'kz' && (MOD[id]?.name_kk || KZ_MOD[id])) || (lang === 'en' && MOD[id]?.name_en) || fallback
const labelName = (l, lang) => LABELS[lang]?.[l] || l

// бэк отвечает по-русски, для en переводим известные фразы
const EN_BY_RU_NAME = Object.fromEntries([
  ...BACK_MENU.items.map((i) => [i.name.toLowerCase(), i.name_en]),
  ...BACK_MENU.modifiers.map((m) => [m.name.toLowerCase(), m.name_en]),
])
const en = (ruName) => EN_BY_RU_NAME[ruName.trim().toLowerCase()] || ruName
const enList = (list) => list.split(/, | или /).map(en).join(', ').replace(/, ([^,]*)$/, ' or $1')
const EN_NOTES = [
  [/^Такого нет в меню: «(.+)»$/, (m) => `"${m[1]}" is not on the menu`],
  [/^Не нашёл в меню: «(.+)»$/, (m) => `Couldn't find "${m[1]}" on the menu`],
  [/^Извините, «(.+)» сейчас нет в наличии$/, (m) => `Sorry, ${en(m[1])} is out of stock`],
  [/^Закончилось: (.+)\. Уберите из заказа или замените$/, (m) => `Out of stock: ${enList(m[1])}. Please remove or replace it`],
  [/^Корзина пуста, нечего подтверждать$/, () => 'Your order is empty, nothing to confirm'],
  [/^Корзина пуста$/, () => 'Your order is empty'],
  [/^Корзина очищена$/, () => 'Order cleared'],
  [/^Заказ подтверждён$/, () => 'Order confirmed'],
  [/^Сначала завершите выбор в комбо$/, () => 'Please finish choosing your combo first'],
  [/^Для «(.+)» нельзя: (.+)$/, (m) => `${en(m[1])} can't have ${en(m[2]).toLowerCase()}`],
  [/^У «(.+)» нет размеров$/, (m) => `${en(m[1])} has no sizes`],
  [/^У «(.+)» нет размера (\w)$/, (m) => `${en(m[1])} doesn't come in ${SIZE_EN[m[2]] || m[2]}`],
  [/^Такой добавки нет в меню$/, () => "We don't have that add-on"],
  [/^В корзине нет: (.+)$/, (m) => `${en(m[1])} is not in your order`],
  [/^Уточните, какой: (.+)\?$/, (m) => `Which one: ${enList(m[1])}?`],
  [/^В корзине нет позиции №(\d+)$/, (m) => `There is no item #${m[1]} in your order`],
  [/^Не понял, какую позицию изменить$/, () => 'Which item should I change?'],
  [/^Не понял, сколько штук$/, () => 'How many?'],
  [/^Не понял, какой размер$/, () => 'Which size?'],
  [/^Не понял, повторите, пожалуйста$/, () => "Sorry, I didn't catch that. Please repeat."],
  [/^Нет комбо, к которому это относится$/, () => 'There is no combo to apply this to'],
  [/^«(.+)» нельзя выбрать в «(.+)»$/, (m) => `${en(m[1])} can't be chosen for ${en(m[2])}`],
  [/^В «(.+)» нечего выбирать$/, (m) => `${en(m[1])} has no options`],
]
function toEnglish(text) {
  for (const [re, fn] of EN_NOTES) {
    const m = text.match(re)
    if (m) return fn(m)
  }
  return text
}

async function http(path, opts = {}) {
  let r
  try {
    r = await fetch(path, opts)
  } catch {
    const e = new Error('нет связи с бэком (он запущен на :8000?)')
    e.noBackend = true
    throw e
  }
  if (r.status === 204) return null
  const body = await r.json().catch(() => ({}))
  if (!r.ok) { const e = new Error(body.detail || `HTTP ${r.status}`); e.status = r.status; throw e }
  return body
}

// ---------- адаптер ответа Python-бэка -> формат UI ----------
function adaptCart(c, lang) {
  const sizes = SIZES[lang] || SIZE_RU
  const lines = (c?.lines || []).map((l) => ({
    position: l.line,
    line_id: `${l.line}-${l.item_id}`,
    item_id: l.item_id,
    name: itemName(l.item_id, l.name, lang),
    name_ru: l.name,
    qty: l.quantity,
    size: l.size || null,
    size_label: l.size ? sizes[l.size] : null,
    modifiers: l.modifiers.map((m) => ({
      id: m.id + m.op,
      name: m.op === 'remove'
        ? (lang === 'kz' ? `${modName(m.id, m.name, lang).toLowerCase()} жоқ`
          : lang === 'en' ? `no ${modName(m.id, m.name, lang).toLowerCase()}`
            : `без ${MOD[m.id]?.gen || m.name.toLowerCase()}`)
        : modName(m.id, m.name, lang),
      price: tg(m.price_cents),
    })),
    choices: l.choices.map((ch) => ({
      id: ch.id,
      text: ch.id === 'size' ? `${labelName(ch.label, lang)}: ${(SIZES[lang] || SIZE_RU)[ch.value] || ch.value}` : itemName(ch.value, ch.name, lang),
      delta: tg(ch.price_delta_cents),
    })),
    missing: l.missing.map((m) => labelName(m, lang)),
    pending: l.pending,
    unit_price: tg(l.unit_price_cents),
    line_total: tg(l.line_total_cents),
  }))
  return { lines, total: tg(c?.total_cents || 0), status: c?.status || 'open' }
}

const ACTION_INTENT = {
  add_item: 'add', remove_item: 'remove', change_quantity: 'modify', change_size: 'modify',
  add_modifier: 'modify', remove_modifier: 'modify', set_combo_choice: 'clarify_answer',
  clear_cart: 'cancel', confirm: 'confirm',
}

// варианты ответа на уточнение: из меню бэка, а не из текста вопроса
const ITEM_BY_ID = Object.fromEntries(BACK_MENU.items.map((i) => [i.id, i]))
const SIZE_WORD = SIZES
function quickReplies(r, lang) {
  if (r.cart?.status && r.cart.status !== 'open') return []
  // допродажа: одна кнопка "добавить"
  if (r.upsell && !r.question) {
    const u = r.upsell
    const add = { ru: 'Добавить', kz: 'Қосу', en: 'Add' }[lang] || 'Добавить'
    return [{
      label: `${add} ${itemName(u.item_id, u.name, lang)} · ${tg(u.price_cents)} ₸`,
      text: u.name, value: u.item_id,
      action: { type: 'add_item', item_id: u.item_id },
    }]
  }
  // неоднозначное блюдо: "сок" -> яблочный / апельсиновый
  const amb = (r.actions || []).find((a) => a.candidates?.length > 1)
  if (amb && r.question) return amb.candidates.filter((id) => ITEM_BY_ID[id]).map((id) => ({ label: itemName(id, ITEM_BY_ID[id].name, lang), text: ITEM_BY_ID[id].name }))
  const line = (r.cart?.lines || []).find((l) => l.pending)
  if (!line) return []
  const item = ITEM_BY_ID[line.item_id]
  const choice = item?.choices?.find((c) => c.label === line.missing[0]) || item?.choices?.find((c) => line.missing.includes(c.label))
  if (!choice) return []
  // action - для прямого выбора кнопкой, text - запасной вариант через NLU
  return choice.options.map((o) => {
    const label = choice.kind === 'size' ? SIZE_WORD[lang][o] : itemName(o, ITEM_BY_ID[o]?.name || o, lang)
    const text = choice.kind === 'size' ? SIZE_WORD.ru[o] : ITEM_BY_ID[o]?.name || o // NLU бэка надёжнее понимает русские названия
    return { label, text, value: o, action: { type: 'set_combo_choice', choice_id: choice.id, value: o, target: { ordinal: line.line } } }
  })
}

// вопрос про комбо для kz и en собираем из меню
const COMBO_Q = {
  kz: { or: 'немесе', drink: 'Комбоға қандай сусын', side: 'Комбоға қандай гарнир', size: 'Комбо қандай өлшемде' },
  en: { or: 'or', drink: 'Which drink for your combo', side: 'Which side for your combo', size: 'Which size for your combo' },
}
function comboQuestion(r, lang) {
  const q = COMBO_Q[lang]
  const line = (r.cart?.lines || []).find((l) => l.pending)
  const item = line && ITEM_BY_ID[line.item_id]
  const ch = item?.choices?.find((c) => c.label === line.missing[0])
  if (!q || !ch || !q[ch.id]) return null
  const opts = ch.options
    .filter((o) => ch.kind === 'size' || ITEM_BY_ID[o]?.available !== false)
    .map((o) => (ch.kind === 'size' ? SIZE_WORD[lang][o] : itemName(o, ITEM_BY_ID[o]?.name || o, lang)))
  return `${q[ch.id]}: ${opts.slice(0, -1).join(', ')} ${q.or} ${opts[opts.length - 1]}?`
}

const REPLY = {
  ru: { confirmed: (t) => `Заказ подтверждён! К оплате ${t} ₸.`, total: (t) => `Итого ${t} ₸. Что-нибудь ещё или подтверждаем?`, again: 'Не понял, повторите, пожалуйста.' },
  kz: { confirmed: (t) => `Расталды! Төлемге ${t} ₸.`, total: (t) => `Барлығы ${t} ₸. Тағы бірдеңе ме?`, again: 'Түсінбедім, қайталаңызшы.' },
  en: { confirmed: (t) => `Order confirmed! Total to pay: ${t} ₸.`, total: (t) => `Total ${t} ₸. Anything else, or shall we confirm?`, again: "Sorry, I didn't catch that. Please repeat." },
}

function adaptStep(r, uiLang, stats, manual = false) {
  // тапы - язык интерфейса; голос/текст - язык фразы (киоск переключится на него сам)
  // en не переключаем на язык фразы
  const lang = manual || uiLang === 'en' ? uiLang : r.lang === 'kk' ? 'kz' : r.lang === 'ru' ? 'ru' : uiLang
  const say = REPLY[lang] || REPLY.ru
  const tr = (text) => (lang === 'en' ? toEnglish(text) : text)
  const cart = adaptCart(r.cart, lang)
  const parts = (r.notes || []).map(tr).map((n) => (/[.!?]$/.test(n) ? n : n + '.'))
  if (r.question) parts.push(comboQuestion(r, lang) || tr(r.question))
  else if (cart.status === 'confirmed') parts.push(say.confirmed(cart.total))
  else if (r.upsell) parts.push(lang === 'ru' ? r.upsell.text
    : lang === 'kz' ? `${itemName(r.upsell.item_id, r.upsell.name, 'kz')} қосайық па?`
      : `Would you like to add ${itemName(r.upsell.item_id, r.upsell.name, 'en')}?`)
  else if (cart.status === 'open' && cart.lines.length && (r.actions || []).length) parts.push(say.total(cart.total))
  if (!parts.length) parts.push(say.again)

  if (manual) stats.manual++
  else {
    stats.turns++
    if (r.question) stats.clarifications++
  }
  const actions = (r.actions || []).map((a) => ({
    intent: a.candidates?.length ? 'clarify' : ACTION_INTENT[a.type] || a.type,
    item: a.item_id || a.value || a.modifier_id || a.target?.menu_item_id || null,
    raw: a,
  }))
  const t = r.timings_ms || {}
  return {
    quick: quickReplies(r, lang),
    reply: parts.join(' '),
    lang,
    transcript: r.transcript,
    actions,
    raw_actions: r.actions,
    cart,
    pending: r.cart?.has_pending || !!r.question ? { question: r.question } : null,
    stats: { ...stats },
    latency_ms: Math.round(t.total ?? Object.values(t).reduce((a, b) => a + b, 0)),
    timings_ms: t,
  }
}

const statsBySession = new Map()
const statsFor = (id) => {
  if (!statsBySession.has(id)) statsBySession.set(id, { turns: 0, clarifications: 0, manual: 0 })
  return statsBySession.get(id)
}

// ---------- публичное API для UI ----------
export function getMenu() {
  if (MODE === 'mock') return mock.menu()
  const CATS = [
    { id: 'combo', ru: 'Комбо', kz: 'Комбо', en: 'Combos' },
    { id: 'burger', ru: 'Бургеры', kz: 'Бургерлер', en: 'Burgers' },
    { id: 'side', ru: 'Закуски', kz: 'Тағамдар', en: 'Sides' },
    { id: 'sauce', ru: 'Соусы', kz: 'Соустар', en: 'Sauces' },
    { id: 'drink', ru: 'Напитки', kz: 'Сусындар', en: 'Drinks' },
    { id: 'dessert', ru: 'Десерты', kz: 'Десерттер', en: 'Desserts' },
  ]
  const items = BACK_MENU.items.map((i) => ({
    id: i.id,
    category: i.category,
    name_ru: i.name,
    name_kz: i.name_kk || KZ_ITEM[i.id] || i.name,
    name_en: i.name_en || i.name,
    desc: i.combo ? { ru: 'бургер + гарнир + напиток', kz: 'бургер + тағам + сусын', en: 'burger + side + drink' } : null,
    price: tg(i.price_cents),
    sizes: i.size_prices_cents ? Object.fromEntries(Object.entries(i.size_prices_cents).map(([k, v]) => [k, tg(v)])) : null,
    available: i.available !== false,
    modifiers: i.modifiers.map((m) => ({
      id: m, name_ru: MOD[m]?.name, name_kz: MOD[m]?.name_kk || KZ_MOD[m] || MOD[m]?.name,
      name_en: MOD[m]?.name_en || MOD[m]?.name, price: tg(MOD[m]?.price_cents || 0),
    })),
  }))
  return Promise.resolve({ categories: CATS.filter((c) => items.some((i) => i.category === c.id)), items })
}

export async function sendMessage(sessionId, text, uiLang = 'ru', manual = false) {
  const t0 = performance.now()
  let res
  if (MODE === 'mock') res = await mock.message(sessionId, text)
  else {
    const r = await http(`/cart/${sessionId}/text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    res = adaptStep(r, uiLang, statsFor(sessionId), manual)
  }
  return { ...res, roundtrip_ms: Math.round(performance.now() - t0) }
}

// голос целиком на бэк: STT + NLU + корзина за один запрос
export async function sendVoice(sessionId, blob, uiLang = 'ru') {
  const t0 = performance.now()
  const ext = (blob.type.split('/')[1] || 'webm').split(';')[0]
  const fd = new FormData()
  fd.append('audio', blob, `speech.${ext}`)
  fd.append('lang', { kz: 'kk', en: 'en' }[uiLang] || 'ru')
  const r = await http(`/cart/${sessionId}/voice`, { method: 'POST', body: fd })
  return { ...adaptStep(r, uiLang, statsFor(sessionId)), roundtrip_ms: Math.round(performance.now() - t0) }
}

export async function resetSession(sessionId) {
  statsBySession.delete(sessionId)
  if (MODE === 'mock') return mock.reset(sessionId)
  return http(`/cart/${sessionId}`, { method: 'DELETE' }).catch(() => null)
}

// ---------- ручные действия (тап по меню, +/-, выбор в комбо) ----------
// POST /cart/{id}/actions -> та же корзина, что и у голоса. Нет эндпоинта -> текстовая команда.
let actionsSupported = MODE === 'python'
export const actionsMode = () => (actionsSupported ? 'actions' : 'text')

export async function sendActions(sessionId, actions, fallbackText, uiLang = 'ru') {
  const t0 = performance.now()
  if (actionsSupported) {
    try {
      const r = await http(`/cart/${sessionId}/actions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actions }),
      })
      return { ...adaptStep(r, uiLang, statsFor(sessionId), true), manual: true, roundtrip_ms: Math.round(performance.now() - t0) }
    } catch (e) {
      if (e.status !== 404 && e.status !== 405) throw e
      actionsSupported = false
    }
  }
  const res = await sendMessage(sessionId, fallbackText, uiLang, true)
  return { ...res, manual: true }
}
