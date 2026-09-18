<!-- 高炉温度分区叠加层：在程序化绘制的炉体图形上，按炉内腔分区**着色 + 标注当前温度**。
     图上只显示「区带着色 + 该区当前温度数值」——不显示区名，也不显示温度区间/推荐范围。
     色带与数值同源，颜色由各区温度按色标插值得到，因此风口带随工况实时变化：
       - 风口带 = 理论燃烧温度 TFT：`buildRealtimeTftParams('blast_furnace', 工序参数, 热风炉/鼓风机设定)`
                  再经 collectTftContext 焓平衡计算 —— 风温/风量等设备设定一动，风口带数值与颜色即变；
       - 炉喉/炉身/炉腰/炉腹/炉缸 = 典型值（现场无层温测点，仅示意）；炉基常无不显示数值。
     两个易踩的坑：① 工序参数取 `store.model.units`（**不是** resultForView/baseline 的工序结果，
     那里没有 params）；② **不要用 `node.params`** —— 2D 节点（scheme 拷贝）里高炉 params 为空，
     传空对象会让 TFT 退化成 tft.js 的缺省参数（实测恒 1718℃，不随工况联动）。

     定位方式（2026-09-17 改）：轮廓与区带全部用**归一化坐标 0~1**，直接乘以炉体图形盒
     （Twin2DView 的 figBox）得到实际位置。轮廓数据来自 data/twin2dFigures.js 的 BF_PROFILE，
     与炉体图形**同一份数据源** —— 旧方案按 PNG 像素坐标标定，换图必错位且要重跑标定脚本，
     现在改炉型只要改图形库的轮廓表，色带自动跟随、不会脱开。 -->
<template>
  <svg :x="box.x" :y="box.y" :width="box.w" :height="box.h" class="bf-temp-ov">
    <!-- 区带着色（沿内腔轮廓的多边形，叠在炉体图形上） -->
    <path v-for="z in zones" :key="'b' + z.key" :d="z.band" :fill="z.color" :fill-opacity="z.fillOp" stroke="none"/>
    <!-- 区带上下分界线：让相邻区带的边界一眼可辨 -->
    <path v-for="z in zones" :key="'e' + z.key" :d="z.edge" :stroke="z.color" stroke-opacity="0.9"
      :stroke-width="edgeW" fill="none"/>
    <!-- 各区当前温度（炉基无温度则不显示）。带深色描边光晕，保证在明暗两种图形上都可读 -->
    <template v-for="z in zones" :key="'t' + z.key">
      <text v-if="z.label" :x="z.cx" :y="z.ly" text-anchor="middle"
        :font-size="fs" :stroke-width="fs * 0.22" class="bf-t" fill="#ffffff">{{ z.label }}</text>
    </template>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { BF_PROFILE, BF_ZONES, bfProfAt } from '../data/twin2dFigures'
import { buildRealtimeTftParams, collectTftContext } from '../utils/tft'
import { makeTftConfig } from '../utils/coalBlend'

const props = defineProps({
  box: { type: Object, required: true },   // 炉体图形显示盒（figBox，节点局部坐标）
  node: { type: Object, required: true },  // 2D 节点（取实例 id 与工序参数）
})

const store = useSimStore()

// 字号/线宽：随图形盒缩放（旧方案写死 PNG 图内像素，换图后比例全乱）
// fs ≈ 图形高的 8.5%，区带内只有一行温度数值，最小区带（风口带）也放得下。
const fs = computed(() => Math.max(4, props.box.h * 0.085))
const edgeW = computed(() => Math.max(0.6, props.box.w * 0.006))

// 归一化 → 图形盒内坐标（必须返回**数字**：文本基线 y 还要在此基础上叠加字号偏移，
// 返回字符串会让 13.3 + 8.8 变成 '13.38.8' 这种非法长度值，SVG 直接报
// "<text> attribute y: Expected length"。路径里再统一取 1 位小数即可。）
const PX = (nx) => nx * props.box.w
const PY = (ny) => ny * props.box.h
const n1 = (v) => Math.round(v * 10) / 10
// 区带多边形：左壁自上而下 → 右壁自下而上，中途带上轮廓控制点
// （必须逐点走轮廓表，只取首末两点会把锥段拉成直边、与炉型脱开）
function bandPath(y0, y1) {
  const ys = [y0, ...BF_PROFILE.filter((p) => p[0] > y0 && p[0] < y1).map((p) => p[0]), y1]
  const left = ys.map((y) => `${n1(PX(bfProfAt(y)[0]))} ${n1(PY(y))}`)
  const right = ys.slice().reverse().map((y) => `${n1(PX(bfProfAt(y)[1]))} ${n1(PY(y))}`)
  return `M${left.join('L')}L${right.join('L')}Z`
}
function edgePath(y0, y1) {
  const a = bfProfAt(y0)
  const b = bfProfAt(y1)
  return `M${n1(PX(a[0]))} ${n1(PY(y0))}H${n1(PX(a[1]))}M${n1(PX(b[0]))} ${n1(PY(y1))}H${n1(PX(b[1]))}`
}

// 炉基无温度（炉底支撑、常温），用中性冷色
const NEUTRAL = '#7d8fa0'

// 温度色标：冷→热 = 蓝 → 青 → 黄绿 → 黄 → 橙 → 红橙 → 红 → 暗红。
// 用**多段线性插值**而不是硬分档：本图相邻区带温度往往只差 50~100℃（炉腹 1450 / 炉缸 1500），
// 硬分档会把它们涂成同一个颜色，反而看不出分区差异。
const RAMP = [
  [150, [47, 127, 224]], [600, [31, 169, 160]], [900, [134, 187, 53]], [1150, [216, 184, 26]],
  [1350, [232, 132, 28]], [1600, [221, 74, 24]], [2000, [193, 26, 8]], [2400, [137, 13, 5]],
]
const rgbStr = (c) => `rgb(${c[0]},${c[1]},${c[2]})`
function tempColor(t) {
  if (t == null) return NEUTRAL
  const R = RAMP
  if (t <= R[0][0]) return rgbStr(R[0][1])
  const last = R[R.length - 1]
  if (t >= last[0]) return rgbStr(last[1])
  for (let i = 0; i < R.length - 1; i++) {
    const a = R[i]
    const b = R[i + 1]
    if (t >= a[0] && t <= b[0]) {
      const k = (t - a[0]) / (b[0] - a[0])
      return rgbStr(a[1].map((v, j) => Math.round(v + (b[1][j] - v) * k)))
    }
  }
  return rgbStr(R[0][1])
}

// 实时 TFT 参数：工序参数（store.model.units，schema 侧默认值 + 编排改动）+ 热制度设备实际设定折算
const tftParams = computed(() => {
  const u = ((store.model && store.model.units) || []).find((x) => x.id === props.node.id)
  const sps = {}
  for (const dt of ['hot_blast_stove', 'blower']) {
    const did = `${props.node.id}::${dt}`
    const sp = store.deviceSetpoints[did]
    const es = store.deviceExtraSetpoints[did]
    if (sp != null || (es && Object.keys(es).length)) sps[dt] = { setpoint: sp, extraSetpoints: es || {} }
  }
  return buildRealtimeTftParams('blast_furnace', (u && u.params) || {}, sps)
})

const zones = computed(() => {
  const p = tftParams.value
  // 风口带 TFT：按当前工况实时焓平衡计算（参数不全时退回兜底值）
  let tft = null
  try {
    const c = collectTftContext(p, makeTftConfig(store.materialOverrides || {}))
    if (Number.isFinite(c.tft)) tft = Math.round(c.tft)
  } catch (e) { /* 参数不全时退回兜底值 */ }
  return BF_ZONES.map((z) => {
    const cur = z.key === 'tuyere' ? (tft != null ? tft : z.cur) : z.cur
    const yc = (z.y0 + z.y1) / 2
    const [l, r] = bfProfAt(yc)
    return {
      key: z.key,
      // 图上只标当前温度；炉基无温度 → 不标注
      label: cur == null ? '' : `${cur}℃`,
      color: tempColor(cur),
      // 填充透明度取 0.24：默认缩放下炉体只有几十屏幕像素，分界线几乎看不见，
      // **分区只能靠色带本身传达**；再淡就分不出区了。
      fillOp: 0.24,
      band: bandPath(z.y0, z.y1),
      edge: edgePath(z.y0, z.y1),
      cx: PX((l + r) / 2),
      ly: PY(yc) + fs.value * 0.35,
    }
  })
})
</script>

<style scoped>
.bf-temp-ov { pointer-events: none; }
/* 深色描边光晕：区带着色后底色有明有暗（炉喉喇叭、风口环、炉基座环偏亮），
   白字 + 深晕在明暗两种图形上都可读 */
.bf-t {
  font-weight: 700; font-variant-numeric: tabular-nums;
  paint-order: stroke; stroke: #16202b; stroke-linejoin: round;
}
</style>
