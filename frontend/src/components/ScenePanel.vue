<template>
  <div class="scn-wrap" :class="{ 'drop-back': dropBackOver }"
       @dragover="onBackOver" @dragleave="onBackLeave" @drop="onDropBack">
    <!-- 编排态提示 -->
    <div v-if="store.editMode" class="scn-edit-hint">
      {{ t('编排模式：以下为当前编排所对应场景的资源树，保存编排后场景将按此更新。') }}
    </div>

    <!-- 场景资源树：工序 → 设备（实时读数） -->
    <div class="scn-body tree" @scroll="onScroll" :class="{ scrolling }">
      <div v-if="!units.length" class="empty-hint">
        {{ t('场景暂无部署工序。') }}<br/>{{ t('可从「资源管理器」把工艺拖入编排画布完成部署。') }}
      </div>
      <div v-for="u in units" :key="u.id" class="tnode">
        <div class="tch sub" :class="{ active: store.selectedUnitId === u.id }"
             :title="u.type" @click="store.selectUnit(u.id)">
          <span class="twisty" :class="{ open: open[u.id] === true }" @click.stop="toggle(u.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </span>
          <span class="tch-dot" :title="t('已部署至场景')"></span>
          <span class="tch-tt">{{ u.name || (PROCESS_MAP[u.type] || {}).label || u.type }}</span>
        </div>
        <div class="tchildren" v-show="open[u.id] === true">
          <div v-if="!devsOf(u.id).length" class="empty-hint sm">{{ t('该工序暂无设备') }}</div>
          <div v-for="d in devsOf(u.id)" :key="d.id" class="tchild leaf dev-leaf click"
               :class="{ active: store.deviceDetailId === d.id, 'drag-src': dragId === d.id }"
               :draggable="!store.editMode"
               :title="(d.measures ? d.label + '（' + d.measures + '）' : d.label) + t(' · 拖拽至「数据分析」作为数据源')"
               @click="store.openDeviceDetail(d.id)"
               @dragstart="onDevDrag($event, d)"
               @dragend="onDevDragEnd">
            <span class="tc-tt">{{ d.label }}</span>
            <span v-if="d.adjustable" class="adj-badge" :title="t('可调设备：设定值可调节')">{{ t('可调') }}</span>
            <span class="dev-live">{{ fmt(d.live) }}<span v-if="d.unit" class="dev-unit">{{ d.unit }}</span></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'

const store = useSimStore()
// 场景菜单默认折叠设备子项（仅显示工序一级），点击 twisty 展开设备（二级）
const open = reactive({})
function toggle(key) { open[key] = !open[key] }

// 当前编排所对应场景的工序集合（运行态 = 已部署产线；编排态 = 编排画布中的方案节点）
const units = computed(() => {
  if (store.editMode && store.scheme && store.scheme.nodes && store.scheme.nodes.length) {
    return store.scheme.nodes.map((n) => ({
      id: n.id,
      // 直接显示实例名（如 热风炉、热风炉2、鼓风机），与 3D 场景铭牌/运行态一致；缺省时回退到类型名
      name: n.name || (PROCESS_MAP[n.type] || {}).label || n.type,
      type: n.type,
      editing: true,
    }))
  }
  return (store.model && store.model.units) || []
})
// 某工序下的设备（计量 + 可调，带实时读数）
function devsOf(unitId) {
  return store.allDevices.filter((d) => d.unitId === unitId)
}
function fmt(v) {
  if (v == null || isNaN(v)) return '—'
  return typeof v === 'number' ? v.toFixed(1) : String(v)
}

// 滚动条显隐
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}

// ==================== 设备拖拽 → 「工况数据分析」数据源 ====================
const dragId = ref(null)
function onDevDrag(e, d) {
  if (store.editMode) { e.preventDefault(); return }
  dragId.value = d.id
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('application/x-dv-device', JSON.stringify({
    id: d.id, label: d.label, unit: d.unit,
    unitId: d.unitId, unitName: d.unitName, unitType: d.unitType,
    color: d.color, reading: d.reading, adjustable: d.adjustable, range: d.range,
  }))
}
function onDevDragEnd() { dragId.value = null }

// ==================== 接收「拖回场景」：从工况数据分析把数据源拖回此处即移除 ====================
const dropBackOver = ref(false)
function onBackOver(e) {
  // 仅响应从数据源列表拖回的拖拽（带 application/x-dv-remove 标记），避免与拖出设备混淆
  if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('application/x-dv-remove')) {
    e.preventDefault()
    dropBackOver.value = true
  }
}
function onBackLeave() { dropBackOver.value = false }
function onDropBack(e) {
  e.preventDefault()
  dropBackOver.value = false
  try {
    const raw = e.dataTransfer.getData('application/x-dv-device')
    if (!raw) return
    const src = JSON.parse(raw)
    if (src && src._back && src.id) {
      store.removeDvSource(src.id)
      store.showToast(t('已把「{name}」移出工况数据源，如需重新添加请再次拖入', { name: src.label || src.id }), 'info')
    }
  } catch (err) {}
}
</script>

<style scoped>
.scn-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.scn-wrap.drop-back { outline: 2px dashed var(--accent); outline-offset: -2px; background: var(--accent-l); }
.scn-edit-hint { flex: 0 0 auto; margin: 6px 10px 0; padding: 6px 8px; font-size: 10.5px; line-height: 1.6; color: var(--warn, #9a6b08); background: var(--warn-l, rgba(255,180,0,.08)); border: 1px solid var(--warn-b, rgba(255,180,0,.25)); border-radius: 6px; }
.scn-body { flex: 1; min-height: 0; overflow-y: auto; padding: 6px 6px 12px; }
.scn-body.scrolling { scrollbar-width: thin; }
/* 工序行字体与资源管理器中对应工艺/物料条目（.tc-tt）保持一致：12px / 400 / 字距 .08px，
   覆盖全局 .tch.sub .tch-tt 的 500 字重与 .15px 字距，避免同一工艺词在两棵树的观感差异 */
.scn-body .tch.sub .tch-tt { font-weight: 400; letter-spacing: .08px; }
.empty-hint { padding: 14px 10px; color: var(--faint); font-size: 11.5px; line-height: 1.7; }
.empty-hint.sm { padding: 6px 10px; font-size: 10.5px; }
.adj-badge { flex: 0 0 auto; font-size: 9px; line-height: 1.7; color: var(--accent-d); background: var(--accent-l); border-radius: 5px; padding: 0 5px; }
.dev-live { margin-left: auto; font-size: 10.5px; color: var(--accent2); font-variant-numeric: tabular-nums; flex: 0 0 auto; }
.dev-unit { margin-left: 2px; color: var(--faint); font-size: 10px; }
.dev-leaf {
  cursor: grab;
  user-select: none; -webkit-user-select: none; -webkit-user-drag: element;
}
.dev-leaf:active { cursor: grabbing; }
.dev-leaf.drag-src { opacity: .45; }
</style>
