<template>
  <div class="twin2d">
    <!-- 顶部厂级 KPI 条（ISA-101：克制、层次清晰、信息密度适中） -->
    <div class="t2d-kpi">
      <div class="kpi"><span>{{ t('总碳排放') }}</span><b :style="{ color: '#a0522d' }">{{ fmt(totals.co2_total) }}</b><i>tCO₂/h</i></div>
      <div class="kpi"><span>{{ t('综合能耗') }}</span><b>{{ fmt(totals.energy_total) }}</b><i>GJ/h</i></div>
      <div class="kpi"><span>{{ t('吨钢强度') }}</span><b>{{ fmt(totals.intensity) }}</b><i>kgCO₂/t</i></div>
      <div class="kpi"><span>{{ t('钢产量') }}</span><b>{{ fmt(totals.steel_output) }}</b><i>t/h</i></div>
      <div class="kpi-sep"></div>
      <div class="kpi hint">
        <span class="lg"><i class="dot ok"></i>{{ t('数据') }}</span>
        <span class="lg"><i class="dot sel"></i>{{ t('选中') }}</span>
        <span class="lg"><i class="dot aux"></i>{{ t('辅助') }}</span>
        <span class="lg"><i class="dot feed"></i>{{ t('反馈') }}</span>
      </div>
      <button type="button" class="t2d-fit" @click="fitAll()" :title="t('适配画布（双击也可）')">{{ t('适配') }}</button>
    </div>

    <!-- 全新 2D 工艺流程图 SVG 画布（非 3D 俯视）：树状布局、正交管线、标准工艺图符 -->
    <div class="t2d-canvas" ref="wrap" @wheel.prevent="onWheel" @mousedown="onDown" @mousemove="onMove" @mouseup="onUp" @mouseleave="onUp" @dblclick="fitAll()">
      <!-- 不用 viewBox，完全由 JS 控制 zoom/pan，避免 viewBox 自动缩放与 group transform 双重缩放 -->
      <svg ref="svg" :style="{ cursor }">
        <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
          <!-- 网格底纹（工业图低对比网格） -->
          <g class="t2d-grid" stroke="#dfe4ea" stroke-width="1">
            <path v-for="l in gridV" :key="'gv'+l" :d="`M${l} 0 V${bounds.h}`"/>
            <path v-for="l in gridH" :key="'gh'+l" :d="`M0 ${l} H${bounds.w}`"/>
          </g>

          <!-- 管线（正交折线，物料色；反馈弧虚线） -->
          <g>
          <path v-for="c in lines" :key="c.id" :d="c.d" :stroke="c.color" :stroke-width="c.feedback ? 1.4 : 2.2"
            fill="none" :stroke-dasharray="c.feedback ? '5 4' : '0'" class="t2d-link"
            @mouseenter="hovered = c.id" @mouseleave="hovered = null" @click.stop="selectConn(c)"/>
          <circle v-for="c in lines" :key="'m'+c.id" :cx="c.mx" :cy="c.my" r="3.5" fill="#fff" :stroke="c.color" stroke-width="1.6"/>
          <text v-for="c in lines" :key="'t'+c.id" :x="c.mx + 7" :y="c.my + 3.5" class="t2d-mat" :fill="c.color">{{ c.matName }}</text>
          </g>

          <!-- 工艺卡片 -->
          <g v-for="n in nodes" :key="n.id" :transform="`translate(${n.x},${n.y})`"
            :class="['t2d-node', { on: isSel(n), aux: isAux(n) }]"
            @click.stop="onNode(n)" @mouseenter="hovered = n.id" @mouseleave="hovered = null">
            <rect class="t2d-card" :width="NW" :height="nodeH(n)" rx="4"/>
            <rect class="t2d-head" :width="NW" :height="HEADER" rx="4"/>
            <rect class="t2d-head-fill" :width="NW - 10" :height="HEADER - 10" x="5" y="5" rx="3"/>
            <text class="t2d-name" x="10" y="21">{{ n.name }}</text>
            <text class="t2d-abbr" :x="NW - 10" y="21" text-anchor="end">{{ abbr(n) }}</text>

            <!-- 工艺标准图符（24×24，与状态色联动） -->
            <g class="t2d-icon" :transform="`translate(14,${HEADER + 10}) scale(1.45)`">
              <template v-for="(el, ei) in iconOf(n.type)" :key="ei">
                <path v-if="el.tag === 'path'" :d="el.d" :stroke-width="el.sw" :stroke-linecap="el.lc" :stroke-linejoin="el.lj" fill="none"/>
                <circle v-else-if="el.tag === 'circle'" :cx="el.cx" :cy="el.cy" :r="el.r" :stroke-width="el.sw" fill="none"/>
                <ellipse v-else-if="el.tag === 'ellipse'" :cx="el.cx" :cy="el.cy" :rx="el.rx" :ry="el.ry" :stroke-width="el.sw" fill="none"/>
                <rect v-else-if="el.tag === 'rect'" :x="el.x" :y="el.y" :width="el.width" :height="el.height" :rx="el.rx" :stroke-width="el.sw" fill="none"/>
              </template>
            </g>

            <!-- 状态点 -->
            <circle class="t2d-state" :cx="NW - 10" :cy="HEADER + 30" r="3.5" :fill="stateColor(n)"/>

            <!-- 端口（in 左 / out 右） -->
            <circle v-for="(p, i) in (n.ports && n.ports.in) || []" :key="'i'+p.id" :cx="8" :cy="portY(i)" r="4.5" class="t2d-port in" :fill="portColor(p.material)"/>
            <circle v-for="(p, i) in (n.ports && n.ports.out) || []" :key="'o'+p.id" :cx="NW - 8" :cy="portY(i)" r="4.5" class="t2d-port out" :fill="portColor(p.material)"/>

            <!-- 底部 KPI（仅主工艺显示，ISA-101 信息密度：关键量优先） -->
            <g v-if="isMain(n)" class="t2d-kpis">
              <text x="10" :y="nodeH(n) - 14" class="t2d-kpi-c">CO₂ {{ fmt(unitOf(n).co2_total) }} t/h</text>
              <text x="10" :y="nodeH(n) + 0" class="t2d-kpi-e">能耗 {{ fmt(unitOf(n).energy_total) }} GJ/h</text>
            </g>
          </g>
        </g>
      </svg>
    </div>

    <!-- 空方案提示 -->
    <div v-if="!nodes.length" class="t2d-empty">{{ t('暂无可编排工艺方案，请先在「流程编排」中构建工艺路线') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'
import { nodeHeight, NODE_NW, MATERIAL_MAP, PROCESS_MAP } from '../data/flowLibrary'
import { T2D_ICONS } from './twin2dIcons'

const store = useSimStore()
const wrap = ref(null)
const svg = ref(null)

const NW = NODE_NW
const HEADER = 32
const GAP = 24
const PAD = 56

// —— 布局（深拷贝方案节点，用工艺树布局在 2D 画布上独立排布，不污染编辑画布） ——
const nodes = ref([])
const conns = ref([])
const bounds = ref({ x: 0, y: 0, w: 1000, h: 600 })

function relayout() {
  const raw = store.scheme && store.scheme.nodes ? store.scheme.nodes : []
  const rawC = store.scheme && store.scheme.connections ? store.scheme.connections : []
  const ns = JSON.parse(JSON.stringify(raw)).filter((n) => n && n.kind === 'process')
  const cs = JSON.parse(JSON.stringify(rawC))

  // 独立 2D 布局：主工艺一行横向流水线；工辅/公用工程在下方两行（ISA-101 流程图布局）
  const mainIds = new Set()
  const mainNodes = [], auxNodes = []
  for (const n of ns) {
    if (isMain(n)) { mainNodes.push(n); mainIds.add(n.id) }
    else { auxNodes.push(n) }
  }
  // 主工艺按 scheme 原始顺序排（buildScheme 已按流程编排拓扑生成），一眼看去就是工艺流
  let x = 80, y = 100
  for (const n of mainNodes) { n.x = x; n.y = y; x += 288 }
  // 工辅在下方，每行最多 5 个
  x = 80; y = 100 + nodeHeight({ ports: { in: [1], out: [1] } }) + 140
  for (let i = 0; i < auxNodes.length; i++) {
    if (i > 0 && i % 5 === 0) { x = 80; y += nodeHeight(auxNodes[i]) + 60 }
    auxNodes[i].x = x; auxNodes[i].y = y; x += 260
  }

  // 计算包围盒
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const n of ns) {
    x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y)
    x1 = Math.max(x1, n.x + NW); y1 = Math.max(y1, n.y + nodeHeight(n))
  }
  if (x0 === Infinity) { x0 = 0; y0 = 0; x1 = 1200; y1 = 700 }
  const pad = PAD
  bounds.value = { x: x0 - pad, y: y0 - pad, w: x1 - x0 + pad * 2, h: y1 - y0 + pad * 2 }
  nodes.value = ns
  conns.value = cs
  nextTick(fitAll)
}

const viewBox = computed(() => `${bounds.value.x} ${bounds.value.y} ${bounds.value.w} ${bounds.value.h}`)

// 网格线（在内容坐标系内生成）
const gridV = computed(() => {
  const arr = []
  for (let x = Math.ceil(bounds.value.x / 80) * 80; x < bounds.value.x + bounds.value.w; x += 80) arr.push(Math.round(x))
  return arr
})
const gridH = computed(() => {
  const arr = []
  for (let y = Math.ceil(bounds.value.y / 80) * 80; y < bounds.value.y + bounds.value.h; y += 80) arr.push(Math.round(y))
  return arr
})

// 节点几何（端口中心与 FlowEditor 一致：y = 76 + i*GAP 相对卡片顶）
function nodeH(n) { return nodeHeight(n) }
function portY(i) { return 76 + i * GAP }
function portPos(n, dir, portId) {
  const arr = dir === 'in' ? n.ports.in : n.ports.out
  const i = arr.findIndex((p) => p.id === portId)
  return { x: dir === 'in' ? n.x + 13 : n.x + NW - 13, y: n.y + 76 + i * GAP }
}

function isAux(n) { return !isMain(n) }
function isMain(n) { const t = PROCESS_MAP[n.type]; return !!t && t.route === 'steel' }
function abbr(n) {
  const map = {
    sinter_plant: 'SIN', pelletizing: 'PEL', coke_oven: 'COK', blast_furnace: 'BF',
    hot_metal_pretreat: 'HMP', bof: 'BOF', ladle_furnace: 'LF', rh_vacuum: 'RH',
    caster: 'CCM', rolling_mill: 'RM', eaf: 'EAF', dri_midrex: 'DRI',
    reheating_furnace: 'RHF', gas_power: 'GPP', waste_heat: 'WH', ccs: 'CCS',
    blower: 'BLW', hot_blast_stove: 'HBS', id_fan: 'IDF', injector: 'INJ',
    combustion_blower: 'CBF', drive_supply: 'DRV', electrode_reg: 'ELR',
    belt_conv: 'BEL', feeder: 'FDR', cool_pump: 'CWP', aux_boiler: 'ABL',
    oxy_plant: 'OXP', oxy_supply: 'OXS', power_supply: 'PWS',
  }
  return map[n.type] || n.type.slice(0, 3).toUpperCase()
}
function iconOf(t) { return T2D_ICONS[t] || T2D_ICONS.default }

// 物料颜色（ISA-101 克制用色）
function portColor(m) { return (MATERIAL_MAP[m] || {}).color || '#8a97a5' }
function matName(m) { return (MATERIAL_MAP[m] || {}).name || m }

// 实时结果（node id = unit id）
function unitOf(n) {
  const units = store.resultForView && store.resultForView.units ? store.resultForView.units : []
  return units.find((x) => x.id === n.id) || {}
}
function isSel(n) { return store.selectedUnitId === n.id || store.selectedFlowId === n.id }
function stateColor(n) {
  const u = unitOf(n)
  if (u.co2_total != null || u.energy_total != null) return '#3a9d6d'
  return '#aab3bd'
}

// 管线正交路径（工业流程图：先水平、后垂直、再水平）
function lineOf(c) {
  const f = nodes.value.find((n) => n.id === c.from)
  const t = nodes.value.find((n) => n.id === c.to)
  if (!f || !t) return null
  const p1 = portPos(f, 'out', c.fromPort)
  const p2 = portPos(t, 'in', c.toPort)
  const dx = 26
  const midX = (p1.x + p2.x) / 2
  const d = c.feedback
    ? `M ${p1.x} ${p1.y} H ${p1.x + dx} V ${p2.y} H ${p2.x + dx} V ${p2.y} H ${p2.x}`
    : (p1.x <= p2.x
      ? `M ${p1.x} ${p1.y} H ${p1.x + dx} V ${p2.y} H ${p2.x}`
      : `M ${p1.x} ${p1.y} H ${p1.x + dx} V ${midX} H ${p2.x - dx} V ${p2.y} H ${p2.x}`)
  return { d, mx: (p1.x + p2.x) / 2, my: (p1.y + p2.y) / 2 }
}
const lines = computed(() => {
  const out = []
  for (const c of conns.value) {
    const g = lineOf(c)
    if (!g) continue
    out.push({
      id: c.id, d: g.d, mx: g.mx, my: g.my,
      feedback: !!c.feedback,
      color: c.feedback ? '#8a97a5' : portColor(c.material),
      matName: matName(c.material),
    })
  }
  return out
})

// 交互：缩放 / 平移 / 选中
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })
const hovered = ref(null)
const dragging = ref(false)
const last = ref({ x: 0, y: 0 })
const cursor = computed(() => (dragging.value ? 'grabbing' : 'grab'))

// 坐标映射：内容坐标系 → 屏幕坐标系
function fitAll() {
  if (!svg.value || !nodes.value.length) { zoom.value = 1; pan.value = { x: 0, y: 0 }; return }
  const rect = svg.value.getBoundingClientRect()
  // 以主工艺行宽度为准，横向占满容器宽度的 88%（最小 0.35，最大 1.1）
  const mainNodes = nodes.value.filter((n) => isMain(n))
  const mainW = mainNodes.length
    ? Math.max(...mainNodes.map((n) => n.x + NW)) - Math.min(...mainNodes.map((n) => n.x)) + 40
    : bounds.value.w
  zoom.value = Math.max(0.38, Math.min(1.1, (rect.width * 0.88) / mainW))
  // 左上角对齐，右侧/下方可滚动查看；向下留出 KPI 条高度避免遮挡
  pan.value = { x: -bounds.value.x + 16, y: -bounds.value.y + 54 }
}
function onWheel(e) {
  if (!svg.value) return
  const rect = svg.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const worldX = mx / zoom.value - pan.value.x
  const worldY = my / zoom.value - pan.value.y
  const f = e.deltaY < 0 ? 1.12 : 0.88
  const nz = Math.min(3.2, Math.max(0.25, zoom.value * f))
  pan.value = {
    x: mx / nz - worldX,
    y: my / nz - worldY,
  }
  zoom.value = nz
}
function onDown(e) {
  if (e.button !== 0) return
  dragging.value = true
  last.value = { x: e.clientX, y: e.clientY }
}
function onMove(e) {
  if (!dragging.value || !svg.value) return
  const dx = e.clientX - last.value.x, dy = e.clientY - last.value.y
  pan.value = { x: pan.value.x + dx / zoom.value, y: pan.value.y + dy / zoom.value }
  last.value = { x: e.clientX, y: e.clientY }
}
function onUp() { dragging.value = false }

function onNode(n) {
  if (n.kind === 'device') return
  store.pickUnit(n.id)
}
function selectConn(c) {
  const cObj = conns.value.find((x) => x.id === c.id)
  if (cObj) store.pickUnit(cObj.from)
}

function fmt(n) {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
const totals = computed(() => (store.resultForView && store.resultForView.totals) || {})

let ro = null
onMounted(() => {
  relayout()
  ro = new ResizeObserver(() => fitAll())
  if (wrap.value) ro.observe(wrap.value)
})
onBeforeUnmount(() => { if (ro) ro.disconnect() })
// 方案变化 → 重排
watch(() => store.scheme, () => relayout(), { deep: true })
</script>

<style scoped>
.twin2d {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: #f2f4f6;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  user-select: none;
}
/* —— 厂级 KPI 条 —— */
.t2d-kpi {
  display: flex; align-items: center; gap: 20px;
  padding: 8px 16px 8px 54px;  /* 左侧避让 3D/2D 切换工具列 */
  background: #fff;
  border-bottom: 1px solid #dde3ea;
  box-shadow: 0 1px 3px rgba(20, 40, 60, 0.06);
  z-index: 2;
}
.kpi { display: flex; align-items: baseline; gap: 6px; }
.kpi span { font-size: 11px; color: #6b7785; }
.kpi b { font-size: 15px; color: #2b3a4a; font-variant-numeric: tabular-nums; }
.kpi i { font-size: 11px; color: #8a97a5; font-style: normal; }
.kpi-sep { width: 1px; height: 24px; background: #e2e7ec; }
.kpi.hint { gap: 10px; font-size: 11px; color: #6b7785; white-space: nowrap; }
.kpi.hint .lg { display: inline-flex; align-items: center; gap: 4px; }
.kpi.hint .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.ok { background: #3a9d6d; }
.dot.sel { background: #2c6e9e; }
.dot.aux { background: #aab3bd; }
.dot.feed { background: #8a97a5; }
.t2d-fit {
  margin-left: auto;
  border: 1px solid #cdd5dd; background: #fff; color: #33475b;
  border-radius: 4px; font-size: 12px; padding: 3px 12px; cursor: pointer;
}
.t2d-fit:hover { border-color: #2c6e9e; color: #2c6e9e; }
/* —— 画布 —— */
.t2d-canvas {
  position: relative; flex: 1; overflow: hidden;
  cursor: grab;
}
.t2d-canvas svg { width: 100%; height: 100%; display: block; }
.t2d-grid { opacity: 0.5; }
/* 管线 */
.t2d-link { opacity: 0.85; transition: opacity .15s; }
.t2d-link:hover { opacity: 1; }
.t2d-mat { font-size: 10px; fill: #6b7785; letter-spacing: 0.02em; }
/* 工艺卡片 */
.t2d-node { cursor: pointer; }
.t2d-card { fill: #ffffff; stroke: #a8b4c0; stroke-width: 1; }
.t2d-node:hover .t2d-card { stroke: #2c6e9e; stroke-width: 1.5; }
.t2d-node.on .t2d-card {
  stroke: #c47f17; stroke-width: 2;
  filter: drop-shadow(0 0 5px rgba(196, 127, 23, 0.25));
}
.t2d-head { fill: #2c6e9e; }
.t2d-head-fill { fill: rgba(255, 255, 255, 0.12); }
.t2d-node.aux .t2d-head { fill: #8a97a5; }
.t2d-node.aux .t2d-card { fill: #fafbfc; }
.t2d-name { font-size: 12px; font-weight: 600; fill: #fff; }
.t2d-abbr {
  font-size: 10px; font-weight: 700; fill: rgba(255, 255, 255, 0.75);
  letter-spacing: 0.08em;
}
.t2d-icon { stroke: #2b3a4a; color: #2b3a4a; opacity: 0.92; }
.t2d-node.aux .t2d-icon { stroke: #6b7785; color: #6b7785; }
.t2d-state { stroke: #fff; stroke-width: 1; }
/* 端口 */
.t2d-port { stroke: #fff; stroke-width: 1.6; }
.t2d-port.in { stroke: #2c6e9e; }
.t2d-port.out { stroke: #8a97a5; }
/* 卡片底部 KPI */
.t2d-kpis { font-size: 11px; }
.t2d-kpi-c { fill: #9a4d33; font-weight: 600; }
.t2d-kpi-e { fill: #33475b; }
.t2d-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #8a97a5; font-size: 14px; background: #f2f4f6;
}
</style>
