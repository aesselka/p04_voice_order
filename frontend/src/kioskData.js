// Визуал для карточек: эмодзи по id блюда (меню бэка + mock), запасной - по категории
const BY_ID = {
  burger: '🍔', chicken_burger: '🍗', combo: '🍱', fries: '🍟', nuggets: '🍗', salad: '🥗',
  cola: '🥤', sprite: '🥤', fanta: '🥤', water: '💧', juice_apple: '🍏', juice_orange: '🍊',
  latte: '☕', coffee: '☕', tea: '🍵', ice_cream: '🍦',
  combo_classic: '🍱', combo_chicken: '🍱', combo_big: '🍱', combo_twister: '🍱',
  cheeseburger: '🍔', hamburger: '🍔', big_burger: '🍔', double_cheese: '🍔', fish_burger: '🐟',
  twister: '🌯', spicy_twister: '🌶️', onion_rings: '🧅', cheese_sticks: '🧀',
  ice_tea: '🧋', americano: '☕', cherry_pie: '🥧',
}
const BY_CAT = { sauce: '🥫', combo: '🍱', burger: '🍔', twister: '🌯', side: '🍟', drink: '🥤', dessert: '🍦' }

export const emojiFor = (id, cat) => BY_ID[id] || BY_CAT[cat] || '🍽️'
export const catEmoji = (cat) => BY_CAT[cat] || '🍽️'

// тёплые подложки карточек, чтобы сетка не была однотонной
const TINTS = {
  combo: ['#3a2416', '#1f1712'], burger: ['#3b2a14', '#1f1810'], twister: ['#33241a', '#1c1611'],
  side: ['#3a3014', '#1f1b10'], drink: ['#162a33', '#11191d'], dessert: ['#33182a', '#1c1118'],
}
export const tintFor = (cat) => {
  const [a, b] = TINTS[cat] || ['#2a2a2e', '#18181b']
  return `radial-gradient(120% 90% at 50% 20%, ${a}, ${b})`
}

// Фото с Pexels (бесплатная лицензия, указание автора не обязательно): https://www.pexels.com/license/
const PX = (id, w = 600) => `https://images.pexels.com/photos/${id}/pexels-photo-${id}.jpeg?auto=compress&cs=tinysrgb&w=${w}`
const PHOTO = {
  // меню I'M из voice_cart_nlu/data/menu.json
  cheeseburger: 4749403, hamburger: 34407507, chickenburger: 8130750, double_cheeseburger: 33502810,
  big_burger: 5374420, beef_tasty: 15010285, chicken_classic: 9207184,
  combo_big_burger: 20003199, combo_double_cheeseburger: 36007382, combo_chicken_classic: 34407059, combo_nuggets: 10183543,
  fries: 5779487, potato_wedges: 34722097, nuggets: 11710530, strips: 14950910,
  ketchup: 32972548, cheese_sauce: 5855238, bbq_sauce: 13828923,
  coca_cola: 15205136, sprite: 9996446, fanta: 7630062, water: 34199673, juice_orange: 4958852,
  milkshake: 18142623, americano: 1235706, latte: 459489, tea: 34835064,
  cinnabon: 14448820, ice_cream: 16962446, cherry_pie: 35672929,
  // старые id (mock-меню и прошлое меню бэка)
  burger: 5374420, chicken_burger: 8130750, combo: 20003199, salad: 842545, cola: 15205136,
  juice_apple: 5817625, coffee: 1235706,
}
// позиции mock-меню берут фото похожего блюда
const ALIAS = {
  combo_classic: 'combo', combo_chicken: 'combo', combo_big: 'combo', combo_twister: 'combo',
  cheeseburger: 'burger', hamburger: 'burger', big_burger: 'burger', double_cheese: 'burger', fish_burger: 'burger',
  twister: 'chicken_burger', spicy_twister: 'chicken_burger', cheese_sticks: 'nuggets', americano: 'coffee',
}
export const photoFor = (id, w) => {
  const p = PHOTO[id] || PHOTO[ALIAS[id]]
  return p ? PX(p, w) : null
}

// фото для списка категорий (берутся у характерного блюда категории)
export const CAT_PHOTO = {
  all: 'combo_big_burger', combo: 'combo_big_burger', burger: 'cheeseburger', twister: 'chicken_burger',
  side: 'fries', sauce: 'ketchup', drink: 'coca_cola', dessert: 'ice_cream',
}
