import { photoFor } from '../kioskData.js'
import { IcMic } from './Icons.jsx'

const SHOW = ['burger', 'fries', 'cola', 'combo', 'ice_cream', 'latte']

// заставка киоска: показывается, когда никого нет. Тап - начать, микрофон - сразу говорить.
export default function IdleScreen({ ui, lang, setLang, onStart, onVoice, canVoice }) {
  return (
    <div className="idle" onClick={onStart}>
      <div className="idle-bg">
        {SHOW.map((id, i) => {
          const src = photoFor(id, 500)
          return <span key={id} className={`idle-tile t${i}`} style={src ? { backgroundImage: `url(${src})` } : undefined} />
        })}
      </div>
      <div className="idle-card" onClick={(e) => e.stopPropagation()}>
        <div className="idle-logo"><span className="logo-mark"><span /></span> VOICE ORDER</div>
        <h1>{ui.idleTitle}</h1>
        <p>{ui.idleSub}</p>
        {canVoice && (
          <button className="idle-mic" onClick={onVoice}>
            <IcMic size={34} />
            <span>{ui.idleVoice}</span>
          </button>
        )}
        <button className="idle-tap" onClick={onStart}>{ui.idleTap}</button>
        <div className="seg idle-lang">
          <button className={lang === 'ru' ? 'on' : ''} onClick={() => setLang('ru')}>Русский</button>
          <button className={lang === 'kz' ? 'on' : ''} onClick={() => setLang('kz')}>Қазақша</button>
        </div>
      </div>
    </div>
  )
}
