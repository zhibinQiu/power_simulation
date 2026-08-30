// 系统主题：主题色（accent）+ 界面模式（themeMode：白天/夜间）。
// 实际颜色通过 App 根节点 data-accent 属性 + main.css 中的变量覆盖规则生效。
import { ref } from 'vue'

export const ACCENTS = [
  { id: 'amber', labelZh: '品牌黄', labelEn: 'Amber' },
  { id: 'blue', labelZh: '科技蓝', labelEn: 'Blue' },
  { id: 'green', labelZh: '生态绿', labelEn: 'Green' },
  { id: 'red', labelZh: '中国红', labelEn: 'Red' },
]

const KEY = 'carbon-sim.accent'
const saved = localStorage.getItem(KEY)

/** 当前主题色 id（响应式，绑定到 App 根节点的 data-accent） */
export const accent = ref(ACCENTS.some((a) => a.id === saved) ? saved : 'amber')

export function setAccent(id) {
  if (!ACCENTS.some((a) => a.id === id)) return
  accent.value = id
  localStorage.setItem(KEY, id)
}

const MODE_KEY = 'carbon-sim.theme-mode'
const savedMode = localStorage.getItem(MODE_KEY)

/** 界面主题模式：'light'（白天，顶栏/底栏亮色）| 'dark'（夜间，深色界面） */
export const themeMode = ref(savedMode === 'dark' ? 'dark' : 'light')

export function setThemeMode(mode) {
  if (mode !== 'light' && mode !== 'dark') return
  themeMode.value = mode
  localStorage.setItem(MODE_KEY, mode)
}
