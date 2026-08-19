// 参数扫描 / 守恒审计 对话框的轻量共享状态（避免牵动主 store sim.js）。
// 由 FlowEditor / LeftSidebar 的右键菜单触发，由 App.vue 挂载 SensitivityDialog 渲染。
import { reactive } from 'vue'
import { useSimStore } from './sim'

export const scanState = reactive({
  open: false,
  unitId: null,      // 当前扫描目标工序 id（审计时为 null）
  unitType: null,
  unitName: null,
  tab: 'scan',       // scan | audit
})

export function openScanDialog(target) {
  const sim = useSimStore()
  // target 既可以是工序 unitId，也可以是工序类型 type（来自资源树/编排节点），
  // 后者取同类型第一个已部署工序作为扫描目标。
  let u = sim.model?.units?.find((x) => x.id === target)
  if (!u) u = sim.model?.units?.find((x) => x.type === target)
  if (!u) return
  scanState.unitId = u.id
  scanState.unitType = u.type
  scanState.unitName = u.name
  scanState.tab = 'scan'
  scanState.open = true
}

export function openAuditDialog() {
  scanState.unitId = null
  scanState.unitType = null
  scanState.unitName = null
  scanState.tab = 'audit'
  scanState.open = true
}

export function closeScanDialog() {
  scanState.open = false
}
