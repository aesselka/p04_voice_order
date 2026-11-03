import { useState } from 'react'
import { fmt } from '../i18n.js'
import { tintFor } from '../kioskData.js'
import FoodImg from './FoodImg.jsx'
import { IcCart } from './Icons.jsx'

export default function ProductCard({ item, lang, ui, inCart, flash, busy, onAdd }) {
  const sizes = item.sizes ? Object.keys(item.sizes) : null
  const [size, setSize] = useState(sizes ? (sizes.includes('M') ? 'M' : sizes[0]) : null)
  const name = item[`name_${lang}`] || item.name_ru
  const price = sizes ? item.sizes[size] : item.price
  const desc = item.desc?.[lang] || (item.modifiers.length ? item.modifiers.map((m) => m[`name_${lang}`] || m.name_ru).slice(0, 3).join(', ') : '')

  return (
    <article className={'pcard' + (item.available ? '' : ' off') + (flash ? ' flash' : '') + (inCart ? ' has' : '')}>
      <button className="pcard-img" style={{ background: tintFor(item.category) }} disabled={!item.available || busy} onClick={() => onAdd(item, size)}>
        <FoodImg id={item.id} cat={item.category} className="pcard-food" />
        {inCart > 0 && <span className="pcard-qty">{inCart}</span>}
        {!item.available && <span className="pcard-off">{ui.outStock}</span>}
      </button>
      <div className="pcard-body">
        <h4>{name}</h4>
        {desc && <p>{desc}</p>}
        {sizes && (
          <div className="sizes">
            {sizes.map((s) => (
              <button key={s} className={s === size ? 'on' : ''} onClick={() => setSize(s)} disabled={!item.available}>{s}</button>
            ))}
          </div>
        )}
        <div className="pcard-foot">
          <b className="pcard-price">{fmt(price)}</b>
          <button className="add-btn" disabled={!item.available || busy} onClick={() => onAdd(item, size)}>
            <IcCart size={16} /> {ui.add}
          </button>
        </div>
      </div>
    </article>
  )
}
