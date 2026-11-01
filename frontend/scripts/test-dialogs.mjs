// Прогон текстовых диалогов через mock-движок: node scripts/test-dialogs.mjs
import { createSession, handleMessage } from '../src/mock/engine.js'

const DIALOGS = [
  { name: 'Два комбо, удалить второе, кола большая',
    turns: ['два комбо классик', 'колу', 'второе убери', 'колу сделай большой'],
    expect: { total: 2690 + 150, lines: 1 } },
  { name: 'Неоднозначное комбо -> уточнение',
    turns: ['хочу комбо', 'чикен', 'спрайт', 'подтверждаю'],
    expect: { total: 2890, status: 'confirmed' } },
  { name: 'Модификаторы и размер',
    turns: ['чизбургер без лука с беконом', 'большую картошку фри', 'и сырный соус'],
    expect: { total: 1290 + 350 + 990 + 200, lines: 2 } },
  { name: 'Замена позиции',
    turns: ['два чизбургера и колу', 'колу замени на спрайт', 'убери один чизбургер'],
    expect: { total: 1290 + 590, lines: 2 } },
  { name: 'Нет в наличии',
    turns: ['фиш бургер', 'тогда биг бургер'],
    expect: { total: 1990, lines: 1 } },
  { name: 'Казахский',
    turns: ['екі чизбургер пиязсыз', 'үлкен кола', 'екіншісін алып таста', 'растаймын'],
    expect: { total: 2 * 1290, status: 'confirmed' } },
  { name: 'Отмена',
    turns: ['твистер и латте', 'отмени заказ'],
    expect: { total: 0, status: 'cancelled' } },
  { name: 'Цепочка в одной фразе',
    turns: ['два комбо биг с колой, второе убери, колу сделай большой'],
    expect: { total: 3290 + 150, lines: 1 } },
  { name: 'Нельзя модификатор',
    turns: ['латте с беконом'],
    expect: { total: 890, lines: 1 } },
  { name: 'Размер по номеру позиции',
    turns: ['наггетсы и фанту', 'вторую сделай маленькой', 'да'],
    expect: { total: 990 + 490, status: 'confirmed' } },
]

let pass = 0
for (const d of DIALOGS) {
  const s = createSession()
  let r
  console.log(`\n=== ${d.name}`)
  for (const t of d.turns) {
    r = handleMessage(s, t)
    console.log(`  > ${t}\n  < ${r.reply}  [${r.latency_ms} ms]`)
  }
  const ok = Object.entries(d.expect).every(([k, v]) =>
    k === 'total' ? r.cart.total === v : k === 'lines' ? r.cart.lines.length === v : r.cart[k] === v)
  console.log(ok ? '  OK' : `  FAIL expected ${JSON.stringify(d.expect)} got total=${r.cart.total} lines=${r.cart.lines.length} status=${r.cart.status}`)
  if (ok) pass++
}
console.log(`\n${pass}/${DIALOGS.length} диалогов прошли`)
