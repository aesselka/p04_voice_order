import { createMockBackend } from './mock/engine.js'
import BACK_MENU from './backendMenu.json'

// mock = встроенный движок, python = бэк voice_cart_nlu (FastAPI) через прокси Vite
export const MODE = import.meta.env.VITE_API_URL ? 'python' : 'mock'
export const STT_MODE = import.meta.env.VITE_STT === 'server' && MODE === 'python' ? 'server' : 'browser'

const mock = createMockBackend()
const tg = (cents) => Math.round(cents / 100)
const SIZE_RU = { S: 'маленький', M: 'средний', L: 'большой' }
const SIZE_KZ = { S: 'кіші', M: 'орта', L: 'үлкен' }
const MOD = Object.fromEntries(BACK_MENU.modifiers.map((m) => [m.id, m]))

// казахские названия: в menu.json бэка их нет, поэтому словарь на фронте (id -> название)
const KZ_ITEM = {
  burger: 'Бургер', chicken_burger: 'Тауық бургері', combo: 'Комбо', fries: 'Фри картобы', nuggets: 'Наггетстер',
  salad: 'Салат', cola: 'Кока-кола', sprite: 'Спрайт', fanta: 'Фанта', water: 'Су', juice_apple: 'Алма шырыны',
  juice_orange: 'Апельсин шырыны', latte: 'Латте', coffee: 'Кофе', tea: 'Шай', ice_cream: 'Балмұздақ',
}
const KZ_MOD = { onion: 'Пияз', cheese: 'Ірімшік', ketchup: 'Кетчуп', garlic_sauce: 'Сарымсақ соусы', mayo: 'Майонез', ice: 'Мұз', sugar: 'Қант' }
const KZ_LABEL = { напиток: 'сусын', гарнир: 'гарнир', размер: 'өлшем' }
const itemName = (id, fallback, lang) => (lang === 'kz' && KZ_ITEM[id]) || fallback
const modName = (id, fallback, lang) => (lang === 'kz' && KZ_MOD[id]) || fallback
const labelName = (l, lang) => (lang === 'kz' && KZ_LABEL[l]) || l

async function http(path, opts = {}) {
  let r
  try {
    r = await fetch(path, opts)
  } catch {
    throw new Error('нет связи с бэком (он запущен на :8000?)')
  }
  if (r.status === 204) return null
  const body = await r.json().catch(() => ({}))
  if (!r.ok) { const e = new Error(body.detail || `HTTP ${r.status}`); e.status = r.status; throw e }
  return body
}

// ---------- адаптер ответа Python-бэка -> формат UI ----------
function adaptCart(c, lang) {
  const sizes = lang === 'kz' ? SIZE_KZ : SIZE_RU
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
        ? (lang === 'kz' ? `${modName(m.id, m.name, lang).toLowerCase()} жоқ` : `без ${MOD[m.id]?.gen || m.name.toLowerCase()}`)
        : modName(m.id, m.name, lang),
      price: tg(m.price_cents),
    })),
    choices: l.choices.map((ch) => ({
      id: ch.id,
      text: ch.id === 'size' ? `${labelName(ch.label, lang)}: ${ch.value}` : itemName(ch.value, ch.name, lang),
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
const SIZE_WORD = { ru: { S: 'маленький', M: 'средний', L: 'большой' }, kz: { S: 'кіші', M: 'орта', L: 'үлкен' } }
function quickReplies(r, lang) {
  if (r.cart?.status && r.cart.status !== 'open') return []
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

// вопрос про комбо по-казахски: бэк отвечает только по-русски, текст собираем из меню
const KZ_Q = { drink: 'Комбоға қандай сусын', side: 'Комбоға қандай гарнир', size: 'Комбо қандай өлшемде' }
function kzComboQuestion(r) {
  const line = (r.cart?.lines || []).find((l) => l.pending)
  const item = line && ITEM_BY_ID[line.item_id]
  const ch = item?.choices?.find((c) => c.label === line.missing[0])
  if (!ch || !KZ_Q[ch.id]) return null
  const opts = ch.options.map((o) => (ch.kind === 'size' ? SIZE_WORD.kz[o] : itemName(o, ITEM_BY_ID[o]?.name || o, 'kz')))
  return `${KZ_Q[ch.id]}: ${opts.slice(0, -1).join(', ')} немесе ${opts[opts.length - 1]}?`
}

function adaptStep(r, uiLang, stats, manual = false) {
  // тапы - язык интерфейса; голос/текст - язык фразы (киоск переключится на него сам)
  const lang = manual ? uiLang : r.lang === 'kk' ? 'kz' : r.lang === 'ru' ? 'ru' : uiLang
  const cart = adaptCart(r.cart, lang)
  const parts = (r.notes || []).map((n) => (/[.!?]$/.test(n) ? n : n + '.'))
  if (r.question) parts.push((lang === 'kz' && kzComboQuestion(r)) || r.question)
  else if (cart.status === 'confirmed') parts.push(lang === 'kz' ? `Расталды! Төлемге ${cart.total} ₸.` : `Заказ подтверждён! К оплате ${cart.total} ₸.`)
  else if (cart.status === 'open' && cart.lines.length && (r.actions || []).length)
    parts.push(lang === 'kz' ? `Барлығы ${cart.total} ₸. Тағы бірдеңе ме?` : `Итого ${cart.total} ₸. Что-нибудь ещё или подтверждаем?`)
  if (!parts.length) parts.push(lang === 'kz' ? 'Түсінбедім, қайталаңызшы.' : 'Не понял, повторите, пожалуйста.')

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
    { id: 'combo', ru: 'Комбо', kz: 'Комбо' },
    { id: 'burger', ru: 'Бургеры', kz: 'Бургерлер' },
    { id: 'side', ru: 'Закуски', kz: 'Тағамдар' },
    { id: 'drink', ru: 'Напитки', kz: 'Сусындар' },
    { id: 'dessert', ru: 'Десерты', kz: 'Десерттер' },
  ]
  const items = BACK_MENU.items.map((i) => ({
    id: i.id,
    category: i.category,
    name_ru: i.name,
    name_kz: KZ_ITEM[i.id] || i.name,
    desc: i.combo ? { ru: 'бургер + гарнир + напиток', kz: 'бургер + тағам + сусын' } : null,
    price: tg(i.price_cents),
    sizes: i.size_prices_cents ? Object.fromEntries(Object.entries(i.size_prices_cents).map(([k, v]) => [k, tg(v)])) : null,
    available: i.available !== false,
    modifiers: i.modifiers.map((m) => ({ id: m, name_ru: MOD[m]?.name, name_kz: KZ_MOD[m] || MOD[m]?.name, price: tg(MOD[m]?.price_cents || 0) })),
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
  fd.append('lang', uiLang === 'kz' ? 'kk' : 'ru')
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
