<template>
  <section
    class="csec"
    :class="{ open: isOpen, dragging: isDragging(dragId), 'drop-before': dropBefore, 'drop-after': dropAfter }"
    :data-drag-id="dragId || undefined"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <button class="chead" type="button" @click="toggle" :aria-expanded="isOpen">
      <span class="chev" :class="{ flipped: !isOpen }">▾</span>
      <span class="ctitle">{{ title }}</span>
      <span
        v-if="dragId"
        class="drag-grip"
        draggable="true"
        @dragstart.stop="onGripStart"
        @dragend.stop="onGripEnd"
        title="拖动调整模块顺序"
      >⠿</span>
      <span v-if="$slots.actions" class="chead-actions" @click.stop>
        <slot name="actions" />
      </span>
      <span v-else-if="showMore && !dragId" class="chead-more" :class="{ shown: hover }" @click.stop title="更多">⋯</span>
    </button>
    <div v-show="isOpen" class="cbody">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useDragState } from '../composables/useDragSort'

const props = defineProps({
  title: { type: String, required: true },
  defaultOpen: { type: Boolean, default: true },
  showMore: { type: Boolean, default: true },
  /** 提供后该模块可上下拖拽重排；同时作为持久化的模块唯一 id */
  dragId: { type: String, default: '' },
  /** 受控展开状态（供父面板持久化） */
  modelValue: { type: Boolean, default: undefined },
  /** 模块标识色（柔和语义色指示条）：blue | green | teal | amber | red */
  tone: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'drop'])

const internal = ref(props.defaultOpen)
const controlled = computed(() => props.modelValue !== undefined)
const isOpen = computed(() => (controlled.value ? !!props.modelValue : internal.value))

function toggle() {
  if (controlled.value) emit('update:modelValue', !props.modelValue)
  else internal.value = !internal.value
}
watch(() => props.modelValue, (v) => {
  if (v !== undefined) internal.value = v
})

const hover = ref(false)

/* —— 拖拽 —— */
const { draggedId, beginDrag, clearDrag, isDragging } = useDragState()
const dropBefore = ref(false)
const dropAfter = ref(false)

function onGripStart(e) {
  if (!props.dragId) return
  beginDrag(props.dragId, e)
  e.stopPropagation()
}
function onGripEnd() {
  clearDrag()
  dropBefore.value = false
  dropAfter.value = false
}
function onDragOver(e) {
  if (!props.dragId || !draggedId.value) return
  e.preventDefault()
  if (draggedId.value === props.dragId) return
  const rect = e.currentTarget.getBoundingClientRect()
  const before = e.clientY < rect.top + rect.height / 2
  dropBefore.value = before
  dropAfter.value = !before
}
function onDrop(e) {
  if (!props.dragId || !draggedId.value) return
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
/* Blender 风属性面板：标题行 22px、贴近字号、深浅底分层；折叠三角置于标题前；右上角 ⋯ 按钮（默认浅显，hover 变深） */
.csec {
  margin: 0;
  border-radius: 0;
  overflow: visible;
  background: transparent;
  border: none;
}
.csec:first-child { margin-top: 0; }
.csec:last-child { margin-bottom: 0; }
.csec.open {
  background: transparent;
}
/* 拖拽插入指示线（Blender 风：蓝线提示落点） */
.csec.drop-before { box-shadow: 0 -2px 0 0 var(--accent); }
.csec.drop-after { box-shadow: 0 2px 0 0 var(--accent); }
.csec.dragging { opacity: .5; }
.chead {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0 6px 0 4px;
  height: 24px;
  text-align: left;
  color: var(--text);
  position: relative;
  user-select: none;
  border-radius: 3px;
}
.csec:not(.open) .chead { background: transparent; }
.chead:hover { background: var(--panel-3); }
.chev {
  font-size: 10px;
  line-height: 1;
  color: var(--muted);
  transition: transform .15s ease;
  flex: 0 0 auto;
  width: 10px;
  text-align: center;
}
.chev.flipped { transform: rotate(-90deg); }
.ctitle {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .4px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* —— 拖拽手柄（⠿，hover 标题行时出现） —— */
.drag-grip {
  flex: 0 0 auto;
  width: 14px;
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
}
.chead:hover .drag-grip { opacity: .7; }
.drag-grip:hover { opacity: 1; background: var(--accent-l); color: var(--accent-d); }
.drag-grip:active { cursor: grabbing; }
.chead-more {
  flex: 0 0 auto;
  width: 18px;
  height: 16px;
  display: grid;
  place-items: center;
  font-size: 14px;
  line-height: 1;
  color: var(--muted);
  border-radius: 3px;
  opacity: .65;
  transition: opacity .12s, background .12s, color .12s;
  letter-spacing: 1px;
}
.chead:hover .chead-more, .chead-more.shown { opacity: 1; }
.chead-more:hover { background: var(--accent-l); color: var(--accent-d); opacity: 1; }
.chead-actions { display: inline-flex; align-items: center; gap: 4px; }
.cbody { padding: 4px 6px 6px; }

/* 暗黑仿真模式：扁平分组（保持与浅色一致的 VS Code 风格） */
.app.sim-dark .csec { background: transparent; border-color: transparent; }
.app.sim-dark .csec.open { background: transparent; }
.app.sim-dark .csec:not(.open) .chead { background: transparent; }
.app.sim-dark .chead:hover { background: #262D38; }
.app.sim-dark .ctitle { color: #DDD; }
.app.sim-dark .chev { color: #888; }
.app.sim-dark .chead-more { color: #888; }
.app.sim-dark .chead-more:hover { background: rgba(0, 114, 189, .25); color: #6AB0F2; }
.app.sim-dark .drag-grip { color: #888; }
.app.sim-dark .drag-grip:hover { background: rgba(61, 165, 255, .18); color: #6AB0F2; }
.app.sim-dark .csec.drop-before, .app.sim-dark .csec.drop-after { box-shadow: 0 -2px 0 0 var(--accent); }
</style>
