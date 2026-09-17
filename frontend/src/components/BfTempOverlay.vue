<!-- 高炉温度分区叠加层：以上传的高炉（空图）为基底，按炉体分区**着色 + 标注当前温度**。
     图上只显示「区带着色 + 该区当前温度数值」——不显示区名，也不显示温度区间/推荐范围。
     色带与数值同源，颜色由各区温度按色标插值得到，因此风口带随工况实时变化：
       - 风口带 = 理论燃烧温度 TFT：`buildRealtimeTftParams('blast_furnace', 工序参数, 热风炉/鼓风机设定)`
                  再经 collectTftContext 焓平衡计算 —— 风温/风量等设备设定一动，风口带数值与颜色即变；
       - 炉喉/炉身/炉腰/炉腹/炉缸 = 典型值（现场无层温测点，仅示意）；炉基常无不显示数值。
     两个易踩的坑：① 工序参数取 `store.model.units`（**不是** resultForView/baseline 的工序结果，
     那里没有 params）；② **不要用 `node.params`** —— 2D 节点（scheme 拷贝）里高炉 params 为空，
     传空对象会让 TFT 退化成 tft.js 的缺省参数（实测恒 1718℃，不随工况联动）。
     定位方式：与设备 PNG 共用显示盒与 viewBox（PNG alpha 外接盒），轮廓坐标 = 原图像素坐标，
     换图时自动跟随；但**换图后必须重跑 `scripts/gen-devimg-meta.py` 并重新标定 PROF/ZONES**
     （各图炉型比例不同，直接用旧坐标会整体错位）。 -->
<template>
  <svg :x="box.x" :y="box.y" :width="box.w" :height="box.h"
    :viewBox="`${meta.bx} ${meta.by} ${meta.bw} ${meta.bh}`"
    preserveAspectRatio="none" class="bf-temp-ov">
    <!-- 区带着色（沿内腔轮廓的多边形，叠在设备图上） -->
    <path v-for="z in zones" :key="'b' + z.key" :d="z.band" :fill="z.color" :fill-opacity="z.fillOp" stroke="none"/>
    <!-- 区带上下分界线：让相邻区带的边界一眼可辨 -->
    <path v-for="z in zones" :key="'e' + z.key" :d="z.edge" :stroke="z.color" stroke-opacity="0.9"
      :stroke-width="EDGE_W" fill="none"/>
    <!-- 各区当前温度（炉基无温度则不显示）。带深色描边光晕，保证在明暗两种图区上都可读 -->
    <template v-for="z in zones" :key="'t' + z.key">
      <text v-if="z.label" :x="z.cx" :y="z.ly" text-anchor="middle"
        :font-size="FS1" class="bf-t" fill="#ffffff">{{ z.label }}</text>
    </template>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { buildRealtimeTftParams, collectTftContext } from '../utils/tft'
import { makeTftConfig } from '../utils/coalBlend'

const props = defineProps({
  box: { type: Object, required: true },   // 设备图显示盒（devImgBox，节点局部坐标）
  meta: { type: Object, required: true },  // 图形真实边界（devImgMetaOf：bx/by/bw/bh）
  node: { type: Object, required: true },  // 2D 节点（取实例 id 与工序参数）
})

const store = useSimStore()

// 字号（viewBox = 原图像素坐标系）。区带内只有一行温度数值，最小区带（风口带）高 130，
// 88 号字（"2209℃" 宽约 280 图内像素）在区带内上下左右都留有余量，不会压到分界线。
const FS1 = 88
const EDGE_W = 7

// —— 炉内腔轮廓（原图像素坐标）——
// 按当前 高炉.png（1440×2880，图形外接盒 74,97,1266,2741）逐行实测「含中心的暗区」左右边界，
// x 限中心段以避开左右热风围管与外沿翻边；被围管/出铁口污染的几行（1700~1800、2090~2210、
// 2450~2630）按相邻干净行线性内插，保证轮廓连续、无台阶。
// ⚠ 逐点走这个表（而不是只用区带首末两点），否则锥段会被拉成直边、与炉型脱开。
const PROF = [
  [310, 600, 840], [360, 560, 868], [400, 535, 893], [440, 500, 929], [480, 497, 930],
  [560, 464, 963], [600, 457, 970], [700, 439, 986], [800, 422, 1001], [900, 402, 1022],
  [1000, 378, 1047], [1100, 359, 1066], [1200, 340, 1085], [1300, 324, 1101], [1400, 309, 1115],
  [1500, 295, 1129], [1600, 267, 1155], [1700, 280, 1140], [1800, 286, 1135], [1850, 289, 1132],
  [1910, 309, 1112], [1970, 318, 1101], [2030, 312, 1109], [2150, 300, 1122], [2270, 285, 1137],
  [2330, 279, 1144], [2390, 243, 1178], [2510, 235, 1188], [2630, 226, 1197], [2690, 222, 1202],
  [2750, 309, 1118], [2810, 476, 961], [2838, 560, 880],
]
function profAt(y) {
  const P = PROF
  if (y <= P[0][0]) return [P[0][1], P[0][2]]
  const last = P[P.length - 1]
  if (y >= last[0]) return [last[1], last[2]]
  for (let i = 0; i < P.length - 1; i++) {
    const a = P[i]
    const b = P[i + 1]
    if (y >= a[0] && y <= b[0]) {
      const t = (b[0] === a[0]) ? 0 : (y - a[0]) / (b[0] - a[0])
      return [a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
    }
  }
  return [P[0][1], P[0][2]]
}
const nf = (v) => v.toFixed(1)
// 区带多边形：左壁自上而下 → 右壁自下而上，中途带上轮廓控制点
function bandPath(y0, y1) {
  const ys = [y0, ...PROF.filter((p) => p[0] > y0 && p[0] < y1).map((p) => p[0]), y1]
  const left = ys.map((y) => `${nf(profAt(y)[0])} ${y}`)
  const right = ys.slice().reverse().map((y) => `${nf(profAt(y)[1])} ${y}`)
  return `M${left.join('L')}L${right.join('L')}Z`
}
function edgePath(y0, y1) {
  const a = profAt(y0)
  const b = profAt(y1)
  return `M${nf(a[0])} ${y0}H${nf(a[1])}M${nf(b[0])} ${y1}H${nf(b[1])}`
}

// —— 分区表 ——
// y0~y1 为区带在**原图**上的上下边界，按图上的炉型特征标定：
//   炉喉=顶部装料喇叭以下到炉身起坡 / 炉身=起坡到最宽的炉腰 / 炉腰=最宽段 / 炉腹=收口段 /
//   风口带=带齿状风口环（左右热风围管经下降管接在此处）/ 炉缸=风口环以下到炉基 / 炉基=底部座环。
// cur = 该区当前温度（℃）：既用于图上标注，也用于取色标色；风口带取实时 TFT（cur 为兜底值），
// 无测点的区域用典型值，炉基为常温（null → 中性冷色、不标注数值）。
const ZONES = [
  { key: 'throat', y0: 310, y1: 470, cur: 200 },
  { key: 'shaft', y0: 470, y1: 1500, cur: 800 },
  { key: 'belly', y0: 1500, y1: 1690, cur: 1200 },
  { key: 'bosh', y0: 1690, y1: 1860, cur: 1450 },
  { key: 'tuyere', y0: 1860, y1: 1990, cur: 2350 },
  { key: 'hearth', y0: 1990, y1: 2330, cur: 1500 },
  { key: 'base', y0: 2330, y1: 2838, cur: null },
]
// 数值纵向位置（图内像素）= 各区带垂直居中：文字基线 = 中心 + FS1*0.35（单行，无需让位）
const LB = { throat: 390, shaft: 985, belly: 1595, bosh: 1775, tuyere: 1925, hearth: 2160, base: 2584 }
const BASE_DY = FS1 * 0.35
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
  return ZONES.map((z) => {
    const cur = z.key === 'tuyere' ? (tft != null ? tft : z.cur) : z.cur
    const [l, r] = profAt(LB[z.key])
    return {
      key: z.key,
      // 图上只标当前温度；炉基无温度 → 不标注
      label: cur == null ? '' : `${cur}℃`,
      color: tempColor(cur),
      // 填充透明度取 0.24：默认缩放下高炉整体仅约 40×103 屏幕像素，分界线（7 图内像素）只有
      // 0.2 屏幕像素、几乎看不见，**分区只能靠色带本身传达**；再淡就分不出区了。
      fillOp: 0.24,
      band: bandPath(z.y0, z.y1),
      edge: edgePath(z.y0, z.y1),
      cx: (l + r) / 2,
      ly: LB[z.key] + BASE_DY,
    }
  })
})
</script>

<style scoped>
.bf-temp-ov { pointer-events: none; }
/* 深色描边光晕：区带着色后底色有明有暗（炉喉喇叭、风口环、炉基座环偏亮），
   白字 + 深晕在明暗两种图区上都可读 */
.bf-t {
  font-weight: 700; font-variant-numeric: tabular-nums;
  paint-order: stroke; stroke: #16202b; stroke-linejoin: round;
  stroke-width: 20;
}
</style>
