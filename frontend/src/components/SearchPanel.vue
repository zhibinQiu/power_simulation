<template>
  <div class="sp-wrap">
    <!-- 搜索框：关键词 + 仅场景 -->
    <div class="sp-search">
      <div class="sp-search-box" :class="{ active: filtering }">
        <svg class="search-ic" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input v-model="kw" type="text" class="sp-input" placeholder="搜索工艺、设备、物料、策略…" />
        <button v-if="kw" class="sp-clear" title="清除搜索" @click="kw = ''">✕</button>
      </div>
      <label class="sp-scene" :class="{ on: onlyScene }" title="仅显示已部署到场景中的资源">
        <input type="checkbox" v-model="onlyScene" />
        <span>仅场景</span>
      </label>
    </div>

    <!-- 搜索结果 -->
    <div class="sp-body" @scroll="onScroll" :class="{ scrolling }">
      <template v-if="!filtering">
        <div class="empty-hint">
          输入关键词搜索工艺、设备、物料与策略；<br/>
          勾选「仅场景」只显示当前已部署到场景中的资源。
        </div>
      </template>
      <template v-else>
        <div v-if="!results.length" class="empty-hint">未找到匹配资源</div>
        <div v-for="g in results" :key="g.key" class="sp-group">
          <div class="sp-group-title" @click="toggle(g.key)">
            <span class="twisty" :class="{ open: open[g.key] !== false }">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </span>
            <span class="sp-group-name">{{ g.label }}</span>
            <span class="sp-count">{{ g.items.length }}</span>
          </div>
          <div v-show="open[g.key] !== false" class="sp-items">
            <div v-for="it in g.items" :key="it.id" class="sp-item" :class="{ active: it.active }"
                 :title="it.title" @click="it.action && it.action()">
              <Icon :name="it.icon" :size="14" class="sp-item-ic" />
              <span class="sp-item-name">{{ it.label }}</span>
              <span v-if="it.sub" class="sp-item-sub">{{ it.sub }}</span>
              <span v-if="it.live != null" class="sp-item-live">{{ fmt(it.live) }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { MATERIALS, ROUTE_GROUPS, PROCESS_TEMPLATES, PROCESS_MAP } from '../data/flowLibrary'
import Icon from './Icon.vue'

const store = useSimStore()
const kw = ref('')
const onlyScene = ref(false)
const filtering = computed(() => kw.value.trim() !== '' || onlyScene.value)
const open = reactive({})
function toggle(key) { open[key] = open[key] === false ? true : false }

// 滚动条显隐（与左侧资源管理器一致）
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}

// 工艺是否已部署到场景
function procInScene(type) {
  const units = store.model && store.model.units ? store.model.units : []
  return units.some((u) => u.type === type)
}
// 打开工艺：工辅优先打开其设备详情，普通工艺打开工艺属性面板
function openProcess(type) {
  const t = PROCESS_MAP[type]
  if (t && t.route === 'aux') {
    const devId = store.linkedAuxDeviceOf(type)
    if (devId) { store.openDeviceDetail(devId); return }
  }
  store.selectAssetType(type)
}
function fmt(v) {
  if (v == null) return ''
  return typeof v === 'number' ? v.toFixed(2) : String(v)
}

// 分组搜索结果：工艺 / 设备 / 物料 / 策略
const results = computed(() => {
  const q = kw.value.trim().toLowerCase()
  const out = []

  // ---- 工艺 ----
  const procs = []
  for (const group of Object.values(ROUTE_GROUPS)) {
    for (const t of group) {
      if (onlyScene.value && !procInScene(t.type)) continue
      if (q && !t.label.toLowerCase().includes(q)) continue
      procs.push({
        id: 'proc:' + t.type,
        label: t.label,
        icon: 'process',
        active: store.selectedAssetType === t.type,
        title: '点击查看工艺属性' + (store.editMode ? '（可拖入编排画布）' : ''),
        action: () => openProcess(t.type),
      })
    }
  }
  if (procs.length) out.push({ key: 'process', label: '工艺', items: procs })

  // ---- 设备（场景内真实设备：计量 + 可调） ----
  const devs = []
  for (const d of store.allDevices) {
    const label = d.label || d.id
    const id = d.id
    if (q && !label.toLowerCase().includes(q) && !id.toLowerCase().includes(q)) continue
    devs.push({
      id: 'dev:' + id,
      label,
      icon: 'process',
      sub: d.unitName || (PROCESS_MAP[d.unitType] || {}).label || '',
      live: d.live,
      active: store.deviceDetailId === id,
      title: '点击查看设备详情与实时数据',
      action: () => store.openDeviceDetail(id),
    })
  }
  if (devs.length) out.push({ key: 'device', label: '设备', items: devs })

  // ---- 物料 ----
  const mats = []
  for (const m of MATERIALS) {
    if (onlyScene.value && !materialInScene(m.id)) continue
    if (q && !m.name.toLowerCase().includes(q)) continue
    mats.push({
      id: 'mat:' + m.id,
      label: m.name,
      icon: 'material',
      sub: m.cat || '',
      active: store.selectedMaterialId === m.id,
      title: '点击查看物料属性',
      action: () => store.selectMaterial(m.id),
    })
  }
  if (mats.length) out.push({ key: 'material', label: '物料', items: mats })

  // ---- 策略（工艺绿色策略 + 系统预置 + 自定义） ----
  const strats = []
  for (const t of PROCESS_TEMPLATES) {
    for (const gs of t.greenStrategies || []) {
      if (onlyScene.value && !(store.greenStrategiesFor(t.type) || []).includes(gs.id)) continue
      if (q && !gs.name.toLowerCase().includes(q)) continue
      strats.push({
        id: 'strat:' + t.type + ':' + gs.id,
        label: gs.name,
        icon: 'bolt',
        sub: t.label,
        active: store.selectedStrategyId === `green::${t.type}::${gs.id}`,
        title: '点击查看策略属性（可在右侧启用/停用）',
        action: () => store.selectGreenStrategy(t.type, gs.id),
      })
    }
  }
  for (const p of store.presets || []) {
    if (onlyScene.value && !p.applied) continue
    if (q && !(p.name || '').toLowerCase().includes(q)) continue
    strats.push({
      id: 'strat:preset:' + p.id,
      label: p.name || '未命名预置策略',
      icon: 'bolt',
      sub: '系统预置',
      active: store.selectedStrategyId === p.id,
      title: '点击查看策略属性（底部「策略仿真」进入仿真模式测试）',
      action: () => store.selectStrategy(p.id),
    })
  }
  for (const s of store.strategies || []) {
    if (onlyScene.value && !s.applied) continue
    if (q && !(s.name || '').toLowerCase().includes(q)) continue
    strats.push({
      id: 'strat:saved:' + s.id,
      label: s.name || '未命名策略',
      icon: 'bolt',
      sub: '自定义',
      active: store.selectedStrategyId === s.id,
      title: '点击查看策略属性（名称/数值调整可编辑）',
      action: () => store.selectStrategy(s.id),
    })
  }
  if (strats.length) out.push({ key: 'strategy', label: '策略', items: strats })

  return out
})

// 物料是否在场景中：被任一已部署工序作为输入/输出使用
function materialInScene(matId) {
  const units = store.model && store.model.units ? store.model.units : []
  return units.some((u) => {
    const t = PROCESS_MAP[u.type]
    if (!t) return false
    return (t.inputs || []).includes(matId) || (t.outputs || []).includes(matId)
  })
}
</script>

<style scoped>
.sp-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.sp-search { display: flex; align-items: center; gap: 6px; padding: 8px 10px 4px; flex: 0 0 auto; }
.sp-search-box {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: 5px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
  padding: 0 7px; height: 24px; transition: border-color .15s, box-shadow .15s;
}
.sp-search-box.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-l); }
.search-ic { color: var(--faint); flex: 0 0 auto; }
.sp-input {
  flex: 1; min-width: 0; border: none; outline: none; background: transparent;
  color: var(--text); font-size: 12px; padding: 0; height: 100%;
}
.sp-input::placeholder { color: var(--faint); }
.sp-clear {
  flex: 0 0 auto; width: 15px; height: 15px; display: grid; place-items: center;
  border: none; border-radius: 50%; background: transparent; color: var(--faint);
  font-size: 10px; cursor: pointer; padding: 0; line-height: 1;
}
.sp-clear:hover { color: var(--text); background: var(--border); }
.sp-scene {
  flex: 0 0 auto; display: flex; align-items: center; gap: 4px;
  font-size: 10.5px; color: var(--muted); cursor: pointer; user-select: none;
  padding: 3px 7px; border: 1px solid var(--border); border-radius: 6px;
  white-space: nowrap; transition: all .15s; line-height: 1;
}
.sp-scene input { display: none; }
.sp-scene:hover { color: var(--text); }
.sp-scene.on { color: var(--accent); border-color: var(--accent-l); background: var(--accent-l); }
.sp-body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 6px 12px; }
.sp-group { margin-top: 2px; }
.sp-group-title {
  display: flex; align-items: center; gap: 5px; padding: 4px 6px;
  font-size: 11.5px; font-weight: 600; color: var(--muted); cursor: pointer;
  border-radius: 4px; user-select: none;
}
.sp-group-title:hover { color: var(--text); background: var(--panel-2); }
.sp-group-name { flex: 1; }
.sp-count { font-size: 10.5px; color: var(--faint); font-weight: 400; }
.sp-items { padding-left: 6px; }
.sp-item {
  display: flex; align-items: center; gap: 6px; padding: 4px 8px;
  border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--text);
  user-select: none; min-width: 0;
}
.sp-item:hover { background: var(--panel-2); }
.sp-item.active { background: var(--accent-l); color: var(--accent); }
.sp-item-ic { flex: 0 0 auto; color: var(--accent2); opacity: .85; }
.sp-item-name { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-item-sub { flex: 0 1 auto; font-size: 10.5px; color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sp-item-live { flex: 0 0 auto; font-size: 10.5px; color: var(--accent2); font-variant-numeric: tabular-nums; }
.sp-body.scrolling { scrollbar-width: thin; }
.empty-hint { padding: 14px 10px; color: var(--faint); font-size: 11.5px; line-height: 1.7; }
</style>
