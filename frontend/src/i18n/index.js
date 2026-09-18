// 轻量 i18n：以中文文案为 key，英文词典按需映射。
// 语言切换实时生效（reactive），并持久化到 localStorage。
import { reactive, ref } from 'vue'
import zhCN from './zh-CN'

const KEY = 'carbon-sim.lang'
const LANG_ZH = 'zh-CN'
const LANG_EN = 'en-US'

// 中文无需词典（key 本身即中文原文）；英文词典是纯 Object 字面量、源码 232KB，
// 原先静态 import 会把整份词条打进首屏主包（主包体积的近三分之一，却只有切英文的用户用得上）。
// 改为**切换英文 / 空闲预取时才异步加载**，中文用户永远不必为它付出下载与解析成本。
const dicts = { [LANG_ZH]: zhCN }
// 词典版本号：英文词典异步到货后自增。t() 每次读取它 —— 在渲染期间调用即建立响应式依赖，
// 因此词典迟到时界面会自动补翻译，「切换语言实时生效」的行为保持原样。
const dictVersion = ref(0)
let enTask = null

export function loadEnDict() {
  if (dicts[LANG_EN] || enTask) return enTask
  enTask = import('./en-US')
    .then((m) => {
      dicts[LANG_EN] = m.default || m
      dictVersion.value++
      applyDocLang()
    })
    .catch(() => { enTask = null })
  return enTask
}

const saved = localStorage.getItem(KEY)
const state = reactive({ lang: saved === LANG_EN ? LANG_EN : LANG_ZH })

/** 翻译：en 查词典，zh 或未命中回退原文（中文）。
 *  支持 {param} 插值：t('当前 {val} {unit}', { val: 42, unit: 'kg' })
 *  插值在查词后执行，因此词典条目与中文原文都需含 {param} 占位符；
 *  未提供 params 时行为与旧版完全一致（向后兼容）。 */
export function t(key, params) {
  void dictVersion.value   // 依赖词典版本：英文词典异步到货后触发调用方重算
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

function applyDocLang() {
  document.documentElement.lang = state.lang === LANG_EN ? 'en' : 'zh-CN'
  document.title = t('工业能碳智控平台')
}

export function setLang(lang) {
  if (lang !== LANG_ZH && lang !== LANG_EN) return
  state.lang = lang
  localStorage.setItem(KEY, lang)
  applyDocLang()
  // 语言就是用户显式选的：英文词典此刻才需要下载（已加载则复用缓存）
  if (lang === LANG_EN) loadEnDict()
}

// 初始化：应用持久化的语言（lang 属性 + 标题）。
// 若上次是英文：先按中文渲染出界面（零等待首屏），词典后台加载到货后自动整体重译为英文。
setLang(state.lang)

// 预取英文词典：避免中文用户首次切英文时出现一瞬间的中文回退。
// 不再无条件在空闲时预取——那会让**所有**中文用户（占绝大多数）都下载并解析
// 194KB 的 en-US chunk，与首屏之后的交互抢带宽和主线程，白白拖慢响应速度。
// 改为「用户真的开始操作了才预取」：后台/挂机标签页完全不下载，
// 而用户既然要交互，就可能在之后切换语言，此时词典早已就位。
if (typeof window !== 'undefined') {
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 3000))
  const prefetch = () => { idle(() => loadEnDict(), { timeout: 10000 }) }
  for (const ev of ['pointerdown', 'keydown']) {
    window.addEventListener(ev, prefetch, { once: true, passive: true, capture: true })
  }
}

export const langState = state
