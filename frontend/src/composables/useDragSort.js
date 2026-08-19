import { reactive, ref, watch } from 'vue'

/**
 * 模块级拖拽状态（所有面板共享的“当前正在拖拽的模块 id”）。
 * 不涉及持久化，由面板的 useDragLayout 负责落盘。
 */
const draggedId = ref(null)

export function useDragState() {
  return {
    draggedId,
    beginDrag(id, e) {
      draggedId.value = id
      if (e && e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move'
        try { e.dataTransfer.setData('text/plain', id) } catch (err) { /* ignore */ }
      }
    },
    clearDrag() {
      draggedId.value = null
    },
    isDragging(id) {
      return draggedId.value === id
    },
  }
}

/**
 * 面板级布局状态：模块顺序 + 各模块展开/折叠，持久化到 localStorage。
 *
 * @param {import('vue').Ref<string>} keyRef  存储 key（响应式，切换面板/对象时自动重载）
 * @param {string[]} defaultOrder  模块默认顺序（固定模块全集）
 * @param {Record<string, boolean>} defaults  各模块默认展开状态
 */
export function useDragLayout(keyRef, defaultOrder, defaults = {}) {
  const state = reactive({ order: [], open: {} })
  const def = defaultOrder.filter(Boolean)

  function load() {
    const saved = read(keyRef.value)
    const valid = (saved && saved.order || []).filter((id) => def.includes(id))
    const order = []
    for (const id of valid) order.push(id)
    for (const id of def) if (!order.includes(id)) order.push(id)
    state.order = order
    for (const id of def) {
      state.open[id] = saved && saved.open && id in saved.open
        ? !!saved.open[id]
        : (defaults[id] !== undefined ? defaults[id] : true)
    }
  }

  load()
  watch(keyRef, load)
  // 展开/折叠状态变化自动落盘（顺序变化走 move() 保存）
  watch(() => ({ ...state.open }), save, { deep: true })

  function save() {
    try {
      localStorage.setItem(keyRef.value, JSON.stringify({
        order: state.order,
        open: state.open,
      }))
    } catch (err) { /* ignore */ }
  }

  function move(from, to, position) {
    if (!from || from === to) return
    const list = state.order.filter((id) => id !== from)
    const idx = list.indexOf(to)
    if (idx < 0) list.push(from)
    else list.splice(position === 'before' ? idx : idx + 1, 0, from)
    state.order = list
    save()
  }

  function toggleOpen(id, v) {
    state.open[id] = v
    save()
  }

  return { state, save, move, toggleOpen }
}

function read(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch (err) {
    return null
  }
}
