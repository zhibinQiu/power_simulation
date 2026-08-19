<template>
  <teleport to="body">
    <div v-if="ctx.open" ref="el" class="ctx-menu" :style="menuStyle" @contextmenu.prevent>
      <template v-for="(it, i) in ctx.items" :key="i">
        <div v-if="it.sep" class="ctx-sep"></div>
        <div v-else class="ctx-item" :class="{ disabled: it.disabled, danger: it.danger }"
             @click="onItem(it)" @mouseenter="hover = i" @mouseleave="hover = -1">
          <span class="ctx-ic" v-if="it.icon"><Icon :name="it.icon" :size="14" /></span>
          <span class="ctx-tx">{{ it.label }}</span>
          <span class="ctx-acc" v-if="it.accel">{{ it.accel }}</span>
        </div>
      </template>
    </div>
  </teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ctxState, closeContextMenu } from '../composables/contextMenu'
import Icon from './Icon.vue'

const ctx = ctxState
const el = ref(null)
const hover = ref(-1)
const menuStyle = reactive({ left: '0px', top: '0px' })

function onItem(it) {
  if (it.disabled) return
  closeContextMenu()
  if (it.action) it.action()
}

function clamp() {
  nextTick(() => {
    const m = el.value
    if (!m) return
    const w = m.offsetWidth || 200
    const h = m.offsetHeight || 200
    let x = ctx.x
    let y = ctx.y
    if (x + w > window.innerWidth - 8) x = Math.max(8, window.innerWidth - w - 8)
    if (y + h > window.innerHeight - 8) y = Math.max(8, window.innerHeight - h - 8)
    menuStyle.left = x + 'px'
    menuStyle.top = y + 'px'
  })
}

watch(() => ctx.open, (v) => { if (v) clamp() })

function onDocMouseDown(e) {
  if (!ctx.open) return
  if (el.value && !el.value.contains(e.target)) closeContextMenu()
}
function onKey(e) {
  if (!ctx.open) return
  if (e.key === 'Escape') closeContextMenu()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onKey)
})
</script>

<style scoped>
.ctx-menu {
  position: fixed; z-index: 300; min-width: 180px;
  background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px; padding: 4px;
  box-shadow: var(--shadow); font-size: 12px; user-select: none;
}
.ctx-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-radius: 5px; cursor: pointer; white-space: nowrap;
}
.ctx-item:hover:not(.disabled) { background: var(--accent-l); }
.ctx-item.disabled { color: var(--faint); cursor: default; }
.ctx-item.danger { color: var(--red); }
.ctx-item.danger:hover:not(.disabled) { background: rgba(199,90,82,.12); }
.ctx-ic { width: 15px; height: 15px; display: grid; place-items: center; color: var(--accent2); flex: 0 0 auto; }
.ctx-item.danger .ctx-ic { color: var(--red); }
.ctx-tx { flex: 1; }
.ctx-acc { color: var(--muted); font-size: 10px; font-family: var(--mono); margin-left: 18px; }
.ctx-sep { height: 1px; background: var(--border); margin: 4px 6px; }
</style>
