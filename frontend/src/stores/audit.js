// 碳素流守恒审计对话框的轻量共享状态（避免牵动主 store sim.js）。
// 由 App.vue 工具菜单触发，由 App.vue 挂载 ConservationAuditDialog 渲染。
import { reactive } from 'vue'

export const auditState = reactive({
  open: false,
})

export function openAuditDialog() {
  auditState.open = true
}

export function closeAuditDialog() {
  auditState.open = false
}
