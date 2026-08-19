<template>
  <div
    class="drag-mod"
    :class="{ dragging: isDragging(dragId), 'drop-before': dropBefore, 'drop-after': dropAfter }"
    :data-drag-id="dragId"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <slot />
    <span
      v-if="handle"
      class="drag-mod-grip"
      draggable="true"
      @dragstart.stop="onGripStart"
      @dragend.stop="onGripEnd"
      title="拖动调整模块顺序"
    >⠿</span>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useDragState } from '../composables/useDragSort'

const props = defineProps({
  /** 模块唯一 id（必填，用于拖拽与持久化） */
  dragId: { type: String, required: true },
  /** 是否渲染右上角拖拽手柄（默认渲染） */
  handle: { type: Boolean, default: true },
})
const emit = defineEmits(['drop'])

const { draggedId, beginDrag, clearDrag, isDragging } = useDragState()
const dropBefore = ref(false)
const dropAfter = ref(false)

function onGripStart(e) {
  beginDrag(props.dragId, e)
}
function onGripEnd() {
  clearDrag()
  dropBefore.value = false
  dropAfter.value = false
}
function onDragOver(e) {
  if (!draggedId.value) return
  e.preventDefault()
  if (draggedId.value === props.dragId) return
  const rect = e.currentTarget.getBoundingClientRect()
  const before = e.clientY < rect.top + rect.height / 2
  dropBefore.value = before
  dropAfter.value = !before
}
function onDrop(e) {
  if (!draggedId.value) return
  e.preventDefault()
  const from = draggedId.value
  const position = dropBefore.value ? 'before' : 'after'
  dropBefore.value = false
  dropAfter.value = false
  if (from === props.dragId) return
  clearDrag()
  emit('drop', { from, to: props.dragId, position })
}
</script>

<style scoped>
.drag-mod {
  position: relative;
  margin: 2px 0;
  border-radius: 4px;
}
.drag-mod.drop-before { box-shadow: 0 -2px 0 0 var(--accent); }
.drag-mod.drop-after { box-shadow: 0 2px 0 0 var(--accent); }
.drag-mod.dragging { opacity: .5; }
/* 右上角拖拽手柄：hover 模块时浮现 */
.drag-mod-grip {
  position: absolute;
  top: 2px;
  right: 4px;
  z-index: 3;
  width: 18px;
  height: 16px;
  display: grid;
  place-items: center;
  font-size: 11px;
  line-height: 1;
  color: var(--muted);
  cursor: grab;
  border-radius: 3px;
  opacity: 0;
  transition: opacity .12s, background .12s, color .12s;
  user-select: none;
  background: var(--panel-2);
  border: 1px solid var(--line);
}
.drag-mod:hover .drag-mod-grip { opacity: .75; }
.drag-mod-grip:hover { opacity: 1; background: var(--accent-l); color: var(--accent-d); }
.drag-mod-grip:active { cursor: grabbing; }
</style>
