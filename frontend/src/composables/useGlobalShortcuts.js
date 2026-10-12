// 全局快捷键与文档级点击处理
import { onMounted, onBeforeUnmount } from 'vue'
import { closeAuditDialog, auditState } from '../stores/audit'

export function useGlobalShortcuts({ store, onSimToggle, focusSel, onMenuEsc, onTftAnalysis, onSaveScheme, onSaveAsScene }) {
  function onKeyGlobal(e) {
    const el = e.target
    const tag = (el && el.tagName) || ''
    // 输入框 / 下拉 / 文本域 / 可编辑元素内的按键一律交还给控件本身：
    // 否则给设备重命名时输入 z / y / f 会被当成快捷键（撤销 / 重做 / 聚焦工序），
    // 字符还被 preventDefault 吞掉，表现为「改名打到一半设备被删掉 / 页面跳走」。
    const typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || !!(el && el.isContentEditable)
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'enter') { e.preventDefault(); onSimToggle(); return }
    // Ctrl+S 手动保存编排（编排为手动保存模式）；Ctrl+Shift+S 另存为场景资源包
    if (mod && e.key.toLowerCase() === 's') {
      e.preventDefault()
      if (e.shiftKey) { if (onSaveAsScene) onSaveAsScene() }
      else if (onSaveScheme) onSaveScheme()
      return
    }
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
    // 编排快捷键（Ctrl+Z/Ctrl+Y 撤销重做）仅在编排画布标签前台时生效；
    // 编排态切到三维仿真 / 其它标签时按当前视图处理（F 聚焦等）
    if (!store.flowEditing) {
      // 仿真态：F 聚焦选中工序（输入态不抢按键）
      if ((e.key === 'f' || e.key === 'F') && store.selectedUnitId && !typing) { e.preventDefault(); focusSel('focus') }
      return
    }
    // 撤销 / 重做必须带 Ctrl / Cmd（与帮助里写的 Ctrl+Z / Ctrl+Y 一致），
    // 裸按 z / y 只是普通字符，绝不能触发——否则重命名输入框里打一个 z 就把刚加的设备撤销掉。
    if (!mod || typing) return
    const k = e.key.toLowerCase()
    if (k === 'z') { e.preventDefault(); if (e.shiftKey) store.redo(); else store.undo() }
    else if (k === 'y') { e.preventDefault(); store.redo() }
  }

  onMounted(() => { window.addEventListener('keydown', onKeyGlobal) })
  onBeforeUnmount(() => { window.removeEventListener('keydown', onKeyGlobal) })
}
