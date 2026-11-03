// Минималистичные иконки категорий: одна толщина линии, скругления, цвет = currentColor
const S = { fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' }

const ICONS = {
  // корзина (пустой заказ)
  cart: (
    <>
      <path d="M5 9h5l4 20h22l4-14H13" />
      <path d="M15 34h21" />
      <circle cx="17" cy="39" r="2.5" />
      <circle cx="33" cy="39" r="2.5" />
    </>
  ),
  // все продукты: тарелка под крышкой
  all: (
    <>
      <path d="M8 34h32" />
      <path d="M11 34a13 13 0 0 1 26 0" />
      <path d="M24 17v4" />
      <circle cx="24" cy="15" r="2" />
      <path d="M6 38h36" />
    </>
  ),
  // комбо: бургер + стакан
  combo: (
    <>
      <path d="M5 26a10 9 0 0 1 20 0z" />
      <path d="M5 30h20" />
      <path d="M6 34h18a2 2 0 0 1-2 3H8a2 2 0 0 1-2-3z" />
      <path d="M30 18h12l-2 21h-8z" />
      <path d="M29 18h14" />
      <path d="M37 18l2-7h3" />
    </>
  ),
  // бургер
  burger: (
    <>
      <path d="M9 22a15 11 0 0 1 30 0z" />
      <path d="M18 15.5h.01M24 14h.01M30 15.5h.01" />
      <path d="M8 27c3-2 5 2 8 0s5 2 8 0 5 2 8 0 5 2 8 0" />
      <path d="M9 32h30a3 3 0 0 1-3 5H12a3 3 0 0 1-3-5z" />
    </>
  ),
  // твистер: ролл
  twister: (
    <>
      <path d="M12 38L30 10a6 6 0 0 1 8 8L18 40z" />
      <path d="M18 40l-6-2" />
      <path d="M27 15l6 4M24 20l6 4" />
    </>
  ),
  // закуски: картофель фри
  side: (
    <>
      <path d="M12 22h24l-3 18H15z" />
      <path d="M17 22l-2-12M22 22V8M27 22l1-13M32 22l3-10" />
      <path d="M18 30a6 4 0 0 0 12 0" />
    </>
  ),
  // соусы: соусник с каплей
  sauce: (
    <>
      <path d="M9 26h30l-3 10a3 3 0 0 1-3 2H15a3 3 0 0 1-3-2z" />
      <path d="M8 26h32" />
      <path d="M24 9c3 4 5 6.5 5 9a5 5 0 0 1-10 0c0-2.5 2-5 5-9z" />
    </>
  ),
  // напитки: стакан с крышкой и трубочкой
  drink: (
    <>
      <path d="M14 17h20l-2.5 23h-15z" />
      <path d="M12 17h24" />
      <path d="M15 13h18l1 4H14z" />
      <path d="M25 13l3-7h5" />
      <path d="M15.5 26h17" />
    </>
  ),
  // десерты: рожок мороженого
  dessert: (
    <>
      <path d="M15 22l9 20 9-20" />
      <path d="M13 22a11 10 0 0 1 22 0z" />
      <path d="M19 28l7 6M28 27l-6 7" />
    </>
  ),
}

export default function CatIcon({ id, size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" {...S} aria-hidden="true">
      {ICONS[id] || ICONS.all}
    </svg>
  )
}