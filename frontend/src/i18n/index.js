// 轻量 i18n：以中文文案为 key，英文词典按需映射。
// 语言切换实时生效（reactive），并持久化到 localStorage。
import { reactive } from 'vue'
import zhCN from './zh-CN'
import enUS from './en-US'

const KEY = 'carbon-sim.lang'
const LANG_ZH = 'zh-CN'
const LANG_EN = 'en-US'
const dicts = { [LANG_ZH]: zhCN, [LANG_EN]: enUS }

const saved = localStorage.getItem(KEY)
const state = reactive({ lang: saved === LANG_EN ? LANG_EN : LANG_ZH })

/** 翻译：en 查词典，zh 或未命中回退原文（中文）。
 *  支持 {param} 插值：t('当前 {val} {unit}', { val: 42, unit: 'kg' })
 *  插值在查词后执行，因此词典条目与中文原文都需含 {param} 占位符；
 *  未提供 params 时行为与旧版完全一致（向后兼容）。 */
export function t(key, params) {
  const d = dicts[state.lang]
  let out = (d && d[key]) || key
  if (params && typeof params === 'object') {
    for (const k of Object.keys(params)) {
      out = out.split(`{${k}}`).join(params[k])
    }
  }
  return out
}

export function isEn() { return state.lang === LANG_EN }

export function getLang() { return state.lang }

export function setLang(lang) {
  if (lang !== LANG_ZH && lang !== LANG_EN) return
  state.lang = lang
  localStorage.setItem(KEY, lang)
  document.documentElement.lang = lang === LANG_EN ? 'en' : 'zh-CN'
  document.title = t('工业能碳智控平台')
}

// 初始化：应用持久化的语言（lang 属性 + 标题）
setLang(state.lang)

export const langState = state
