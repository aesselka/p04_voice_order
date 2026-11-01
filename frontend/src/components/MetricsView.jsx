import { Kpi, CardHead, LatencyChart, ActivityFeed } from './Widgets.jsx'
import { IcLayers, IcQuestion, IcClock, IcCart, IcChart, IcPulse, IcCode } from './Icons.jsx'

// экран для защиты: метрики сессии и лог действий (голос и ручные)
export default function MetricsView({ ui, stats, turns, activity, messages, actionsMode, demo, busy, onDemo, onReset }) {
  const voiceTurns = turns.filter((t) => !t.manual)
  const lastMs = voiceTurns.length ? voiceTurns[voiceTurns.length - 1].ms : 0
  const avgMs = voiceTurns.length ? Math.round(voiceTurns.reduce((a, t) => a + t.ms, 0) / voiceTurns.length) : 0
  const lastBot = [...messages].reverse().find((m) => m.res)
  return (
    <div className="metrics">
      <div className="metrics-bar">
        <div>
          <h2>{ui.navMetrics}</h2>
          <small>{ui.metricsHint} · {ui.ordersDone}: <b>{stats.orders}</b></small>
        </div>
        <button className="btn-ghost" onClick={onReset} disabled={demo}>{ui.resetMetrics}</button>
        <button className="btn-orange slim" onClick={onDemo} disabled={demo || busy}>{demo ? ui.demoRunning : ui.runDemo}</button>
      </div>
      <div className="kpis">
        <Kpi icon={IcLayers} title={ui.kTurns} value={stats.turns} sub={ui.voiceCmds} />
        <Kpi icon={IcQuestion} title={ui.kClarifs} value={stats.clarifications}
          sub={stats.turns ? `${Math.round((stats.clarifications / stats.turns) * 100)}% ${ui.ofTurns}` : '-'} />
        <Kpi icon={IcCart} title={ui.kManual} value={stats.manual || 0} sub={ui.manualVia(actionsMode)} />
        <Kpi icon={IcClock} title={ui.kLatency} value={`${lastMs} ms`} sub={ui.kLatencySub(avgMs)}
          badge={voiceTurns.length ? (lastMs <= 500 ? 'OK' : 'slow') : null} tone={lastMs <= 500 ? 'green' : 'orange'} />
      </div>
      <div className="metrics-grid">
        <div className="card">
          <CardHead icon={IcChart} title={ui.latencyChart} right={<span className="muted small">ms</span>} />
          <LatencyChart turns={voiceTurns} ui={ui} />
        </div>
        <div className="card">
          <CardHead icon={IcPulse} title={ui.activity} right={<span className="muted small">{activity.length}</span>} />
          <ActivityFeed items={activity} ui={ui} />
        </div>
        <div className="card span2">
          <CardHead icon={IcCode} title={ui.lastJson} />
          <pre className="debug">{lastBot ? JSON.stringify(lastBot.res.raw_actions ?? lastBot.res.actions, null, 2) : '-'}</pre>
        </div>
      </div>
    </div>
  )
}
