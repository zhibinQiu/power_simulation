// 面板尺寸拖拽调整：左侧栏宽度 / 右侧栏宽度 / 命令行窗口高度（均持久化到 localStorage）
import { ref } from 'vue'

const SIDE_W_KEY = 'sim.leftw'
const RIGHT_W_KEY = 'sim.rightw'
const CMD_H_KEY = 'sim.cmdwin.h'

// 通用拖拽：vertical 为 true 时按 Y 轴（高度，向上增大），否则按 X 轴
// invert 为 true 时方向取反（用于面板锚定在屏幕另一侧、手柄在面板边缘的场景，保证手柄跟手）
function startDrag(e, { vertical, invert = false, initial, clamp, onDone }) {
  const startPos = vertical ? e.clientY : e.clientX
  const startVal = initial.value
  const extent = vertical ? window.innerHeight : window.innerWidth
  const raf = { id: null }
  // 拖拽期间禁用 .app 的 grid 过渡：否则每次更新列宽都会重新触发 0.22s 过渡动画，
  // 布局永远追着鼠标跑（不跟手），且中间 stage 慢速过渡与 SceneViewer 的 canvas
  // 立即 setSize 不同步造成闪烁。松开后恢复，面板开合动画不受影响。
  document.body.classList.add('panel-dragging')
  const onMove = (ev) => {
    if (raf.id) return
    raf.id = requestAnimationFrame(() => {
      const rawDelta = vertical ? startPos - ev.clientY : ev.clientX - startPos
      const delta = invert ? -rawDelta : rawDelta
      const nv = clamp(startVal + delta, extent)
      initial.value = Math.round(nv)
      raf.id = null
    })
  }
  const onUp = () => {
    if (raf.id) { cancelAnimationFrame(raf.id); raf.id = null }
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    document.body.classList.remove('panel-dragging')
    onDone(initial.value)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

export function usePanelSizes() {
  const lw = ref(Number(localStorage.getItem(SIDE_W_KEY)) || 286)
  const rw = ref(Number(localStorage.getItem(RIGHT_W_KEY)) || 372)
  const cmdH = ref(Number(localStorage.getItem(CMD_H_KEY)) || 132)

  const lResizing = ref(false)
  const rResizing = ref(false)
  const resizing = ref(false)

  function startLeftResize(e) {
    lResizing.value = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ew-resize'
    startDrag(e, {
      vertical: false, initial: lw,
      clamp: (v, vw) => Math.max(180, Math.min(v, Math.round(vw * 0.42))),
      onDone: (v) => { lResizing.value = false; localStorage.setItem(SIDE_W_KEY, String(v)) },
    })
  }
  function startRightResize(e) {
    rResizing.value = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ew-resize'
    startDrag(e, {
      vertical: false, invert: true, initial: rw,
      clamp: (v, vw) => Math.max(200, Math.min(v, Math.round(vw * 0.5))),
      onDone: (v) => { rResizing.value = false; localStorage.setItem(RIGHT_W_KEY, String(v)) },
    })
  }
  function startResize(e) {
    resizing.value = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ns-resize'
    startDrag(e, {
      vertical: true, initial: cmdH,
      clamp: (v, vh) => Math.max(64, Math.min(v, Math.round(vh * 0.6))),
      onDone: (v) => { resizing.value = false; localStorage.setItem(CMD_H_KEY, String(v)) },
    })
  }

  return { lw, rw, cmdH, lResizing, rResizing, resizing, startLeftResize, startRightResize, startResize }
}
