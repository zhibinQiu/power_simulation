<template>
  <div ref="el" class="panel">
    <svg :viewBox="`0 0 ${W} ${vbH}`" style="display:block; width:100%">
      <!-- links -->
      <path v-for="(l, i) in paths" :key="'p' + i" :d="l.d" :fill="l.color" opacity="0.45" />
      <!-- nodes -->
      <g v-for="n in drawnNodes" :key="n.id">
        <rect :x="n.x" :y="n.y" :width="NODE_W" :height="n.h" :fill="n.color" rx="2" />
        <text :x="n.labelX" :y="n.y + n.h / 2" :text-anchor="n.anchor"
              dominant-baseline="middle" font-size="10"
              :fill="store.simMode ? '#FFFFFF' : 'var(--text)'">
          {{ n.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<script setup>
/**
 * 桑基图通用底座（三段式布局 + 节点着色 + 贝塞尔流向带）。
 *
 * 碳素流（CarbonSankey）与能流（EnergySankey）此前各自复制了一份布局算法，
 * 仅数据源键 / 高度 / 着色规则不同；现统一由本组件承载，差异通过 props 注入，
 * 两个业务组件退化为十几行的配色声明（布局算法只有一处实现）。
 */
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'

const props = defineProps({
  /** store.resultForView 上的数据键：'sankey'（碳素流）/ 'sankey_energy'（能流） */
  dataKey: { type: String, required: true },
  /** 画布基准高度（未超出容器时的最小高度） */
  height: { type: Number, default: 340 },
  /** 底部留白 */
  pad: { type: Number, default: 12 },
  /** 与 store.resultForView.units 中工艺 id 匹配的前缀：'u:' / 'eu:' */
  nodePrefix: { type: String, required: true },
  /** 归入左列的节点 kind（碳：fuel；能：source + fuel） */
  leftKinds: { type: Array, default: () => ['fuel'] },
  /** 汇节点着色：(id) => color */
  sinkColor: { type: Function, required: true },
  /** 源/物料节点着色：(node) => color（非 sink/process/mid 时生效） */
  otherColor: { type: Function, default: () => '#ED7D31' },
  /** 流向带着色：(link, sourceNode, targetNode) => color；缺省按 sink/mid 规则推导 */
  linkColor: { type: Function, default: null },
})

const store = useSimStore()
const H = props.height
const NODE_W = 14
const TOP = 16

// 画布宽度跟随容器（右侧属性面板可拖拽调宽）：ResizeObserver 实时同步，避免横向滚动条
const el = ref(null)
const W = ref(560)
let ro = null
onMounted(() => {
  ro = new ResizeObserver(() => {
    if (el.value) W.value = Math.max(300, Math.round(el.value.clientWidth))
  })
  if (el.value) ro.observe(el.value)
})
onBeforeUnmount(() => { if (ro) ro.disconnect() })

/** 热负荷 → 绿-黄-红渐变（工艺节点着色） */
function hcolor(h) {
  if (h == null) return 'var(--faint)'
  const g = [46, 158, 99], y = [201, 154, 46], r = [209, 75, 75]
  let c
  if (h < 0.5) c = g.map((v, i) => Math.round(v + (y[i] - v) * h / 0.5))
  else c = y.map((v, i) => Math.round(v + (r[i] - v) * (h - 0.5) / 0.5))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

const layout = computed(() => {
  const sk = store.resultForView && store.resultForView[props.dataKey]
  if (!sk || !sk.nodes || !sk.nodes.length) return null
  // 三段式布局：左侧物料(原料) | 中间工艺 | 右侧物料(产物，含中间产品)，避免横向列多导致标签重叠
  const kindOf = {}
  sk.nodes.forEach((n) => (kindOf[n.id] = n.kind))
  const nodes = sk.nodes.map((n) => ({
    ...n,
    col: (n.kind === 'sink' || n.kind === 'mid') ? 2 : props.leftKinds.includes(n.kind) ? 0 : 1,
  }))
  // 工艺之间不连线：只保留「物料→工艺」「工艺→物料」，过滤「中间产品→工艺」的流转线
  const links = (sk.links || []).filter((l) => !(kindOf[l.source] === 'mid' && kindOf[l.target] === 'process'))
  const colKeys = [...new Set(nodes.map((n) => n.col))].sort((a, b) => a - b)
  const cols = {}
  colKeys.forEach((c) => (cols[c] = []))
  nodes.forEach((n) => cols[n.col].push(n))
  const lastCol = colKeys[colKeys.length - 1]
  const outSum = {}, inSum = {}
  links.forEach((l) => { outSum[l.source] = (outSum[l.source] || 0) + l.value; inSum[l.target] = (inSum[l.target] || 0) + l.value })
  const val = {}
  nodes.forEach((n) => {
    if (n.col === colKeys[0]) val[n.id] = outSum[n.id] || 0
    else if (n.col === lastCol) val[n.id] = inSum[n.id] || 0
    else val[n.id] = Math.max(outSum[n.id] || 0, inSum[n.id] || 0)
  })
  const top = TOP, avail = H - top - props.pad
  const colTotal = {}
  colKeys.forEach((c) => (colTotal[c] = 0))
  Object.keys(cols).forEach((c) => cols[c].forEach((n) => (colTotal[c] += val[n.id])))
  const maxTotal = Math.max(...Object.values(colTotal), 1)
  const gap = 10
  const scale = (avail - gap * 8) / maxTotal
  const span = W.value - 24 - 24 - NODE_W
  const colX = {}
  colKeys.forEach((c, i) => (colX[c] = 24 + (colKeys.length === 1 ? 0 : (span * i) / (colKeys.length - 1))))
  const pos = {}
  let bottom = 0
  colKeys.forEach((c) => {
    const arr = cols[c]
    const used = arr.reduce((s, n) => s + val[n.id], 0) * scale + gap * (arr.length - 1)
    let y = top + Math.max(0, (avail - used) / 2)
    arr.forEach((n) => {
      const h = Math.max(5, val[n.id] * scale)
      pos[n.id] = { x: colX[c], y, h, val: val[n.id] }
      y += h + gap
      bottom = Math.max(bottom, y - gap)
    })
  })
  const vbH = Math.ceil(bottom + props.pad)
  return { nodes, links, pos, scale, vbH, lastCol }
})

const vbH = computed(() => (layout.value ? layout.value.vbH : H))

const drawnNodes = computed(() => {
  if (!layout.value) return []
  const lastCol = layout.value.lastCol
  return layout.value.nodes.map((n) => {
    const p = layout.value.pos[n.id]
    const isProcess = n.kind === 'process'
    const res = store.resultForView && store.resultForView.units
      && store.resultForView.units.find((u) => props.nodePrefix + u.id === n.id)
    const color = n.kind === 'sink'
      ? props.sinkColor(n.id)
      : isProcess ? hcolor(res ? res.heat : 0.3)
        : n.kind === 'mid' ? 'var(--gas)' : props.otherColor(n)
    const anchor = n.col === lastCol ? 'end' : 'start'
    const labelX = n.col === lastCol ? p.x - 4 : p.x + NODE_W + 4
    return { ...n, ...p, color, anchor, labelX }
  })
})

function linkColorOf(l, s, t) {
  if (props.linkColor) return props.linkColor(l, s, t)
  if (t.kind === 'sink') return props.sinkColor(t.id)
  if (s.kind === 'mid' || t.kind === 'mid') return 'var(--gas)'
  return 'var(--faint)'
}

const paths = computed(() => {
  if (!layout.value) return []
  const { links, pos, val, scale } = layout.value
  const outCur = {}, inCur = {}
  Object.keys(pos).forEach((id) => { outCur[id] = pos[id].y; inCur[id] = pos[id].y })
  const out = []
  links.forEach((l) => {
    const s = pos[l.source], t = pos[l.target]
    if (!s || !t) return
    const w = Math.max(1, l.value * scale)
    const y0 = outCur[l.source]; outCur[l.source] += w
    const y1 = inCur[l.target]; inCur[l.target] += w
    const x0 = s.x + NODE_W, x1 = t.x
    const mx = (x0 + x1) / 2
    const color = linkColorOf(l, s, t)
    // 工艺与中间产品同列：改为向右的小弧线，避免水平反向弯曲重叠
    const d = Math.abs(x0 - x1) <= NODE_W + 1
      ? `M ${x1} ${y0} C ${x1 + 9} ${y0}, ${x1 + 9} ${y1}, ${x1} ${y1} L ${x1} ${y1 + w} C ${x1 + 9} ${y1 + w}, ${x1 + 9} ${y0 + w}, ${x1} ${y0 + w} Z`
      : `M ${x0} ${y0} C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1} L ${x1} ${y1 + w} C ${mx} ${y1 + w}, ${mx} ${y0 + w}, ${x0} ${y0 + w} Z`
    out.push({ d, color })
  })
  return out
})
</script>

<style scoped>
.panel { display: block; }
</style>
