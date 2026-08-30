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
        :title="t('拖动调整模块顺序')"
      >⠿</span>
      <span v-if="$slots.actions" class="chead-actions" @click.stop>
        <slot name="actions" />
      </span>
    </button>
    <!-- 包豪斯化：grid 轨道 0fr→1fr 平滑展开/折叠（替代 v-show 硬切换），丝滑不跳动 -->
    <div class="cbody" :class="{ on: isOpen }">
      <div class="cbody-in">
        <slot />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { t } from '../i18n'
import { useDragState } from '../composables/useDragSort'

const props = defineProps({
  title: { type: String, required: true },
  /** 默认折叠（ISA-101 少即是多），点击标题展开 */
  defaultOpen: { type: Boolean, default: false },
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
.chead-actions { display: inline-flex; align-items: center; gap: 4px; }
/* 包豪斯化：内容区用 grid 行轨道 0fr→1fr 实现平滑展开/折叠动画 */
.cbody { display: grid; grid-template-rows: 0fr; transition: grid-template-rows .24s cubic-bezier(.4, 0, .2, 1); }
.cbody.on { grid-template-rows: 1fr; }
.cbody-in { overflow: hidden; min-height: 0; padding: 4px 6px 6px; transition: padding .18s ease, opacity .18s ease; opacity: 1; }
.csec:not(.open) .cbody-in { padding: 0 6px; opacity: 0; }
/* 折叠时整体不可交互，避免键盘/点击落到隐藏内容 */
.csec:not(.open) .cbody { pointer-events: none; }

/* 暗黑仿真模式：扁平分组（保持与浅色一致的 VS Code 风格） */
.app.sim-dark .csec { background: transparent; border-color: transparent; }
.app.sim-dark .csec.open { background: transparent; }
.app.sim-dark .csec:not(.open) .chead { background: transparent; }
.app.sim-dark .chead:hover { background: #2A2E2A; }
.app.sim-dark .ctitle { color: #E2E0DA; }
.app.sim-dark .chev { color: #8E8C84; }
.app.sim-dark .drag-grip { color: #8E8C84; }
.app.sim-dark .drag-grip:hover { background: rgba(245, 169, 10, .18); color: #FFC42E; }
.app.sim-dark .csec.drop-before, .app.sim-dark .csec.drop-after { box-shadow: 0 -2px 0 0 var(--accent); }
</style>
