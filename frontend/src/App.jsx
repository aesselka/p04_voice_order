import { useEffect, useMemo, useRef, useState } from 'react'
import { getMenu, sendMessage, sendVoice, sendActions, resetSession, actionsMode, MODE, STT_MODE } from './api.js'
import { useSpeech } from './useSpeech.js'
import { LANGS, UI } from './i18n.js'
import CatIcon from './components/CatIcons.jsx'
import ProductCard from './components/ProductCard.jsx'
import OrderPanel from './components/OrderPanel.jsx'
import MetricsView from './components/MetricsView.jsx'
import IdleScreen from './components/IdleScreen.jsx'
import { IcMenu, IcChart, IcSearch, IcRefresh } from './components/Icons.jsx'

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random())
const EMPTY_CART = { lines: [], total: 0, status: 'open' }
const ORD_RU = ['первое', 'второе', 'третье', 'четвёртое', 'пятое', 'шестое', 'седьмое', 'восьмое', 'девятое', 'десятое']
const ORD_KZ = ['біріншісін', 'екіншісін', 'үшіншісін', 'төртіншісін', 'бесіншісін', 'алтыншысын', 'жетіншісін', 'сегізіншісін', 'тоғызыншысын', 'оныншысын']
const SIZE_RU = { S: 'маленький', M: 'средний', L: 'большой' }

export default function App() {
  const [lang, setLang] = useState('ru')
  const [sessionId, setSessionId] = useState(newId)
  const sid = useRef(sessionId) // актуальная сессия для асинхронных вызовов (демо-прогон)
  const [demo, setDemo] = useState(false)
  const [menu, setMenu] = useState(null)
  const [messages, setMessages] = useState([])
  const [cart, setCart] = useState(EMPTY_CART)
  const [pending, setPending] = useState(null)
  const [quick, setQuick] = useState([])
  const [last, setLast] = useState(null) // {heard, reply}
  const [stats, setStats] = useState({ turns: 0, clarifications: 0, manual: 0, orders: 0 })
  const [turns, setTurns] = useState([])
  const [activity, setActivity] = useState([])
  const [inflight, setInflight] = useState(0)
  const busy = inflight > 0
  const queue = useRef(Promise.resolve()) // голос и тапы выполняются строго по очереди
  const [view, setView] = useState('kiosk')
  const [cat, setCat] = useState('all')
  const [query, setQuery] = useState('')
  const [flash, setFlash] = useState([])
  const [mode, setMode] = useState('in')
  const [sheet, setSheet] = useState(false)
  const [idle, setIdle] = useState(true) // заставка при старте и когда киоск простаивает
  const [resetIn, setResetIn] = useState(null) // секунды до автосброса после подтверждения
  const lastTouch = useRef(Date.now())
  const flashTimer = useRef(null)
  const ui = UI[lang]
  const orderNo = useMemo(() => sessionId.replace(/-/g, '').slice(0, 6).toUpperCase(), [sessionId])

  useEffect(() => {
    getMenu().then(setMenu).catch((e) => setLast({ reply: `${UI[lang].menuError}: ${e.message}` }))
  }, [])

  // ---------- общий приём ответа: голос, текст и тапы попадают в одну корзину ----------
  function applyRes(res, text, kind) {
    setMessages((m) => [...m, { role: 'user', text, kind }, { role: 'bot', text: res.reply, res }])
    setCart(res.cart)
    setPending(res.pending)
    setQuick(res.quick || [])
    setStats((s) => ({
      turns: s.turns + (kind === 'tap' ? 0 : 1),
      clarifications: s.clarifications + (kind !== 'tap' && res.pending?.question ? 1 : 0),
      manual: s.manual + (kind === 'tap' ? 1 : 0),
      orders: s.orders + (res.cart?.status === 'confirmed' && (res.actions || []).some((x) => x.intent === 'confirm') ? 1 : 0),
    }))
    if (kind !== 'tap') setLast({ heard: kind === 'voice' ? text : null, reply: res.reply })
    else if (res.pending?.question) setLast({ heard: null, reply: res.reply })
    const ms = res.roundtrip_ms ?? res.latency_ms ?? 0
    setTurns((t) => [...t, { n: t.length + 1, ms, text, manual: kind === 'tap' }])
    const now = Date.now()
    const acts = (res.actions || []).map((a, i) => ({
      id: `${now}-${i}`, t: now, intent: a.intent,
      title: `${a.intent}${a.item ? ` · ${a.item}` : ''}`,
      sub: kind === 'tap' ? `👆 ${text}` : `🎙 "${text}"`,
    }))
    if (res.pending?.question) acts.push({ id: `${now}-q`, t: now, intent: 'clarify', title: 'clarify', sub: res.pending.question })
    setActivity((a) => [...a, ...acts])
    // подсветка карточек, которые изменил голос
    const ids = (res.actions || []).map((a) => a.raw?.item_id || a.item).filter(Boolean)
    if (ids.length) {
      setFlash(ids)
      clearTimeout(flashTimer.current)
      flashTimer.current = setTimeout(() => setFlash([]), 1400)
    }
    if (res.lang === 'kz' && lang === 'ru' && kind !== 'tap') setLang('kz')
  }
  const fail = (e) => setLast({ reply: e.noBackend ? ui.noBackend : `${ui.error}: ${e.message}` })

  // не блокируем экран: каждый запрос встаёт в очередь, порядок фраз и тапов сохраняется
  function run(fn, text, kind) {
    setInflight((n) => n + 1)
    const p = queue.current.then(async () => {
      try {
        const res = await fn()
        applyRes(res, kind === 'voice' && res.transcript ? res.transcript : text, kind)
      } catch (e) {
        fail(e)
      } finally {
        setInflight((n) => n - 1)
      }
    })
    queue.current = p
    return p
  }

  const send = (text, voice = false) => run(() => sendMessage(sid.current, text, lang), text, voice ? 'voice' : 'text')
  const sendAudio = (blob) => run(() => sendVoice(sid.current, blob, lang), '...', 'voice')
  const act = (actions, fallbackText, label) => run(() => sendActions(sid.current, actions, fallbackText, lang), label || fallbackText, 'tap')

  const speech = useSpeech({
    lang,
    onFinal: (t) => { lastTouch.current = Date.now(); send(t, true) },
    onAudio: sendAudio,
  })

  // ---------- режим киоска: заставка и автосброс ----------
  useEffect(() => {
    const touch = () => { lastTouch.current = Date.now() }
    window.addEventListener('pointerdown', touch)
    window.addEventListener('keydown', touch)
    return () => { window.removeEventListener('pointerdown', touch); window.removeEventListener('keydown', touch) }
  }, [])
  // пустая корзина и 60 с без действий -> заставка (заказ в процессе никогда не прячем)
  useEffect(() => {
    const t = setInterval(() => {
      if (!idle && !demo && !busy && !speech.listening && cart.lines.length === 0 && view === 'kiosk'
        && Date.now() - lastTouch.current > 60000) setIdle(true)
    }, 5000)
    return () => clearInterval(t)
  }, [idle, demo, busy, speech.listening, cart.lines.length, view])
  // заказ подтверждён -> через 20 с новый заказ и заставка
  useEffect(() => {
    if (cart.status !== 'confirmed' || demo) { setResetIn(null); return }
    setResetIn(20)
    const t = setInterval(() => setResetIn((s) => (s == null ? null : s - 1)), 1000)
    return () => clearInterval(t)
  }, [cart.status, demo])
  useEffect(() => {
    if (resetIn === 0) {
      if (speech.listening) speech.stop()
      newOrder().then(() => { setIdle(true); setView('kiosk') })
    }
  }, [resetIn])

  // ---------- ручные действия ----------
  const nameOf = (item) => item[`name_${lang}`] || item.name_ru
  const ordText = (pos) => (lang === 'kz' ? `${ORD_KZ[pos - 1] || pos + ' позицияны'} алып таста` : `убери ${ORD_RU[pos - 1] || 'позицию ' + pos}`)

  function addItem(item, size) {
    // комбо ждёт напиток/гарнир, а гость тапнул подходящую карточку - это ответ комбо, а не новая позиция
    const answer = quick.find((q) => q.action && q.value === item.id)
    if (answer) return onQuick(answer)
    const n = nameOf(item)
    const sw = size && size !== 'M' ? SIZE_RU[size] + ' ' : ''
    // запасной текст для NLU - всегда по-русски, его бэк понимает надёжнее
    act([{ type: 'add_item', item_id: item.id, quantity: 1, ...(size ? { size } : {}) }], `${sw}${item.name_ru}`, `+ ${n}${size ? ' ' + size : ''}`)
  }
  const plus = (l) =>
    act([{ type: 'change_quantity', target: { ordinal: l.position }, quantity: l.qty + 1 }], l.name_ru || l.name, `+1 ${l.name}`)
  const minus = (l) =>
    l.qty > 1
      ? act([{ type: 'change_quantity', target: { ordinal: l.position }, quantity: l.qty - 1 }], `убери один ${l.name_ru || l.name}`, `-1 ${l.name}`)
      : remove(l)
  const remove = (l) => act([{ type: 'remove_item', target: { ordinal: l.position } }], ordText(l.position), `✕ ${l.name}`)
  const onQuick = (q) => (q.action ? act([q.action], q.text, q.label) : send(q.text))
  // запасной текст для nlu всегда ru/kk
  const confirm = () => act([{ type: 'confirm' }], lang === 'kz' ? 'растаймын' : 'подтверждаю', ui.confirm)
  const clear = () => act([{ type: 'clear_cart' }], lang === 'kz' ? 'тапсырысты болдырма' : 'отмени заказ', ui.clear)

  // новый заказ: корзина с нуля, метрики остаются (копятся за всю сессию киоска)
  async function newOrder() {
    await resetSession(sid.current).catch(() => {})
    const id = newId()
    sid.current = id
    setSessionId(id)
    setCart(EMPTY_CART)
    setPending(null)
    setQuick([])
    setLast(null)
  }
  function resetMetrics() {
    setStats({ turns: 0, clarifications: 0, manual: 0, orders: 0 })
    setTurns([])
    setActivity([])
    setMessages([])
  }

  // демо для защиты: сценарий из задания прогоняется через бэк, метрики заполняются вживую
  const DEMO = {
    ru: ['два чизбургера и колу', 'колу сделай большой', 'комбо наггетс', 'спрайт', 'картофель фри', 'убери первое', 'подтверждаю'],
    kz: ['екі чизбургер және кола', 'үлкен қыл', 'комбо наггетс', 'спрайт', 'фри', 'біріншісін алып таста', 'растаймын'],
  }
  DEMO.en = DEMO.ru // nlu понимает ru/kk
  async function runDemo() {
    if (demo) return
    setDemo(true)
    try {
      await newOrder()
      for (const phrase of DEMO[lang]) {
        await send(phrase)
        await new Promise((r) => setTimeout(r, 700))
      }
    } finally {
      setDemo(false)
    }
  }

  // ---------- меню ----------
  const inCart = useMemo(() => {
    const m = {}
    cart.lines.forEach((l) => { m[l.item_id] = (m[l.item_id] || 0) + l.qty })
    return m
  }, [cart])
  const items = useMemo(() => {
    if (!menu) return []
    const q = query.trim().toLowerCase()
    return menu.items.filter((i) => (cat === 'all' || i.category === cat) && (!q || nameOf(i).toLowerCase().includes(q)))
  }, [menu, cat, query, lang])

  const catTitle = cat === 'all' ? ui.allProducts : menu?.categories.find((c) => c.id === cat)?.[lang]

  return (
    <div className="kshell">
      <header className="khead">
        <div className="klogo">
          <span className="logo-mark"><span /></span>
          <b>Voice Order</b>
        </div>
        <nav className="knav">
          <button className={view === 'kiosk' ? 'on' : ''} onClick={() => setView('kiosk')}>
            <IcMenu size={17} />{ui.navKiosk}
          </button>
          <button className={view === 'metrics' ? 'on' : ''} onClick={() => setView('metrics')}>
            <IcChart size={17} />{ui.navMetrics}
          </button>
        </nav>
        <label className="ksearch">
          <IcSearch size={18} />
          <input value={query} onChange={(e) => { setQuery(e.target.value); setView('kiosk') }} placeholder={ui.search} />
        </label>
        <div className="seg">
          {LANGS.map((l) => (
            <button key={l.id} className={lang === l.id ? 'on' : ''} onClick={() => setLang(l.id)}>{l.short}</button>
          ))}
        </div>
        <span className="kstatus" title={`STT: ${STT_MODE}`}>
          <span className={'dot ' + (MODE === 'mock' ? 'warn' : 'ok')} />{MODE === 'mock' ? 'mock' : 'API'}
        </span>
        <button className="btn-yellow head-btn" onClick={newOrder}><IcRefresh size={17} />{ui.newOrder}</button>
      </header>

      <div className="kbody">
        <main className="kmain">
          {view === 'kiosk' ? (
            <div className="kmenu">
              <div className="kmenu-side">
                <h1 className="ktitle">{catTitle}</h1>
                <button className={'cat-all' + (cat === 'all' ? ' on' : '')} onClick={() => setCat('all')}>
                  <span className="cat-ic"><CatIcon id="all" /></span>{ui.allProducts}
                </button>
                <div className="cats">
                  {menu?.categories.map((c) => (
                    <button key={c.id} className={'cat' + (cat === c.id ? ' on' : '')} onClick={() => setCat(c.id)}>
                      <span className="cat-ic"><CatIcon id={c.id} /></span>{c[lang]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid">
                {items.map((i) => (
                  <ProductCard key={i.id} item={i} lang={lang} ui={ui} inCart={inCart[i.id] || 0}
                    flash={flash.includes(i.id)} busy={cart.status === 'confirmed'} onAdd={addItem} />
                ))}
              </div>
            </div>
          ) : (
            <MetricsView ui={ui} stats={stats} turns={turns} activity={activity} messages={messages} actionsMode={actionsMode()}
              demo={demo} busy={busy} onDemo={runDemo} onReset={resetMetrics} />
          )}
        </main>

        <OrderPanel
          ui={ui} lang={lang} cart={cart} pending={pending} quick={quick} busy={busy} speech={speech}
          last={last} orderNo={orderNo} mode={mode} setMode={setMode}
          onSend={(t) => send(t)} onQuick={onQuick} onPlus={plus} onMinus={minus} onRemove={remove}
          onConfirm={confirm} onClear={clear} onNew={newOrder} open={sheet} setOpen={setSheet} resetIn={resetIn}
        />
      </div>

      {idle && !demo && (
        <IdleScreen ui={ui} lang={lang} setLang={setLang} canVoice={speech.supported}
          onStart={() => { lastTouch.current = Date.now(); setIdle(false) }}
          onVoice={() => { lastTouch.current = Date.now(); setIdle(false); if (!speech.listening) speech.start() }} />
      )}
    </div>
  )
}