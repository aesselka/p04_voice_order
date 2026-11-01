const P = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }
const I = ({ d, size = 16, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...P}>{d ? <path d={d} /> : children}</svg>
)

export const IcMic = (p) => <I {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></I>
export const IcCart = (p) => <I {...p}><path d="M3 4h2l2.4 11h10.2L20 7H6.3" /><circle cx="9" cy="19" r="1.3" /><circle cx="17" cy="19" r="1.3" /></I>
export const IcGrid = (p) => <I {...p}><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></I>
export const IcMenu = (p) => <I {...p}><path d="M6 3v8a2 2 0 0 0 2 2v8M10 3v8a2 2 0 0 1-2 2M8 3v6M16 21V3c2.5 1 4 3.5 4 7v3h-4" /></I>
export const IcChart = (p) => <I {...p}><path d="M4 4v16h16" /><path d="M8 16v-4M12 16V8M16 16v-6" /></I>
export const IcPulse = (p) => <I {...p} d="M3 12h4l2-6 4 12 2-6h6" />
export const IcLayers = (p) => <I {...p}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></I>
export const IcCoin = (p) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M14.5 9.5c-.4-.9-1.3-1.5-2.5-1.5-1.6 0-2.5.8-2.5 2 0 2.8 5 1.6 5 4.2 0 1.1-1 1.8-2.5 1.8-1.3 0-2.2-.6-2.6-1.6M12 6.5v1.5M12 16v1.5" /></I>
export const IcClock = (p) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></I>
export const IcQuestion = (p) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.4M12 17h.01" /></I>
export const IcSearch = (p) => <I {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></I>
export const IcPlus = (p) => <I {...p} d="M12 5v14M5 12h14" />
export const IcMinus = (p) => <I {...p} d="M5 12h14" />
export const IcEdit = (p) => <I {...p}><path d="M4 20h4L19 9l-4-4L4 16v4Z" /></I>
export const IcCheck = (p) => <I {...p} d="m5 12 4.5 4.5L19 7" />
export const IcX = (p) => <I {...p} d="M6 6l12 12M18 6 6 18" />
export const IcSend = (p) => <I {...p}><path d="M4 12 20 4l-6 16-3-7-7-1Z" /></I>
export const IcCode = (p) => <I {...p} d="m8 8-4 4 4 4M16 8l4 4-4 4" />
export const IcBurger = (p) => <I {...p}><path d="M4 11h16M5 11a7 5 0 0 1 14 0M4 15h16M5 15v1a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-1" /></I>
export const IcCup = (p) => <I {...p}><path d="M6 8h12l-1.5 12h-9L6 8ZM8 8l1-4h6" /></I>
export const IcFries = (p) => <I {...p}><path d="M6 10h12l-2 10H8L6 10ZM8 10 7 4M11 10V3M14 10l1-6M17 10l1.5-4" /></I>
export const IcStar = (p) => <I {...p} d="m12 4 2.4 5 5.6.6-4.2 3.8 1.2 5.6L12 16.3 7 19l1.2-5.6L4 9.6 9.6 9 12 4Z" />
export const IcBox = (p) => <I {...p}><rect x="4" y="7" width="16" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></I>
export const IcRefresh = (p) => <I {...p}><path d="M20 11a8 8 0 0 0-14.6-4.5M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5M20 20v-4h-4" /></I>
export const IcBars = (p) => <I {...p} d="M4 7h16M4 12h16M4 17h10" />

export const CAT_ICON = { combo: IcBox, burger: IcBurger, twister: IcBurger, side: IcFries, drink: IcCup, dessert: IcStar }
export const INTENT_ICON = { add: IcPlus, remove: IcMinus, modify: IcEdit, confirm: IcCheck, cancel: IcX, clarify: IcQuestion, clarify_answer: IcQuestion, unknown: IcQuestion }
