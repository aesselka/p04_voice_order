import { useEffect, useState } from 'react'
import { fmt } from '../i18n.js'
import { CAT_ICON, INTENT_ICON, IcBox } from './Icons.jsx'

export const Round = ({ icon: Icon, size = 34 }) => (
  <span className="round" style={{ width: size, height: size }}><Icon size={size * 0.47} /></span>
)

export function CardHead({ icon, title, right }) {
  return (
    <div className="card-head">
      <Round icon={icon} />
      <h3>{title}</h3>
      <div className="card-head-right">{right}</div>
    </div>
  )
}

export function Kpi({ icon, title, value, sub, badge, tone = 'green' }) {
  return (
    <div className="card kpi">
      <div className="kpi-top">
        <Round icon={icon} size={30} />
        <span>{title}</span>
      </div>
      <div className="kpi-row">
        <b>{value}</b>
        {badge != null && <span className={`badge ${tone}`}>{badge}</span>}
      </div>
      <small>{sub}</small>
    </div>
  )
}

// столбики задержки по репликам, последняя - оранжевая
export function LatencyChart({ turns, ui }) {
  const data = turns.slice(-8)
  if (!data.length) return <div className="chart-empty">{ui.noTurns}</div>
  const maxV = Math.max(100, ...data.map((d) => d.ms))
  const top = Math.ceil(maxV / 50) * 50
  const ticks = [top, Math.round(top * 0.75), Math.round(top * 0.5), Math.round(top * 0.25), 0]
  return (
    <div className="chart">
      <div className="chart-y">{ticks.map((t) => <span key={t}>{t}</span>)}</div>
      <div className="chart-plot">
        {ticks.map((t, i) => <i key={t} className="grid-line" style={{ top: `${(i / 4) * 100}%` }} />)}
        {data.map((d, i) => {
          const last = i === data.length - 1
          const h = Math.max(6, (d.ms / top) * 100)
          return (
            <div key={d.n} className="bar-col" title={`${d.text}: ${d.ms} ms`}>
              <div className={'bar' + (last ? ' hot' : '')} style={{ height: `${h}%` }}>
                {last ? <span className="bar-tip">{d.ms} ms</span> : <i className="bar-cap" />}
              </div>
              <span className={'bar-label' + (last ? ' on' : '')}>#{d.n}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function useNow() {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(t) }, [])
  return now
}

export function ActivityFeed({ items, ui }) {
  const now = useNow()
  if (!items.length) return <div className="chart-empty">{ui.noActivity}</div>
  const ago = (t) => {
    const s = Math.round((now - t) / 1000)
    if (s < 10) return ui.now
    return s < 60 ? `${s}${ui.sec} ${ui.ago}` : `${Math.round(s / 60)}${ui.min} ${ui.ago}`
  }
  return (
    <ul className="feed">
      {items.slice(-12).reverse().map((a) => {
        const Icon = INTENT_ICON[a.intent] || IcBox
        return (
          <li key={a.id}>
            <span className={`round sm i-${a.intent}`}><Icon size={14} /></span>
            <div className="feed-main">
              <b>{a.title}</b>
              <small>{a.sub}</small>
            </div>
            <span className="feed-time">{ago(a.t)}</span>
          </li>
        )
      })}
    </ul>
  )
}

export function MenuTable({ menu, lang, ui, query, busy, onPick }) {
  if (!menu) return null
  const nk = lang === 'kz' ? 'name_kz' : 'name_ru'
  const catName = Object.fromEntries(menu.categories.map((c) => [c.id, c[lang]]))
  const q = query.trim().toLowerCase()
  const items = menu.items.filter((i) => !q || i[nk].toLowerCase().includes(q) || (catName[i.category] || '').toLowerCase().includes(q))
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{ui.colName}</th>
            <th>{ui.colStatus}</th>
            <th className="hide-sm">{ui.colSizes}</th>
            <th className="num">{ui.colPrice}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((i) => {
            const Icon = CAT_ICON[i.category] || IcBox
            const price = i.sizes ? `${ui.from} ${fmt(Math.min(...Object.values(i.sizes)))}` : fmt(i.price)
            return (
              <tr key={i.id}>
                <td>
                  <div className="cell-item">
                    <span className="round sm"><Icon size={14} /></span>
                    <div>
                      <b>{i[nk]}</b>
                      <small>{i.desc ? i.desc[lang] : catName[i.category]}</small>
                    </div>
                  </div>
                </td>
                <td><span className={'badge ' + (i.available ? 'green' : 'orange')}>{i.available ? ui.inStock : ui.outStock}</span></td>
                <td className="hide-sm muted">{i.sizes ? Object.keys(i.sizes).join(' / ') : '-'}</td>
                <td className="num">{price}</td>
                <td className="num">
                  <button className="pill sm" disabled={!i.available || busy} onClick={() => onPick(i[nk])}>{ui.add}</button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
