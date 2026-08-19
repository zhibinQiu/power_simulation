<template>
  <div class="scn-wrap">
    <!-- 场景概要（标题由侧边栏头部统一显示，这里只保留统计） -->
    <div class="scn-head">
      <div class="scn-stats">
        <span class="scn-badge">{{ units.length }} 道工序</span>
        <span v-if="units.length">设备 <b>{{ deviceCount }}</b></span>
        <span v-if="units.length">实时排放 <b>{{ fmt(liveTotalCo2) }}</b> tCO₂/h</span>
      </div>
    </div>

    <!-- 编排态提示 -->
    <div v-if="store.editMode" class="scn-edit-hint">
      编排模式：以下为当前编排所对应场景的资源树，保存编排后场景将按此更新。
    </div>

    <!-- 场景资源树：工序 → 设备（实时读数） -->
    <div class="scn-body tree" @scroll="onScroll" :class="{ scrolling }">
      <div v-if="!units.length" class="empty-hint">
        场景暂无部署工序。<br/>可从「资源管理器」把工艺拖入编排画布完成部署。
      </div>
      <div v-for="u in units" :key="u.id" class="tnode">
        <div class="tch sub" :class="{ active: store.selectedUnitId === u.id }"
             :title="u.type" @click="store.selectUnit(u.id)">
          <span class="twisty" :class="{ open: open[u.id] !== false }" @click.stop="toggle(u.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          </span>
          <span class="tch-dot" title="已部署至场景"></span>
          <span class="tch-tt">{{ u.name || (PROCESS_MAP[u.type] || {}).label || u.type }}</span>
          <span class="tch-count">{{ devsOf(u.id).length }}</span>
        </div>
        <div class="tchildren" v-show="open[u.id] !== false">
          <div v-if="!devsOf(u.id).length" class="empty-hint sm">该工序暂无设备</div>
          <div v-for="d in devsOf(u.id)" :key="d.id" class="tchild leaf dev-leaf click"
               :class="{ active: store.deviceDetailId === d.id }"
               :title="d.measures ? d.label + '（' + d.measures + '）' : d.label"
               @click="store.openDeviceDetail(d.id)">
            <span class="tc-tt">{{ d.label }}</span>
            <span v-if="d.adjustable" class="adj-badge" title="可调设备：设定值可调节">可调</span>
            <span class="dev-live">{{ fmt(d.live) }}<span v-if="d.unit" class="dev-unit">{{ d.unit }}</span></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'

const store = useSimStore()
const open = reactive({})
function toggle(key) { open[key] = open[key] === false ? true : false }

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
const deviceCount = computed(() => store.allDevices.length)
// 实时排放总量：优先取最新遥测，其次取当前方案计算结果
const liveTotalCo2 = computed(() => {
  if (store.live && store.live.total_co2 != null) return store.live.total_co2
  const r = store.resultForView
  return r && r.totals ? r.totals.co2_total : 0
})
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
</script>

<style scoped>
.scn-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.scn-head { flex: 0 0 auto; padding: 8px 10px 6px; border-bottom: 1px solid var(--border); }
.scn-badge { font-size: 10px; color: var(--accent); background: var(--accent-l); border-radius: 8px; padding: 1px 7px; }
.scn-stats { display: flex; gap: 12px; align-items: center; font-size: 10.5px; color: var(--muted); }
.scn-stats b { color: var(--text); font-variant-numeric: tabular-nums; }
.scn-edit-hint { flex: 0 0 auto; margin: 6px 10px 0; padding: 6px 8px; font-size: 10.5px; line-height: 1.6; color: var(--warn, #9a6b08); background: var(--warn-l, rgba(255,180,0,.08)); border: 1px solid var(--warn-b, rgba(255,180,0,.25)); border-radius: 6px; }
.scn-body { flex: 1; min-height: 0; overflow-y: auto; padding: 6px 6px 12px; }
.scn-body.scrolling { scrollbar-width: thin; }
.empty-hint { padding: 14px 10px; color: var(--faint); font-size: 11.5px; line-height: 1.7; }
.empty-hint.sm { padding: 6px 10px; font-size: 10.5px; }
.adj-badge { flex: 0 0 auto; font-size: 9px; line-height: 1.7; color: var(--accent); background: var(--accent-l); border-radius: 5px; padding: 0 5px; }
.dev-live { margin-left: auto; font-size: 10.5px; color: var(--accent2); font-variant-numeric: tabular-nums; flex: 0 0 auto; }
.dev-unit { margin-left: 2px; color: var(--faint); font-size: 10px; }
</style>
