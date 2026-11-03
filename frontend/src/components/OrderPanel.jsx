import { useState } from 'react'
import { fmt } from '../i18n.js'
import FoodImg from './FoodImg.jsx'
import CatIcon from './CatIcons.jsx'
import { IcMic, IcSend, IcX, IcPlus, IcMinus, IcCheck } from './Icons.jsx'

// правая колонка киоска: голос + заказ + итог. На узком экране - нижняя шторка.
export default function OrderPanel({
  ui, lang, cart, pending, quick, busy, speech, last, orderNo, mode, setMode,
  onSend, onQuick, onPlus, onMinus, onRemove, onConfirm, onClear, onNew, open, setOpen, resetIn,
}) {
  const [text, setText] = useState('')
  const lines = cart?.lines || []
  const status = cart?.status || 'open'
  const qty = lines.reduce((a, l) => a + l.qty, 0)
  const pendingCount = lines.filter((l) => l.pending || l.needs_drink).length

  const submit = (e) => {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  // микрофон включён: показываем то, что слышим, а между фразами - последний ответ кассы
  const voiceStatus = speech.interim || (busy ? ui.thinking : last?.reply || (speech.listening ? ui.listeningHint : ui.voiceHint))

  return (
    <aside className={'order' + (open ? ' open' : '')}>
      {/* свёрнутая полоска (только узкий экран) */}
      <div className="order-peek" onClick={() => setOpen(!open)}>
        <span className="peek-grip" />
        <button
          className={'mic sm' + (speech.listening ? ' on' : '')}
          onClick={(e) => { e.stopPropagation(); speech.toggle() }}
          disabled={!speech.supported || status === 'confirmed'}
          aria-label="mic"
        >
          <IcMic size={18} />
        </button>
        <div className="peek-text">
          <b>{ui.myOrder} · {qty}</b>
          <small>{speech.interim || (speech.listening ? '● ' + ui.liveOn : last?.reply || ui.voiceHint)}</small>
        </div>
        <span className="peek-total">{fmt(cart?.total || 0)}</span>
      </div>

      <div className="order-head">
        <div>
          <small>{ui.currentOrder}</small>
          <b>#{orderNo}</b>
        </div>
        <div className="ta-right">
          <small>{ui.kiosk}</small>
          <b>01</b>
        </div>
      </div>

      <div className="seg big">
        {[['away', ui.takeAway], ['in', ui.dineIn]].map(([k, l]) => (
          <button key={k} className={mode === k ? 'on' : ''} onClick={() => setMode(k)}>{l}</button>
        ))}
      </div>

      {/* голос */}
      <div className={'voicebox' + (speech.listening ? ' live' : '')}>
        <div className="voice-row">
          <button
            className={'mic' + (speech.listening ? ' on' : '')}
            onClick={speech.toggle}
            disabled={!speech.supported || status === 'confirmed'}
            title={speech.listening ? ui.tapToStop : ui.tapToSpeak}
          >
            <IcMic size={24} />
          </button>
          <div className="voice-text">
            {speech.listening ? <small className="live-tag"><i />{ui.liveOn}</small> : last?.heard && <small>«{last.heard}»</small>}
            <p className={speech.interim ? 'interim' : ''}>{voiceStatus}</p>
          </div>
        </div>
        {quick?.length > 0 && status === 'open' && (
          <div className="quick">
            {quick.map((q) => (
              <button key={q.label} className="chip-q" disabled={busy} onClick={() => onQuick(q)}>{q.label}</button>
            ))}
          </div>
        )}
        <form className="voice-input" onSubmit={submit}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={ui.placeholder} disabled={status === 'confirmed'} />
          <button disabled={!text.trim()} aria-label="send"><IcSend size={15} /></button>
        </form>
        {speech.error && <div className="err">{speech.error}</div>}
      </div>

      {status === 'confirmed' ? (
        <div className="done">
          <span className="done-ic"><IcCheck size={30} /></span>
          <h3>{ui.statusConfirmed}</h3>
          <p>{ui.orderNo} <b>#{orderNo}</b></p>
          <b className="done-total">{fmt(cart.total)}</b>
          <button className="btn-orange" onClick={onNew}>{ui.newOrder}</button>
          {resetIn != null && resetIn > 0 && <small className="done-timer">{ui.autoReset(resetIn)}</small>}
        </div>
      ) : (
        <>
          <h2 className="order-title">
            {ui.myOrder}
            {pending && status === 'open' && <span className="badge orange">{ui.pending}</span>}
          </h2>

          {lines.length === 0 ? (
            <div className="order-empty">
              <span className="empty-ic"><CatIcon id="cart" size={34} /></span>
              <b>{ui.empty}</b>
              <small>{ui.emptyHint}</small>
            </div>
          ) : (
            <ul className="olines">
              {lines.map((l) => (
                <li key={l.line_id} className={l.pending ? 'pending' : ''}>
                  <span className="othumb"><FoodImg id={l.item_id} cat={l.category} w={160} /></span>
                  <div className="omain">
                    <b>{l.name}{l.size && <span className="chip">{l.size}</span>}</b>
                    {(l.choices?.length > 0 || l.modifiers.length > 0 || l.drink) && (
                      <small>
                        {[
                          ...(l.drink ? [l.drink.name] : []),
                          ...(l.choices || []).map((c) => c.text),
                          ...l.modifiers.map((m) => m.name),
                        ].join(' · ')}
                      </small>
                    )}
                    {l.missing?.length > 0 && <small className="warn">{ui.choose}: {l.missing.join(', ')}</small>}
                    {l.needs_drink && <small className="warn">{ui.needDrink}</small>}
                    <div className="stepper">
                      <button disabled={busy} onClick={() => onMinus(l)} aria-label="minus"><IcMinus size={13} /></button>
                      <span>{l.qty}</span>
                      <button disabled={busy} onClick={() => onPlus(l)} aria-label="plus"><IcPlus size={13} /></button>
                    </div>
                  </div>
                  <div className="oright">
                    <b className={l.pending ? 'dim' : ''}>{fmt(l.line_total)}</b>
                    <button className="x" disabled={busy} onClick={() => onRemove(l)} aria-label="remove"><IcX size={12} /></button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <div className="summary">
            <div><span>{ui.items}</span><span>{qty}</span></div>
            {pendingCount > 0 && <div className="warn"><span>{ui.waitChoice}</span><span>{pendingCount}</span></div>}
            <div className="sum-total"><span>{ui.total}</span><b>{fmt(cart?.total || 0)}</b></div>
            <button className="btn-orange" disabled={busy || !lines.length || !!pending} onClick={onConfirm}>{ui.confirm}</button>
            {lines.length > 0 && <button className="btn-ghost" disabled={busy} onClick={onClear}>{ui.clear}</button>}
          </div>
        </>
      )}
    </aside>
  )
}