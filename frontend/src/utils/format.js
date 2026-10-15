/**
 * 统一数值 / 时间格式化。
 *
 * 背景：此前 `fmt` 类函数在 30+ 个组件里各写一份，且有三种互不兼容的方言
 * （占位符 '—' vs '--'、去尾零 vs 固定小数、toFixed vs toLocaleString），
 * 同一个数字在不同面板显示成 1.5 / 1.50 / 1.5 三种样子。这里收敛为单一实现，
 * 各调用点通过参数表达差异，不再各写一份。
 *
 * 设计原则：纯函数、无 i18n / 无 Vue 依赖（语言相关的文案由调用方传入），
 * 便于单测与在 three.js 等非组件代码里复用。
 */

/** 空值占位符（全平台统一） */
export const NIL = '—'

function _num(v) {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 去尾零小数：1.50 → "1.5"，1.00 → "1"，0.0050 → "0.01"。
 * 用于「数值型读数」这类希望紧凑显示的场景。
 */
export function fmtNum(v, digits = 2, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return n.toFixed(digits).replace(/\.?0+$/, '')
}

/**
 * 固定小数位（不去尾零）：1.5 → "1.50"。用于对齐的表格/坐标轴。
 */
export function fmtDigits(v, digits = 2, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return n.toFixed(digits)
}

/**
 * 千分位 + 最大小数位（不补零）：1234.5 → "1,234.5"。用于总量/能耗这类大数。
 */
export function fmtLocale(v, digits = 1, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

/** 百分比（入参为百分数本身：12.5 → "12.5%"） */
export function fmtPct(v, digits = 1, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return n.toFixed(digits) + '%'
}

/** 万位压缩：12345 → "1.2w"。用于紧凑卡片里的大计数。 */
export function fmtCompact(v, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return n >= 10000 ? (n / 10000).toFixed(1) + 'w' : String(n)
}

/** 按量级自适应小数位：|v|≥100 保留 1 位，否则 2 位。 */
export function fmtAuto(v, dash = NIL) {
  const n = _num(v)
  if (n === null) return dash
  return Math.abs(n) >= 100 ? n.toFixed(1) : n.toFixed(2)
}

/**
 * 「多久之前」。epoch 为**秒**级时间戳（与后端 ts 口径一致）。
 * labels 由调用方传入已翻译的单位后缀，如 { s: '秒前', m: '分钟前', h: '小时前', d: '天前' }。
 */
export function fmtAgo(epoch, labels = { s: 's', m: 'm', h: 'h', d: 'd' }, nowSec = Date.now() / 1000) {
  if (!epoch) return ''
  const s = Math.floor(nowSec - Number(epoch))
  if (s < 60) return `${s}${labels.s}`
  if (s < 3600) return `${Math.floor(s / 60)}${labels.m}`
  if (s < 86400) return `${Math.floor(s / 3600)}${labels.h}`
  return `${Math.floor(s / 86400)}${labels.d}`
}

/**
 * 时长（秒）→ 「3天5小时 / 5小时20分 / 20分 / 45秒」。
 * labels: { d: '天', h: '小时', m: '分', s: '秒' }
 */
export function fmtDuration(seconds, labels = { d: '天', h: '小时', m: '分', s: '秒' }, dash = NIL) {
  const n = _num(seconds)
  if (n === null) return dash
  const s = Math.floor(n)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d) return `${d}${labels.d}${h}${labels.h}`
  if (h) return `${h}${labels.h}${m}${labels.m}`
  if (m) return `${m}${labels.m}`
  return `${s}${labels.s}`
}

/** 秒级时间戳 → HH:MM:SS */
export function fmtClock(t, dash = '') {
  if (!t) return dash
  const d = new Date(Number(t) * 1000)
  if (Number.isNaN(d.getTime())) return dash
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 任意时间输入（秒/毫秒时间戳、ISO 串、Date）→ YYYY-MM-DD HH:MM:SS */
export function fmtDateTime(v, dash = '') {
  if (v == null || v === '') return dash
  let ms
  if (v instanceof Date) ms = v.getTime()
  else if (typeof v === 'number') ms = v < 1e12 ? v * 1000 : v   // 秒级 → 毫秒
  else ms = Date.parse(String(v))
  if (!Number.isFinite(ms)) return dash
  const d = new Date(ms)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
