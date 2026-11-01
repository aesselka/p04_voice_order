// Тестовое меню (по мотивам публичного меню im.kz). Цены в тенге.
// aliases: основы слов; "=слово" = точное слово; несколько слов через пробел = фраза.

export const CATEGORIES = [
  { id: 'combo', ru: 'Комбо', kz: 'Комбо' },
  { id: 'burger', ru: 'Бургеры', kz: 'Бургерлер' },
  { id: 'twister', ru: 'Твистеры', kz: 'Твистерлер' },
  { id: 'side', ru: 'Закуски', kz: 'Тағамдар' },
  { id: 'drink', ru: 'Напитки', kz: 'Сусындар' },
  { id: 'dessert', ru: 'Десерты', kz: 'Десерттер' },
]

export const SIZE_LABELS = {
  S: { ru: 'маленький', kz: 'кіші', short: 'S' },
  M: { ru: 'средний', kz: 'орта', short: 'M' },
  L: { ru: 'большой', kz: 'үлкен', short: 'L' },
}

export const MODIFIERS = {
  no_onion: { ru: 'без лука', kz: 'пиязсыз', price: 0 },
  extra_cheese: { ru: 'доп. сыр', kz: 'қосымша ірімшік', price: 200 },
  bacon: { ru: 'бекон', kz: 'бекон', price: 350 },
  spicy: { ru: 'острый соус', kz: 'ащы соус', price: 150 },
  cheese_sauce: { ru: 'сырный соус', kz: 'ірімшік соусы', price: 200 },
  no_ice: { ru: 'без льда', kz: 'мұзсыз', price: 0 },
}

export const COMBO_UPSIZE_L = 150 // доплата за большой напиток в комбо
export const COMBO_DRINK_IDS = ['cola', 'fanta', 'sprite', 'ice_tea', 'water']

export const GROUPS = {
  combo: { ru: 'Какое именно комбо?', kz: 'Қай комбо?', aliases: ['комбо', 'комбик'] },
  burger: { ru: 'Какой именно бургер?', kz: 'Қай бургер?', aliases: ['бургер'] },
}

const BURGER_MODS = ['no_onion', 'extra_cheese', 'bacon', 'spicy']
const DRINK_MODS = ['no_ice']

export const MENU = [
  // Комбо (бургер + картошка фри M + напиток M на выбор)
  { id: 'combo_classic', cat: 'combo', group: 'combo', ru: 'Комбо Классик', kz: 'Классик комбо', price: 2690,
    desc: { ru: 'Чизбургер + фри + напиток', kz: 'Чизбургер + фри + сусын' },
    mods: BURGER_MODS, aliases: ['комбо классик', 'классик комбо', 'классическ комбо', 'комбо классическ', 'комбо чиз', 'чиз комбо', 'классик'] },
  { id: 'combo_chicken', cat: 'combo', group: 'combo', ru: 'Комбо Чикен', kz: 'Чикен комбо', price: 2890,
    desc: { ru: 'Чикен бургер + фри + напиток', kz: 'Чикен бургер + фри + сусын' },
    mods: BURGER_MODS, aliases: ['комбо чикен', 'чикен комбо', 'комбо курин', 'курин комбо', 'тауық комбо', 'комбо тауық'] },
  { id: 'combo_big', cat: 'combo', group: 'combo', ru: 'Комбо Биг', kz: 'Биг комбо', price: 3290,
    desc: { ru: 'Биг бургер + фри + напиток', kz: 'Биг бургер + фри + сусын' },
    mods: BURGER_MODS, aliases: ['комбо биг', 'биг комбо'] },
  { id: 'combo_twister', cat: 'combo', group: 'combo', ru: 'Комбо Твистер', kz: 'Твистер комбо', price: 2790,
    desc: { ru: 'Твистер + фри + напиток', kz: 'Твистер + фри + сусын' },
    mods: ['no_onion', 'spicy'], aliases: ['комбо твистер', 'твистер комбо'] },

  // Бургеры
  { id: 'cheeseburger', cat: 'burger', group: 'burger', ru: 'Чизбургер', kz: 'Чизбургер', price: 1290,
    mods: BURGER_MODS, aliases: ['чизбургер', 'чиз бургер', 'чизик'] },
  { id: 'hamburger', cat: 'burger', group: 'burger', ru: 'Гамбургер', kz: 'Гамбургер', price: 1090,
    mods: BURGER_MODS, aliases: ['гамбургер'] },
  { id: 'big_burger', cat: 'burger', group: 'burger', ru: 'Биг Бургер', kz: 'Биг бургер', price: 1990,
    mods: BURGER_MODS, aliases: ['биг бургер', 'бигбургер', '=биг'] },
  { id: 'chicken_burger', cat: 'burger', group: 'burger', ru: 'Чикен Бургер', kz: 'Чикен бургер', price: 1590,
    mods: BURGER_MODS, aliases: ['чикен бургер', 'чикенбургер', 'курин бургер', 'тауық бургер', '=чикен'] },
  { id: 'double_cheese', cat: 'burger', group: 'burger', ru: 'Двойной Чизбургер', kz: 'Қос чизбургер', price: 2290,
    mods: BURGER_MODS, aliases: ['двойн чизбургер', 'дабл чиз', 'двойн чиз', 'қос чизбургер', '=дабл'] },
  { id: 'fish_burger', cat: 'burger', group: 'burger', ru: 'Фиш Бургер', kz: 'Балық бургер', price: 1690,
    mods: ['no_onion', 'extra_cheese'], aliases: ['фиш бургер', 'фишбургер', 'рыбн бургер', 'балық бургер', '=фиш'], available: false },

  // Твистеры
  { id: 'twister', cat: 'twister', ru: 'Твистер', kz: 'Твистер', price: 1690,
    mods: ['no_onion', 'spicy', 'cheese_sauce'], aliases: ['твистер'] },
  { id: 'spicy_twister', cat: 'twister', ru: 'Твистер Острый', kz: 'Ащы твистер', price: 1790,
    mods: ['no_onion', 'cheese_sauce'], aliases: ['остр твистер', 'твистер остр', 'ащы твистер'] },

  // Закуски
  { id: 'fries', cat: 'side', ru: 'Картофель фри', kz: 'Фри картобы', sizes: { S: 590, M: 790, L: 990 }, defaultSize: 'M',
    mods: ['cheese_sauce'], aliases: ['картошк фри', 'картофел фри', 'картоп фри', 'фри', 'картошк', 'картофел', 'картоп'] },
  { id: 'nuggets', cat: 'side', ru: 'Наггетсы 6 шт', kz: 'Наггетс 6 дана', price: 990,
    mods: ['cheese_sauce', 'spicy'], aliases: ['наггетс', 'наггет', 'нагетс', 'нагет'] },
  { id: 'onion_rings', cat: 'side', ru: 'Луковые кольца', kz: 'Пияз сақиналары', price: 890,
    mods: ['cheese_sauce'], aliases: ['луков кольц', 'колечк', 'кольц', 'пияз сақина', 'сақина'] },
  { id: 'cheese_sticks', cat: 'side', ru: 'Сырные палочки', kz: 'Ірімшік таяқшалары', price: 990,
    mods: [], aliases: ['сырн палоч', 'ірімшік таяқ', 'палочк'] },

  // Напитки
  { id: 'cola', cat: 'drink', ru: 'Кока-Кола', kz: 'Кока-Кола', sizes: { S: 490, M: 590, L: 690 }, defaultSize: 'M',
    mods: DRINK_MODS, aliases: ['кока кол', 'кока-кол', 'кол', 'кока', 'coca', 'cola'] },
  { id: 'fanta', cat: 'drink', ru: 'Фанта', kz: 'Фанта', sizes: { S: 490, M: 590, L: 690 }, defaultSize: 'M',
    mods: DRINK_MODS, aliases: ['фант', 'fanta'] },
  { id: 'sprite', cat: 'drink', ru: 'Спрайт', kz: 'Спрайт', sizes: { S: 490, M: 590, L: 690 }, defaultSize: 'M',
    mods: DRINK_MODS, aliases: ['спрайт', 'sprite'] },
  { id: 'ice_tea', cat: 'drink', ru: 'Айс Ти', kz: 'Мұзды шай', sizes: { S: 490, M: 590, L: 690 }, defaultSize: 'M',
    mods: DRINK_MODS, aliases: ['айс ти', 'айсти', 'холодн чай', 'мұзды шай', 'ice tea', 'лимонн чай'] },
  { id: 'water', cat: 'drink', ru: 'Вода 0.5', kz: 'Су 0.5', price: 390,
    mods: [], aliases: ['вод', 'минералк', '=су', '=суы', '=суды'] },
  { id: 'americano', cat: 'drink', ru: 'Американо', kz: 'Американо', sizes: { M: 690, L: 790 }, defaultSize: 'M',
    mods: [], aliases: ['американо', 'кофе', 'кофейк'] },
  { id: 'latte', cat: 'drink', ru: 'Латте', kz: 'Латте', sizes: { M: 890, L: 990 }, defaultSize: 'M',
    mods: [], aliases: ['латте', 'лате'] },
  { id: 'tea', cat: 'drink', ru: 'Чай', kz: 'Шай', price: 390,
    mods: [], aliases: ['чай', 'чаю', 'шай'] },

  // Десерты
  { id: 'ice_cream', cat: 'dessert', ru: 'Мороженое', kz: 'Балмұздақ', price: 590,
    mods: [], aliases: ['морожен', 'балмұздақ', 'пломбир'] },
  { id: 'cherry_pie', cat: 'dessert', ru: 'Вишнёвый пирожок', kz: 'Шие бәліші', price: 490,
    mods: [], aliases: ['пирож', 'пирог', 'бәліш'], available: false },
]

export const ITEM = Object.fromEntries(MENU.map((i) => [i.id, { available: true, ...i }]))
