// 系统主题色：预设主题色列表 + 响应式状态 + localStorage 持久化。
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

export function getAccent() { return accent.value }
