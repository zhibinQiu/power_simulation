// 全局快捷键与文档级点击处理
import { onMounted, onBeforeUnmount } from 'vue'
import { closeAuditDialog, auditState } from '../stores/audit'

export function useGlobalShortcuts({ store, onRun, focusSel, onMenuEsc, onTftAnalysis }) {
  function onKeyGlobal(e) {
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'enter') { e.preventDefault(); onRun(); return }
    // Alt+T：高炉数值仿真分析（仅仿真模式可用，逻辑在回调内判断）
    if (e.altKey && !mod && e.key.toLowerCase() === 't') {
      if (onTftAnalysis) { e.preventDefault(); onTftAnalysis(); return }
    }
    // Esc：优先关闭已打开的模态/弹层（审计对话框、菜单），与组件内 Esc 互不冲突
    if (e.key === 'Escape') {
      if (auditState.open) { closeAuditDialog(); return }
      if (onMenuEsc) onMenuEsc()
      return
    }
    if (!store.editMode) {
      // 仿真态：F 聚焦选中工序
      if ((e.key === 'f' || e.key === 'F') && store.selectedUnitId) { e.preventDefault(); focusSel('focus') }
      return
    }
    const k = e.key.toLowerCase()
    if (k === 'z') { e.preventDefault(); if (e.shiftKey) store.redo(); else store.undo() }
    else if (k === 'y') { e.preventDefault(); store.redo() }
  }

  onMounted(() => { window.addEventListener('keydown', onKeyGlobal) })
  onBeforeUnmount(() => { window.removeEventListener('keydown', onKeyGlobal) })
}
