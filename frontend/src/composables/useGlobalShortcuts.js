// 全局快捷键与文档级点击处理
import { onMounted, onBeforeUnmount } from 'vue'
import { closeScanDialog, scanState } from '../stores/scan'

export function useGlobalShortcuts({ store, onRun, focusSel, onMenuEsc }) {
  function onKeyGlobal(e) {
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'enter') { e.preventDefault(); onRun(); return }
    // Esc：优先关闭已打开的模态/弹层（扫描对话框、菜单），与组件内 Esc 互不冲突
    if (e.key === 'Escape') {
      if (scanState.open) { closeScanDialog(); return }
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
