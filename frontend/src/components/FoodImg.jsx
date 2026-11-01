import { useState } from 'react'
import { emojiFor, photoFor } from '../kioskData.js'

// фото блюда; пока грузится или если не загрузилось - эмодзи
export default function FoodImg({ id, cat, w = 600, className = '' }) {
  const src = photoFor(id, w)
  const [ok, setOk] = useState(false)
  const [bad, setBad] = useState(false)
  return (
    <span className={'food ' + className}>
      {(!src || !ok || bad) && <span className="food-emoji">{emojiFor(id, cat)}</span>}
      {src && !bad && (
        <img src={src} alt="" loading="lazy" onLoad={() => setOk(true)} onError={() => setBad(true)} className={ok ? 'on' : ''} />
      )}
    </span>
  )
}
