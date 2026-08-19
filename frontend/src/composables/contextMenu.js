// 通用右键上下文菜单的共享状态。任意组件调用 openContextMenu(x, y, items) 打开菜单，
// 由 App.vue 统一挂载的 <ContextMenu> 渲染。对标 Simulink / MATLAB 的右键上下文操作。
import { reactive } from 'vue'

export const ctxState = reactive({
  open: false,
  x: 0,
  y: 0,
  items: [],   // [{ label, icon?, action, disabled?, danger?, accel?, sep? }]
})

export function openContextMenu(x, y, items) {
  ctxState.x = x
  ctxState.y = y
  ctxState.items = items || []
  ctxState.open = true
}

export function closeContextMenu() {
  ctxState.open = false
}
