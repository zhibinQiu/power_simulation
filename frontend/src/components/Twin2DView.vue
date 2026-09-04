<template>
  <div class="twin2d">
    <!-- 顶部厂级 KPI 条（ISA-101：克制、层次清晰、信息密度适中）；全屏时右侧避让全屏工具按钮 -->
    <div class="t2d-kpi" :class="{ fs: store.fullscreenOn }">
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
        <defs>
          <!-- 工业风渐变（金属/热态/冷态） -->
          <linearGradient id="g-metal-v" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#e6ecf2"/><stop offset="1" stop-color="#8a97a5"/>
          </linearGradient>
          <linearGradient id="g-metal-d" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#9aa6b3"/><stop offset="1" stop-color="#566570"/>
          </linearGradient>
          <linearGradient id="g-hot-v" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#ffb347"/><stop offset="0.5" stop-color="#f47720"/><stop offset="1" stop-color="#b03a0a"/>
          </linearGradient>
          <linearGradient id="g-hot-h" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#ff8a3d"/><stop offset="1" stop-color="#c2430e"/>
          </linearGradient>
          <linearGradient id="g-cool-v" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#7ec1ec"/><stop offset="1" stop-color="#2c6e9e"/>
          </linearGradient>
          <linearGradient id="g-cool-h" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#7ec1ec"/><stop offset="1" stop-color="#2c6e9e"/>
          </linearGradient>
          <!-- 管线流向箭头（线色自动继承） -->
          <marker id="arrow-fwd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" opacity="0.95"/>
          </marker>
          <marker id="arrow-back" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#8a97a5" opacity="0.9"/>
          </marker>
          <!-- 卡片金属底 + 顶部色条渐变 -->
          <linearGradient id="g-card" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#fbfcfd"/><stop offset="1" stop-color="#dde3ea"/>
          </linearGradient>
          <linearGradient id="g-card-hdr" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#2c6e9e"/><stop offset="1" stop-color="#1d4e72"/>
          </linearGradient>
          <linearGradient id="g-card-hdr-aux" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#7d8a9a"/><stop offset="1" stop-color="#5a6675"/>
          </linearGradient>
        </defs>
        <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
          <!-- 网格底纹（工业图低对比网格） -->
          <g class="t2d-grid" stroke="#dfe4ea" stroke-width="1">
            <path v-for="l in gridV" :key="'gv'+l" :d="`M${l} 0 V${bounds.h}`"/>
            <path v-for="l in gridH" :key="'gh'+l" :d="`M0 ${l} H${bounds.w}`"/>
          </g>

          <!-- 辅助系统分组虚线框（衬于卡片/连线之下，展示「一组辅助设备」；不拦截交互） -->
          <g v-for="g in groups" :key="g.key" class="t2d-grp" :transform="`translate(${g.x},${g.y})`">
            <rect class="t2d-grp-frame" :width="g.w" :height="g.h" rx="7"/>
            <circle class="t2d-grp-dot" cx="13" cy="17" r="3"/>
            <text class="t2d-grp-title" x="24" y="21">{{ g.label }}</text>
            <text class="t2d-grp-n" :x="g.w - 14" y="21" text-anchor="end">{{ g.count }} 台</text>
          </g>

          <!-- 组中组：系统框内按设备类型再套一层二级虚线框（如同一送风系统里的 热风炉×3 / 鼓风机×3） -->
          <g v-for="s in subFrames" :key="s.kid" class="t2d-subgrp" :transform="`translate(${s.x},${s.y})`">
            <rect class="t2d-subgrp-frame" :width="s.w" :height="s.h" rx="4"/>
            <text class="t2d-subgrp-title" x="7" y="14">{{ s.label }}</text>
            <text class="t2d-subgrp-n" :x="s.w - 8" y="14" text-anchor="end">{{ s.count }} 台</text>
          </g>

          <!-- 管线（正交折线，物料色；反馈弧虚线。中点标物料名小标签，不参与点击） -->
          <g>
            <path v-for="c in lines" :key="c.id" :d="c.d" :stroke="c.color" :stroke-width="c.feedback ? 1.6 : c.sw"
              fill="none" :stroke-dasharray="c.feedback ? '5 4' : '0'" :marker-end="c.feedback ? 'url(#arrow-back)' : 'url(#arrow-fwd)'" class="t2d-link"/>
            <circle v-for="c in lines" :key="'m'+c.id" :cx="c.mx" :cy="c.my" r="2.5" fill="#fff" :stroke="c.color" stroke-width="1.4" class="t2d-mid"/>
            <text v-for="c in lines" :key="'t'+c.id" :x="c.mx + 6" :y="c.my + 3" class="t2d-mat" :fill="c.color">{{ c.matName }}</text>
          </g>

          <!-- 设备节点：无卡片底，设备平面图直接作为主体（参考水泥行业图：设备本体 + 名称浮签 + 实时数据） -->
          <g v-for="n in nodes" :key="n.id" :transform="`translate(${n.x},${n.y})`"
            :class="['t2d-node', { on: isSel(n), aux: isAux(n) }]"
            @click.stop="onNode(n)" @mouseenter="hovered = n.id" @mouseleave="hovered = null">
            <!-- 设备名称浮签（节点顶部居中） -->
            <text class="t2d-name" :x="boxW(n)/2" y="18" text-anchor="middle">{{ n.name }}</text>

            <!-- 设备主体：优先贴真实设备图（已自动裁透明边；视口铺满可用图带并横向外扩，等比 contain 居中）；
                 无图时退回矢量图元（立体图符按节点图带等比放大，描边宽随缩放反除保持细线质感） -->
            <image v-if="devImgOf(n)" :x="devImgBox(n).x" :y="devImgBox(n).y" :width="devImgBox(n).w" :height="devImgBox(n).h" :href="devImgOf(n)" preserveAspectRatio="xMidYMid meet" class="t2d-figimg"/>
            <g v-else class="t2d-fig" :transform="`translate(${figOf(n).x},${figOf(n).y}) scale(${figOf(n).s})`">
              <template v-for="(el, ei) in iconOf(n.type)" :key="ei">
                <path v-if="el.tag === 'path'" :d="el.d" :stroke="el.stroke" :stroke-width="(el.sw||0)/figOf(n).s" :stroke-linecap="el.lc" :stroke-linejoin="el.lj" :fill="el.fill || 'none'"/>
                <circle v-else-if="el.tag === 'circle'" :cx="el.cx" :cy="el.cy" :r="el.r" :stroke="el.stroke" :stroke-width="(el.sw||0)/figOf(n).s" :fill="el.fill || 'none'"/>
                <ellipse v-else-if="el.tag === 'ellipse'" :cx="el.cx" :cy="el.cy" :rx="el.rx" :ry="el.ry" :stroke="el.stroke" :stroke-width="(el.sw||0)/figOf(n).s" :fill="el.fill || 'none'" :transform="el.transform || ''"/>
                <rect v-else-if="el.tag === 'rect'" :x="el.x" :y="el.y" :width="el.width" :height="el.height" :rx="el.rx || 0" :stroke="el.stroke" :stroke-width="(el.sw||0)/figOf(n).s" :fill="el.fill || 'none'"/>
                <polygon v-else-if="el.tag === 'polygon'" :points="el.pts.map(p => p.join(',')).join(' ')" :stroke="el.stroke" :stroke-width="(el.sw||0)/figOf(n).s" :fill="el.fill || 'none'"/>
              </template>
            </g>


            <!-- 底部实时 KPI（仅主工艺，悬浮在设备下方） -->
            <text v-if="isMain(n)" :x="boxW(n)/2" :y="boxH(n) - 7" text-anchor="middle" class="t2d-kpis">
              <tspan class="t2d-kpi-c">CO₂ {{ fmt(unitOf(n).co2_total) }} t/h</tspan>
              <tspan class="t2d-kpi-sep">　·　</tspan>
              <tspan class="t2d-kpi-e">能耗 {{ fmt(unitOf(n).energy_total) }} GJ/h</tspan>
            </text>
          </g>
        </g>
      </svg>
    </div>

    <!-- 空方案提示 -->
    <div v-if="!nodes.length" class="t2d-empty">{{ t('暂无可编排工艺方案，请先在「流程编排」中构建工艺路线') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'
import { MATERIAL_MAP, PROCESS_MAP } from '../data/flowLibrary'
import { T2D_ICONS, T2D_GEOM, T2D_INOUT } from '../data/twin2dIcons'

const store = useSimStore()
const wrap = ref(null)
const svg = ref(null)

const PAD = 56

// —— 辅助系统分组（2D 图将非主工艺节点按「系统」归组，每组一个虚线框） ——
const AUX_SYS_DEF = [
  { key: 'wind',    label: '高炉送风系统',   types: ['hot_blast_stove', 'blower', 'combustion_blower'] },
  { key: 'pci',     label: '喷煤系统',       types: ['injector'] },
  { key: 'dedust',  label: '除尘抽风系统',   types: ['id_fan'] },
  { key: 'oxygen',  label: '全厂供氧系统',   types: ['oxy_supply', 'oxy_plant'] },
  { key: 'power',   label: '供配电系统',     types: ['power_supply', 'drive_supply', 'electrode_reg'] },
  { key: 'therm',   label: '热力与冷却系统', types: ['aux_boiler', 'cool_pump'] },
  { key: 'feed',    label: '原料输送系统',   types: ['belt_conv', 'feeder'] },
  { key: 'carbon',  label: '节能减碳(公用)', types: ['gas_power', 'waste_heat', 'ccs'] },
  { key: 'others',  label: '其他辅助',       types: [] },
]
const GRP_HEAD = 34     // 组框标题带高
const GRP_PAD_X = 26    // 组框左右内边距
const GRP_PAD_B = 16    // 组框底部内边距
const GRP_GAP_X = 40    // 组间横向间距
const GRP_GAP_Y = 30    // 组间纵向间距（放不下换行时）
const AUX_GAP_X = 34    // 组内设备横向间距
const AUX_ROW_CAP = 5   // 组内每行设备上限
const AUX_GAP_ROW = 26  // 组内行间距
// —— 组中组几何 ——
const SUB_PAD_X = 14
const SUB_PAD_Y = 12
const SUB_TITLE_H = 20
const SUB_GAP_Y = 16
const SUB_TOP = 14
const SUB_BOTTOM = 14

// —— 布局（深拷贝方案节点，用工艺树布局在 2D 画布上独立排布，不污染编辑画布） ——
const nodes = ref([])
const conns = ref([])
const groups = ref([])
const subFrames = ref([])
const bounds = ref({ x: 0, y: 0, w: 1000, h: 600 })
const mainBand = ref({ l: 80, r: 900, top: 100, bot: 700 })

function relayout() {
  const raw = store.scheme && store.scheme.nodes ? store.scheme.nodes : []
  const rawC = store.scheme && store.scheme.connections ? store.scheme.connections : []
  const ns = JSON.parse(JSON.stringify(raw)).filter((n) => n && n.kind === 'process')
  const cs = JSON.parse(JSON.stringify(rawC))

  const mainNodes = [], auxNodes = []
  for (const n of ns) {
    if (isMain(n)) mainNodes.push(n)
    else auxNodes.push(n)
  }
  // 主工艺按 scheme 原始顺序横排，设备以平面图落地
  // 矩形布局：主工艺占右半（右上 rowA 横排 + 右下 LF 折返竖链），辅助占左半。
  // rowA 从「辅助目标宽 + 主辅间距」开始，把左侧整块留给辅助组铺开，主+辅合起来填满矩形画布。
  // 紧凑参数：AUX_TARGET_W/MAIN_GAP 调小让画布宽 ≤ 容器宽，zoom 自然升高、设备屏幕更大。
  const MAIN_GAP = 50
  const FOLD_GAP = 116 // 横向主带与折返纵向链之间 / 纵向链层间的净空（留折返横带）
  const AUX_TARGET_W = 700    // 辅助区域目标宽度（矩形左半，~3 列 × 单台宽 200+gaps）
  const MAIN_AUX_GAP = 50      // 主行与辅助区的横向间距
  // 折返：LF(LF 精炼)之后的工序不再继续向右横排成一条直线，而是沿 LF 中心列逐台向下排成
  // 「纵向链」（RH → 连铸 → 热轧），像产线总图一样竖着走下去，占矩形右半下部。
  const FOLD_TYPE = 'ladle_furnace'
  const foldI = mainNodes.findIndex((n) => n.type === FOLD_TYPE)
  const rowA = foldI >= 0 ? mainNodes.slice(0, foldI + 1) : mainNodes
  const colB = foldI >= 0 ? mainNodes.slice(foldI + 1) : []
  let x = AUX_TARGET_W + MAIN_AUX_GAP, y = 100
  for (const n of rowA) { n.x = x; n.y = y; x += boxW(n) + MAIN_GAP }
  if (colB.length) {
    const lf = rowA[rowA.length - 1]
    const lfCx = lf.x + boxW(lf) / 2
    let cy = lf.y + boxH(lf) + FOLD_GAP
    for (const n of colB) { n.x = lfCx - boxW(n) / 2; n.y = cy; cy += boxH(n) + FOLD_GAP }
  }
  const bandBot = rowA.length ? Math.max(...rowA.map((n) => n.y + boxH(n))) : 0
  const mainBottom = mainNodes.length
    ? Math.max(...mainNodes.map((n) => n.y + boxH(n)))
    : null
  const mainW = mainNodes.length
    ? Math.max(...mainNodes.map((n) => n.x + boxW(n))) - Math.min(...mainNodes.map((n) => n.x))
    : 900
  mainBand.value = {
    l: mainNodes.length ? Math.min(...mainNodes.map((n) => n.x)) : 80,
    r: mainNodes.length ? Math.max(...mainNodes.map((n) => n.x + boxW(n))) : 900,
    top: mainNodes.length ? rowA[0].y : 100,
    bot: bandBot, // 只指「横向主带」底；折返纵向链在它下方，走廊/顶带判定不把它当主带
  }

  // —— 辅助设备 → 系统分组 ——
  const sysOf = (n) => {
    const def = AUX_SYS_DEF.find((d) => d.types.includes(n.type))
    return def ? def.key : 'others'
  }
  const bySys = new Map(AUX_SYS_DEF.map((d) => [d.key, { ...d, items: [] }]))
  for (const n of auxNodes) bySys.get(sysOf(n)).items.push(n)
  const auxGroups = AUX_SYS_DEF.map((d) => bySys.get(d.key)).filter((g) => g.items.length)

  // —— 每个辅助组的「主连接目标列 x 中心」 ——
  // 把辅助组摆到「它对外连线最密集的主设备」正下方，让组↔主设备之间的折线尽量短（多数情况下
  // 就只是一段短竖线 / 一个直角）。权重：连到主设备 = 1、连到另一辅助组 = 0.5、组内自连 = 0。
  const mainCenX = new Map(mainNodes.map((m) => [m.id, m.x + boxW(m) / 2]))
  const allById = new Map(ns.map((n) => [n.id, n]))
  const groupOfNode = new Map()
  for (const g of auxGroups) for (const n of g.items) groupOfNode.set(n.id, g)
  const anchorX = (g) => {
    let sx = 0, sw = 0
    for (const n of g.items) {
      for (const c of cs) {
        let peer = null, isInternal = false
        if (c.from === n.id) { peer = allById.get(c.to); isInternal = groupOfNode.get(c.to) === g }
        else if (c.to === n.id) { peer = allById.get(c.from); isInternal = groupOfNode.get(c.from) === g }
        if (!peer || isInternal) continue
        if (mainCenX.has(peer.id)) { sx += mainCenX.get(peer.id); sw += 1 }
        else if (groupOfNode.has(peer.id)) { sx += peer.x + boxW(peer) / 2; sw += 0.5 }
      }
    }
    return sw > 0 ? sx / sw : (mainNodes.length ? mainCenX.get(mainNodes[Math.floor(mainNodes.length / 2)].id) : 600)
  }

  const typeLabel = (type) => (PROCESS_MAP[type] && PROCESS_MAP[type].label) || type

  // 平铺排布（单类型组）
  const placeFlat = (g, gx0, gy0) => {
    g.x = gx0; g.y = gy0
    g.count = g.items.length
    g.subs = []
    let cy = gy0 + GRP_HEAD
    let maxRowW = 0
    for (let i = 0; i < g.items.length; i += AUX_ROW_CAP) {
      const row = g.items.slice(i, i + AUX_ROW_CAP)
      let cx = gx0 + GRP_PAD_X, rh = 0
      for (const n of row) { n.x = cx; n.y = cy; cx += boxW(n) + AUX_GAP_X; rh = Math.max(rh, boxH(n)) }
      const rowW = cx - AUX_GAP_X - (gx0 + GRP_PAD_X)
      maxRowW = Math.max(maxRowW, rowW)
      cy += rh + AUX_GAP_ROW
    }
    g.w = maxRowW + GRP_PAD_X * 2
    g.h = cy - gy0 - AUX_GAP_ROW + GRP_PAD_B
  }
  // 组中组排布（多类型组）
  const placeNested = (g, gx0, gy0) => {
    g.x = gx0; g.y = gy0
    g.count = g.items.length
    const order = [], byType = new Map()
    for (const n of g.items) {
      let cl = byType.get(n.type)
      if (!cl) { cl = { type: n.type, label: typeLabel(n.type), count: 0, items: [] }; byType.set(n.type, cl); order.push(n.type) }
      cl.count++; cl.items.push(n)
    }
    g.subs = []
    let top = gy0 + GRP_HEAD + SUB_TOP, maxW = 0
    for (const type of order) {
      const cl = byType.get(type)
      cl.x = gx0 + SUB_PAD_X
      cl.y = top
      let cy = cl.y + SUB_TITLE_H, maxRowW = 0
      for (let i = 0; i < cl.items.length; i += AUX_ROW_CAP) {
        const row = cl.items.slice(i, i + AUX_ROW_CAP)
        let cx = cl.x + SUB_PAD_X, rh = 0
        for (const n of row) { n.x = cx; n.y = cy; cx += boxW(n) + AUX_GAP_X; rh = Math.max(rh, boxH(n)) }
        const rowW = cx - AUX_GAP_X - (cl.x + SUB_PAD_X)
        maxRowW = Math.max(maxRowW, rowW)
        cy += rh + AUX_GAP_ROW
      }
      cl.w = maxRowW + SUB_PAD_X * 2
      cl.h = cy - AUX_GAP_ROW - cl.y + SUB_PAD_Y
      maxW = Math.max(maxW, cl.w)
      g.subs.push(cl)
      top = cl.y + cl.h + SUB_GAP_Y
    }
    g.w = maxW + SUB_PAD_X * 2
    g.h = top - SUB_GAP_Y - gy0 + SUB_BOTTOM
  }
  const placeGroup = (g, gx0, gy0) => {
    const multiType = new Set(g.items.map((n) => n.type)).size > 1
    multiType ? placeNested(g, gx0, gy0) : placeFlat(g, gx0, gy0)
  }

  // —— 4 个辅助系统按用户指定位置分列排布 ——
  //   焦炉列：喷煤(pci) 在焦炉正下，高炉送风(wind) 在喷煤之下。
  //   烧结/球团列：除尘抽风(dedust) 留在烧结/球团正下方中央列。
  //   铁水预处理/转炉列：全厂供氧(oxygen) 右移到该列正下方，并额外下压 OXY_DROP(画布右下角)。
  // 每列起始 y = 该列参考设备盒底 + STACK_TOP_PAD + drop；组中心对齐该列参考中心 x。
  //   drop 只给 oxygen 用：避免它与左侧除尘抽风组在同一水平带上互相挤占。
  const STACK_TOP_PAD = 30
  const STACK_GAP_Y = 40
  // 主设备带底 → 辅助系统组框顶 之间的最小留白(即「横向走廊」宽度)。
  // 必须 > feedback 回流虚线的走廊偏移(mainBot + 24),否则虚线会压在辅助系统虚线框上。
  const CORRIDOR_GAP = 40
  const OXY_DROP = 150      // 全厂供氧组相对「参考盒底 + STACK_TOP_PAD」的额外下压量
  const findN = (type) => mainNodes.find((n) => n.type === type)
  const sinterN = findN('sinter_plant')
  const pelletN = findN('pelletizing')
  const cokeN   = findN('coke_oven')
  const bfN     = findN('blast_furnace')
  const pretN   = findN('hot_metal_pretreat')
  const bofN    = findN('bof')
  const colCx = (a, b) => (a && b)
    ? (a.x + boxW(a) / 2 + b.x + boxW(b) / 2) / 2
    : (a ? a.x + boxW(a) / 2 : (b ? b.x + boxW(b) / 2 : null))
  const STACK_COLUMNS = [
    { keys: ['pci', 'wind'],
      cx: cokeN ? cokeN.x + boxW(cokeN) / 2 : null,
      refY: cokeN ? cokeN.y + boxH(cokeN) : mainBand.value.bot },
    { keys: ['dedust'],
      cx: colCx(sinterN, pelletN),
      refY: Math.min(
        sinterN ? sinterN.y + boxH(sinterN) : Infinity,
        pelletN ? pelletN.y + boxH(pelletN) : Infinity) },
    { keys: ['oxygen'],
      cx: colCx(pretN, bofN) || (pretN ? pretN.x + boxW(pretN) / 2 : (bfN ? bfN.x + boxW(bfN) / 2 : null)),
      refY: Math.max(
        bfN ? bfN.y + boxH(bfN) : -Infinity,
        pretN ? pretN.y + boxH(pretN) : -Infinity),
      drop: OXY_DROP },
  ]
  const stackGroups = []
  // 1) 其余组(restGroups)走「原 anchorX 升序 + 流式多行」,放在主带左外侧辅助矩形(80..AUX_TARGET_W)
  const STACK_KEY_SET = new Set(STACK_COLUMNS.flatMap((c) => c.keys))
  const restGroups = auxGroups.filter((g) => !STACK_KEY_SET.has(g.key))
  restGroups.forEach((g) => { g.anchorX = anchorX(g); g._order = AUX_SYS_DEF.findIndex((d) => d.key === g.key) })
  restGroups.sort((a, b) => a.anchorX - b.anchorX || a._order - b._order)
  // 2) 每列在「该列参考设备盒底之下」按列内 keys 顺序纵向堆叠,每组中心对齐该列 cx
  //    (x 允许落在主带盒所在 x 段,但 gy 起点已 > 参考盒底,y 与主带盒 y 段不交,不冲突)
  for (const col of STACK_COLUMNS) {
    if (col.cx == null) continue
    // 下限 = 主带底 + CORRIDOR_GAP：在主设备带与辅助系统之间留出横向走廊,
    // 供 feedback 回流虚线(cy = mainBot + 24)等走线,避免压住辅助系统的虚线框。
    let gy = Math.max(col.refY + STACK_TOP_PAD + (col.drop || 0), mainBand.value.bot + CORRIDOR_GAP)
    for (const k of col.keys) {
      const g = auxGroups.find((g) => g.key === k)
      if (!g) continue
      // 用占位 x 算出 g.w/g.h 后再覆盖为最终 cx 对齐的 x
      placeGroup(g, 80, gy)
      const finalX = Math.max(80, col.cx - g.w / 2)
      placeGroup(g, finalX, gy)
      stackGroups.push(g)
      gy += g.h + STACK_GAP_Y
    }
  }
  // 3) restGroups 走原「组外流式」排布(同原逻辑,仅在 restGroups 数组上)
  const auxX0 = 80
  const auxY0 = 100
  const auxMaxW = AUX_TARGET_W
  let gy = auxY0, lineH = 0, lineEnd = auxX0
  for (const g of restGroups) {
    placeGroup(g, auxX0, gy)
    const prefX = Math.max(auxX0, Math.min(g.anchorX - g.w / 2, auxX0 + auxMaxW - g.w))
    let rowEnd = lineEnd
    if (prefX < rowEnd + GRP_GAP_X && rowEnd > auxX0) {
      gy += lineH + GRP_GAP_Y
      lineH = 0
      rowEnd = auxX0
    }
    const finalX = Math.max(prefX, rowEnd + GRP_GAP_X)
    placeGroup(g, finalX, gy)
    lineEnd = finalX + g.w
    lineH = Math.max(lineH, g.h)
  }
  // 合并回 auxGroups 供后续 subFrames / bounds 使用;顺序 rest 在前(展示用),stack 在后(主带下方)
  auxGroups.length = 0
  auxGroups.push(...restGroups, ...stackGroups)
  // 展平二级子框（多类型组才有），模板据此画「组中组」虚线框
  const sf = []
  for (const g of auxGroups) for (const s of g.subs || []) sf.push({ kid: `${g.key}--${s.type}`, label: s.label, count: s.count, x: s.x, y: s.y, w: s.w, h: s.h })
  subFrames.value = sf

  // 计算包围盒（主卡 ∪ 辅助组框），保证「适配」后全部框与连线可见
  // 矩形化：外框强制为 (80,100) → (mainRight, max(主底, 辅底)) 的矩形，主+辅合起来填满画布。
  const rectL = 80
  const rectT = 100
  const rectR = mainNodes.length ? Math.max(...mainNodes.map((n) => n.x + boxW(n))) : 1200
  const mainBotY = mainBottom != null ? mainBottom : 0
  // 逆向连线数（估算返回通道占用高度）
  let bwdN = 0
  for (const c of cs) {
    const f = ns.find((n) => n.id === c.from)
    const t = ns.find((n) => n.id === c.to)
    if (!f || !t) continue
    if ((f.x + boxW(f) - 13) - (t.x + 13) > FWD_TOL) bwdN++
  }
  const frameBottom = auxGroups.length ? Math.max(...auxGroups.map((g) => g.y + g.h)) : 0
  const rectB = Math.max(mainBotY, frameBottom)
  const floor = rectB + 26 + bwdN * LANE_STEP + 20
  const pad = PAD
  bounds.value = { x: rectL - pad, y: rectT - pad, w: rectR - rectL + pad * 2, h: Math.max(rectB, floor) - rectT + pad * 2 }
  nodes.value = ns
  groups.value = auxGroups
  conns.value = rewriteConnTopology(ns, cs)
  nextTick(fitAll)
  probeImgs()   // 设备 PNG 探测：命中后用图替矢量，结果缓存免重试
}

// 网格线（在内容坐标系内生成）
const gridV = computed(() => {
  const arr = []
  for (let x = Math.ceil(bounds.value.x / 80) * 80; x < bounds.value.x + bounds.value.w; x += 80) arr.push(x)
  return arr
})
const gridH = computed(() => {
  const arr = []
  for (let y = Math.ceil(bounds.value.y / 80) * 80; y < bounds.value.y + bounds.value.h; y += 80) arr.push(y)
  return arr
})

// —— 节点图幅几何 ——
const KPI_H = 26
function boxW(n) { return (T2D_GEOM[n.type] || T2D_GEOM.default).w }
function boxH(n) {
  const g = T2D_GEOM[n.type] || T2D_GEOM.default
  const cnt = Math.max(
    (n.ports && n.ports.in ? n.ports.in.length : 0),
    (n.ports && n.ports.out ? n.ports.out.length : 0), 1)
  // 端口扩展间距 12（原 24）：主工艺端口位置已全部由 T2D_INOUT 图标坐标决定（portPos
  // 走 anc 分支），此扩展只对 portY 均布兜底的设备生效；间距过大会把高炉(9 入口)撑到
  // 304 高、破坏主工艺统一尺寸(330×230 → 246)，收紧后全部回落统一高度。
  const h = Math.max(g.h, 96 + (cnt - 1) * 12)
  return isMain(n) ? h + KPI_H : h
}
// 端口纵向：在节点腰部带内均布（顶部名称之下、底部 KPI/留白之上）
function portY(n, dir, i) {
  const arr = (n.ports && n.ports[dir]) || []
  const cnt = Math.max(arr.length, 1)
  const H = boxH(n)
  const top = 30
  const bot = H - (isMain(n) ? 50 : 16)
  const span = Math.max(24, bot - top)
  return top + (i + 0.5) * (span / cnt)
}

// —— 连接拓扑按位置重映射 ————————————————————————
//
// store.scheme.connections 的 from/to 是「具体实例 id」(oxy_supply_1 / 鼓风机3 等),
// 它是按工艺树手工写死的。但 2D 视图的矩形布局里我们把同一组(`oxy_supply`,`blower` ...)
// 的多台设备「贴左下角矩形铺开」，物理位置与「原来从属哪个主设备」不再对应 ——
// 例如「供氧系统 1」原本从属转炉，但在新布局里它被塞到了离「鼓风机 3」很近的位置，
// 此时仍按 store 把 from=供氧1 to=转炉 画出来，就会出线从左下角一路折回到右上主行，
// 主↔辅连线大弯。
//
// 这里的策略是：**2D 视图渲染时,只重写 conn 里「辅助」那一端的设备引用** ——
// 对每条 conn，取其 from/to 中「是辅助」的那个端,改指到「与对端主设备位置最近、且
// 已被引用次数最少的同 type 设备」。
// - 主设备端不改（保持工艺拓扑稳定）。
// - 设备本身(id/image/label)不变 —— 只换「连线接哪台」。
// - 不会污染 store：conns.value 是 relayout 内部副本，store 仍按原拓扑供 3D/引擎用。
// - 平衡分配：`ref` 计数约束,后到的 conn 不全扎堆最近那台,允许次近距离替补。
//
// 编号语义锁定：这些辅助类型在 SCHEME_AUX 中显式指定了「第几台服务谁」
// (如 供氧系统1/2/3→鼓风机1/2/3、供氧系统4→铁水预处理、供氧系统5→转炉)，
// 2D 渲染不再就近重排,严格按 store 拓扑显示(保证图上编号对应与数据语义一致)。
const LOCKED_AUX = ['oxy_supply']
function rewriteConnTopology(ns, cs) {
  const allById = new Map()
  const poolByType = new Map()
  for (const n of ns) {
    allById.set(n.id, n)
    if (isMain(n)) continue
    if (!poolByType.has(n.type)) poolByType.set(n.type, [])
    poolByType.get(n.type).push({
      id: n.id,
      cx: n.x + boxW(n) / 2,
      cy: n.y + boxH(n) / 2,
      ref: 0,
    })
  }
  const csOut = []
  for (const c of cs) {
    const c2 = { ...c }
    for (const end of ['from', 'to']) {
      const oldN = allById.get(c2[end])
      const peerKey = end === 'from' ? 'to' : 'from'
      const peer = allById.get(c2[peerKey])
      if (!oldN || isMain(oldN) || !peer) continue
      if (LOCKED_AUX.includes(oldN.type)) continue // 编号锁定：该辅助端保持 store 指定,不就近重排
      const pool = poolByType.get(oldN.type) || []
      if (pool.length < 2) continue // 单台：没有备选,不浪费重算
      const bx = peer.x + boxW(peer) / 2
      const by = peer.y + boxH(peer) / 2
      // 选「ref 最小、距离最近」的候选;ref 越小越优先(均摊),距离越小越优先
      let best = null
      let bestRef = Infinity
      let bestDist = Infinity
      for (const cand of pool) {
        const d = Math.hypot(cand.cx - bx, cand.cy - by)
        if (cand.ref < bestRef || (cand.ref === bestRef && d < bestDist)) {
          best = cand
          bestRef = cand.ref
          bestDist = d
        }
      }
      // 当前 from/to 已经是最优邻位：不重排,但同样要记一次引用(ref++)——
      // 否则该设备被占用却不计数,后续 conn 会把它误当「空闲最近台」抢走,
      // 造成一台设备被多个不同主目标争用、连线反而变长。
      const cur = pool.find((c3) => c3.id === c2[end])
      if (cur && cur.id === best.id) { cur.ref++; continue }
      // 防自环：from/to 分属不同 type 池理论上不会同指,但防御性兜底——
      // 若改后两端变成同一台设备,回退本次改写。
      const prevEnd = c2[end]
      c2[end] = best.id
      if (c2.from === c2.to) { c2[end] = prevEnd }
      else {
        best.ref++
        // 端口 id 是 per-instance uid,旧设备的端口在新设备的 ports[] 里 findIndex === -1
        // → portPos 会走 fallback 把所有改写线都画到「右/左边的第一个端口」(顶槽),5 条
        // 氧气线从同一开口出来,视觉重叠。同步把 fromPort/toPort 换成「同 material 的端口」,
        // 让新设备按物料语义打开对应端口,5 条氧气线分散到不同端口开口。
        const dir = end === 'from' ? 'out' : 'in'
        const newN = allById.get(c2[end])
        if (newN && newN.ports && newN.ports[dir]) {
          const port = newN.ports[dir].find((p) => p.material === c.material)
          if (port) c2[end + 'Port'] = port.id
        }
      }
    }
    csOut.push(c2)
  }
  return csOut
}

// 端口锚点：按行业入料特点，把端口放到设备图符上真实的入/出口位置（T2D_INOUT），
// 下标缺失时回退到「图幅左右均布」的旧行为（保证未知设备仍可渲染）。
function portPos(n, dir, portId) {
  const arr = (n.ports && n.ports[dir]) || []
  const i = arr.findIndex((p) => p.id === portId)
  const def = T2D_INOUT[n.type] && T2D_INOUT[n.type][dir]
  const anc = def && def[i]
  if (anc) {
    const fo = figOf(n)
    return {
      x: n.x + fo.x + anc.cx * fo.s,
      y: n.y + fo.y + anc.cy * fo.s,
      side: anc.side,
    }
  }
  return {
    x: dir === 'in' ? n.x + 13 : n.x + boxW(n) - 13,
    y: n.y + portY(n, dir, Math.max(i, 0)),
    side: dir === 'in' ? 'L' : 'R',
  }
}
// 图符绘制区：从名称带(24)到图带底(主工艺留出 KPI、辅助留出底部留白)，等比 contain 居中。
function figOf(n) {
  const W = boxW(n)
  const H = boxH(n)
  const top = 24
  const bot = H - (isMain(n) ? KPI_H + 32 : 14)
  const avW = W - 8
  const avH = Math.max(30, bot - top)
  const s = Math.min(avW / 22, avH / 23.5)
  return { s, x: (W - 22 * s) / 2, y: top + (avH - 23.5 * s) / 2 }
}

function isAux(n) { return !isMain(n) }
function isMain(n) { const t = PROCESS_MAP[n.type]; return !!t && t.route === 'steel' }
function iconOf(t) { return T2D_ICONS[t] || T2D_ICONS.default }

// —— 设备 PNG 图替（可选）：public/2D-image/devices/{设备名}.png 或 {type}.png 存在时，
//    用真实设备图片替代矢量图元（按设备名中文优先、type 兜底）。发现机制：进入视图后对
//    当前节点逐个 HEAD 探测，命中即换图；结果缓存，避免每次重排重复请求。找不到仍画矢量。
const IMG_DIR = '/2D-image/devices/'
const headCache = new Map()          // url -> 可访问（只缓存「命中」，会话级）
const failAt = new Map()             // url -> 上次探测失败时间戳（失败不永久缓存，可重试）
const FAIL_TTL = 5000                // 失败后多久允许重新探测（ms），避免瞬时故障被永久固化
const urlOk = reactive(new Map())    // url -> 探测结果（驱动模板 v-if）
function devImgCands(n) {
  const out = []
  const nm = (n.name || '').trim()
  if (nm) out.push(IMG_DIR + encodeURIComponent(nm) + '.png')
  // 实例名去掉末尾序号（热风炉1 → 热风炉）：多台同类型实例共享「类型图」如 热风炉.png
  const base = nm.replace(/\s*\d+$/, '')
  if (base && base !== nm) out.push(IMG_DIR + encodeURIComponent(base) + '.png')
  // 类型中文名兜底：节点被重命名（如「热风炉1」→「1号炉」）时仍能命中 热风炉.png
  const tl = PROCESS_MAP[n.type] && PROCESS_MAP[n.type].label
  if (tl) out.push(IMG_DIR + encodeURIComponent(tl) + '.png')
  if (n.type) out.push(IMG_DIR + n.type + '.png')
  return out
}
async function probeImgs() {
  const list = new Set()
  for (const n of nodes.value) for (const u of devImgCands(n)) list.add(u)
  for (const u of list) {
    if (headCache.has(u)) { urlOk.set(u, headCache.get(u)); continue }
    // 失败项在 TTL 内跳过（避免每次重排都发请求），超期则再探一次：
    // 覆盖「dev server 重启 / 网络抖动 / 首次探测时图片还没放好」导致的批量失败，无需刷新页面即可自愈。
    if (failAt.has(u) && Date.now() - failAt.get(u) < FAIL_TTL) continue
    let ok = false
    try {
      const res = await fetch(u, { method: 'HEAD' })
      // 不能只看 res.ok：dev server 对不存在的路径会 SPA-fallback 返回 200 text/html
      const ct = (res.headers.get('content-type') || '').toLowerCase()
      ok = res.ok && ct.startsWith('image/')
    } catch { ok = false }
    if (ok) { headCache.set(u, true); failAt.delete(u); urlOk.set(u, true) }
    else { failAt.set(u, Date.now()); urlOk.delete(u) }
  }
}
function devImgOf(n) {
  const nm = (n.name || '').trim()
  if (nm) { const u = IMG_DIR + encodeURIComponent(nm) + '.png'; if (urlOk.get(u)) return u }
  const base = nm.replace(/\s*\d+$/, '')
  if (base && base !== nm) { const u = IMG_DIR + encodeURIComponent(base) + '.png'; if (urlOk.get(u)) return u }
  const tl = PROCESS_MAP[n.type] && PROCESS_MAP[n.type].label
  if (tl) { const u = IMG_DIR + encodeURIComponent(tl) + '.png'; if (urlOk.get(u)) return u }
  if (n.type) { const u = IMG_DIR + n.type + '.png'; if (urlOk.get(u)) return u }
  return null
}
// 设备 PNG 显示盒：铺满节点「名称下方 → KPI/底部上方」的可用图带（等比 contain 居中）；
// 宽向外扩 10%（主设备行间距大，溢出不碰相邻盒），高度方向收在 KPI 之上，主体比原归一框大得多。
function devImgBox(n) {
  const W = boxW(n), H = boxH(n)
  const main = isMain(n)
  const top = 30
  const bot = H - (main ? 40 : 12)
  const aw = (W - 6) * 1.1
  const ah = Math.max(24, bot - top)
  return { x: (W - aw) / 2, y: top, w: aw, h: ah }
}

// 端口外接点：把端口沿 side 方向向外推 STUB，得到 stub 的外端点（折线从此开始/结束）
function stubPoint(p, side) {
  switch (side) {
    case 'L': return { x: p.x - STUB, y: p.y }
    case 'R': return { x: p.x + STUB, y: p.y }
    case 'T': return { x: p.x, y: p.y - STUB }
    case 'B': return { x: p.x, y: p.y + STUB }
    default:  return { x: p.x, y: p.y }
  }
}
function portColor(m) { return (MATERIAL_MAP[m] || {}).color || '#8a97a5' }
function matName(m) { return (MATERIAL_MAP[m] || {}).name || m }

function unitOf(n) {
  const units = store.resultForView && store.resultForView.units ? store.resultForView.units : []
  return units.find((x) => x.id === n.id) || {}
}
function isSel(n) { return store.selectedUnitId === n.id || store.selectedFlowId === n.id }

// —— 管线正交路径(工业流程图) ——
// 出入口口径(用户约束)：设备「左/上/下 = 输入端、右 = 输出端」，T2D_INOUT 已按此落位；
// 路由原则：每条线尽量「少转折、每段笔直」，杜绝网格锯齿(旧 A* 兜底会拉出一串 10px 小台阶，
// 视觉上像“波动”)。做法：
//   1) 先试直连 H-then-V / 纵向主链折返(_foldChain)；
//   2) 若穿第三方设备框，枚举「候选走廊」(直连高度 / 主行顶上方走廊 / 主行底下方车道 /
//      源组/目标组顶底空带) ×「候选竖列」(源口列 / 源组右缘外 / 主带左右外侧 / 目标左右外)，
//      用穿盒检测过滤，取「不穿任何设备框」中路径最短者 → 每段都是长直段；
//   3) 极端兜底走主带顶大走廊，几乎不会进入。
// 共享端口(同口多线)在端口处按 ±k*14 错开，保持束状整齐。
const FWD_TOL = 100
const LINE_STEP = 14
const LANE_STEP = 16
const STUB = 16
const UPPER_GAP = 22
const OBST_PAD = 4

function _grpOf(id) {
  return groups.value.find((g) => g.items && g.items.some((n) => n.id === id))
}
function _dedupe(pts) {
  const o = [pts[0]]
  for (let i = 1; i < pts.length; i++) { const p = pts[i], q = o[o.length - 1]; if (p.x !== q.x || p.y !== q.y) o.push(p) }
  return o
}
function _pathLen(pts) {
  let s = 0
  for (let i = 1; i < pts.length; i++) s += Math.abs(pts[i].x - pts[i - 1].x) + Math.abs(pts[i].y - pts[i - 1].y)
  return s
}
// —— 端点设备避让障碍 ——
function _obstaclesFor(c) {
  const out = []
  for (const n of nodes.value) {
    if (n.id === c.from || n.id === c.to) continue
    const W = boxW(n), H = boxH(n)
    out.push({ x0: n.x - OBST_PAD, y0: n.y - OBST_PAD, x1: n.x + W + OBST_PAD, y1: n.y + H + OBST_PAD })
  }
  return out
}
function _segHitRect(x1, y1, x2, y2, r) {
  if (x1 === x2) {
    if (x1 < r.x0 - 1 || x1 > r.x1 + 1) return false
    const yA = Math.min(y1, y2), yB = Math.max(y1, y2)
    return yB > r.y0 - 1 && yA < r.y1 + 1
  }
  if (y1 === y2) {
    if (y1 < r.y0 - 1 || y1 > r.y1 + 1) return false
    const xA = Math.min(x1, x2), xB = Math.max(x1, x2)
    return xB > r.x0 - 1 && xA < r.x1 + 1
  }
  return false
}
function _hasCross(pts, obs) {
  for (let i = 1; i < pts.length; i++) {
    const x1 = pts[i - 1].x, y1 = pts[i - 1].y, x2 = pts[i].x, y2 = pts[i].y
    for (let k = 0; k < obs.length; k++) {
      if (_segHitRect(x1, y1, x2, y2, obs[k])) return true
    }
  }
  return false
}
// 折线穿过设备数(兜底排序用)
function _crossCount(pts, obs) {
  let n = 0
  for (let i = 1; i < pts.length; i++) {
    const x1 = pts[i - 1].x, y1 = pts[i - 1].y, x2 = pts[i].x, y2 = pts[i].y
    for (let k = 0; k < obs.length; k++) { if (_segHitRect(x1, y1, x2, y2, obs[k])) n++ }
  }
  return n
}
function _lineRoutes() {
  const mainTop = mainBand.value.top, mainBot = mainBand.value.bot
  const list = []
  for (const c of conns.value) {
    const f = nodes.value.find((n) => n.id === c.from)
    const t = nodes.value.find((n) => n.id === c.to)
    if (!f || !t) continue
    const p1 = portPos(f, 'out', c.fromPort)
    const p2 = portPos(t, 'in', c.toPort)
    list.push({ c, p1, p2, f, t })
  }
  // 同源同口 / 同目标同口的多线在端口处错开（保持束状、不叠线）
  const srcSt = {}
  {
    const m = {}
    for (const r of list) { const k = r.c.from + '|' + r.c.fromPort; (m[k] = m[k] || []).push(r) }
    for (const arr of Object.values(m)) arr.forEach((r, i) => {
      if (arr.length > 1) srcSt[r.c.id] = (i - (arr.length - 1) / 2) * LINE_STEP
    })
  }
  const dstOff = {}
  {
    const m = {}
    for (const r of list) { const k = r.c.to + '|' + r.c.toPort; (m[k] = m[k] || []).push(r) }
    for (const arr of Object.values(m)) arr.forEach((r, i) => {
      if (arr.length > 1) dstOff[r.c.id] = (i - (arr.length - 1) / 2) * LINE_STEP
    })
  }
  // —— 共享目标端口的多源「母线汇流」预解析 ——
  // 条件：同 (to,toPort)、源同属一辅助组、源 out 口 y 相同、≥2 条 conn。
  // 几何：支线沿各自槽竖上到「母线带 yBus」(组顶 -16),首尾相接汇入下一源槽；
  // 最后一条（干线）从最右源槽在 yBus 横跨到端口 stub x,再沿 L 槽入端口。
  // 收益：热风炉1/2/3 共用一根热风总管进风口带,避免画面 3 个独立 stub。
  const busData = new Map()
  {
    const m = {}
    for (const r of list) { const k = r.c.to + '|' + r.c.toPort; (m[k] = m[k] || []).push(r) }
    for (const arr of Object.values(m)) {
      if (arr.length < 2) continue
      const y0 = arr[0].p1.y
      if (!arr.every((r) => (r.p1.side || 'R') === 'R' && Math.abs(r.p1.y - y0) < 0.5)) continue
      const grp = _grpOf(arr[0].f.id)
      if (!grp || !arr.every((r) => _grpOf(r.f.id) === grp)) continue
      const yBus = Math.min(...arr.map((r) => r.f.y)) - 16
      const rows = arr.map((r) => ({ r, slot: r.p1.x + STUB })).sort((a, b) => a.slot - b.slot)
      busData.set(arr[0].c.to + '|' + arr[0].c.toPort, { rows, yBus })
      // 母线组端口错开清零（共用单端口,不再 ±14 错开生成多个 stub）
      for (const x of arr) delete dstOff[x.c.id]
    }
  }
  // —— 每条 conn 的确定性折线路径 ——
  const path = new Map()
  for (const r of list) {
    const { c, p1, p2, f, t } = r
    const s1 = p1.side || 'R'
    const s2 = p2.side || 'L'
    const p1a = applyOff(p1, s1, srcSt[c.id])
    const p2a = applyOff(p2, s2, dstOff[c.id])
    const p1s = stubPoint(p1a, s1)
    const p2s = stubPoint(p2a, s2)
    const obs = _obstaclesFor(c)
    let pts = null
    // 0) 共享目标端口的「母线汇流」：支线首尾相接、干线单线入端口
    const busKey = c.to + '|' + c.toPort
    if (busData.has(busKey)) {
      const bus = busData.get(busKey)
      const idx = bus.rows.findIndex((row) => row.r.c.id === c.id)
      if (idx >= 0) {
        if (idx < bus.rows.length - 1) {
          const nextSlot = bus.rows[idx + 1].slot
          const seg = _dedupe([p1a, p1s, { x: p1s.x, y: bus.yBus }, { x: nextSlot, y: bus.yBus }])
          if (seg.length >= 2 && !_hasCross(seg, obs)) pts = seg
        } else {
          // 干线：最右源槽 yBus → 端口 stub x,y
          const seg = _dedupe([p1a, p1s, { x: p1s.x, y: bus.yBus }, { x: p2s.x, y: bus.yBus }, p2s, p2a])
          if (seg.length >= 2 && !_hasCross(seg, obs)) pts = seg
        }
      }
    }
    // 0.5) 回流弧（feedback 虚线）优先走「主带下缘走廊」
    //   回供线在工艺上是下游→上游（图中多为从右往左），若按常规最短路径会绕到画面最上方
    //   横穿整幅图（跨越所有设备顶部，视觉上很突兀）。这里先试主带下方三条车道，
    //   取不穿任何设备框的最短者；全部受阻才退回常规候选枚举。
    if (!pts && c.feedback) {
      const under = []
      for (let k = 0; k < 3; k++) {
        const cy = mainBot -24 + k * LANE_STEP
        const seg = _dedupe([p1a, p1s, { x: p1s.x, y: cy }, { x: p2s.x, y: cy }, p2s, p2a])
        if (seg.length >= 2 && !_hasCross(seg, obs)) under.push(seg)
      }
      if (under.length) pts = under.sort((a, b) => _pathLen(a) - _pathLen(b))[0]
    }
    // 1) 主工艺纵向折返链（LF 后 RH/连铸/热轧 逐台向下）→ 两带间确定性折线
    if (isMain(f) && isMain(t) && Math.abs(p1a.y - p2a.y) > 140) {
      const fp = _foldChain(p1a, s1, p2a, s2, f, t)
      if (fp && fp.length >= 2 && !_hasCross(fp, obs)) pts = fp
    }
    if (!pts) {
      // 2) 直连 H-then-V（同带短连 / 栈组垂直对齐时的近直线）
      const flat = _dedupe([p1a, p1s, { x: p2s.x, y: p1s.y }, p2s, p2a])
      if (flat.length >= 2 && !_hasCross(flat, obs)) pts = flat
    }
    if (!pts) {
      // 3) 候选走廊枚举：横移带 cy × 竖列 bx 的网格组合，取不穿盒的最短折线
      const srcGrp = _grpOf(f.id)
      const tgtGrp = _grpOf(t.id)
      const cySet = new Set([
        p1s.y, p2s.y,
        mainTop - UPPER_GAP,
        mainTop - UPPER_GAP - LINE_STEP,
        mainTop - UPPER_GAP - LINE_STEP * 2,
        mainBot + 24,
        mainBot + 24 + LANE_STEP,
        mainBot + 24 + LANE_STEP * 2,
      ])
      if (srcGrp) { cySet.add(srcGrp.y - 16); cySet.add(srcGrp.y + srcGrp.h + 16) }
      if (tgtGrp) { cySet.add(tgtGrp.y - 16); cySet.add(tgtGrp.y + tgtGrp.h + 16) }
      const bxSet = new Set([
        p1s.x,
        f.x + boxW(f) + 16,
        srcGrp ? srcGrp.x + srcGrp.w + 12 : f.x + boxW(f) + 16,
        mainBand.value.r + 14,
        mainBand.value.l - 14,
        t.x - 14,
        t.x + boxW(t) + 14,
      ])
      if (tgtGrp) { bxSet.add(tgtGrp.x - 14); bxSet.add(tgtGrp.x + tgtGrp.w + 14) }
      const cand = []
      for (const bx of bxSet) {
        for (const cy of cySet) {
          const seg = _dedupe([p1a, p1s, { x: bx, y: p1s.y }, { x: bx, y: cy }, { x: p2s.x, y: cy }, p2s, p2a])
          if (seg.length >= 2 && !_hasCross(seg, obs)) cand.push(seg)
        }
      }
      // 4) 兜底：主带顶大走廊（多通道错开），仍无则取穿盒最少者
      if (!cand.length) {
        for (let k = 0; k < 6; k++) {
          const cy = mainTop - 24 - k * LINE_STEP
          const seg = _dedupe([p1a, p1s, { x: p1s.x, y: p1s.y }, { x: p1s.x, y: cy }, { x: p2s.x, y: cy }, p2s, p2a])
          if (seg.length >= 2 && !_hasCross(seg, obs)) { cand.push(seg); break }
        }
      }
      if (!cand.length) {
        const outer = [
          _dedupe([p1a, p1s, { x: mainBand.value.r + 20, y: p1s.y }, { x: mainBand.value.r + 20, y: mainTop - 24 }, { x: p2s.x, y: mainTop - 24 }, p2s, p2a]),
          _dedupe([p1a, p1s, { x: mainBand.value.r + 20, y: p1s.y }, { x: mainBand.value.r + 20, y: mainBot + 24 }, { x: p2s.x, y: mainBot + 24 }, p2s, p2a]),
        ]
        pts = outer.sort((a, b) => _crossCount(a, obs) - _crossCount(b, obs) || _pathLen(a) - _pathLen(b))[0]
      } else {
        pts = cand.sort((a, b) => _pathLen(a) - _pathLen(b))[0]
      }
    }
    path.set(c.id, pts)
  }
  return { list, srcSt, dstOff, path }
}
function applyOff(p, side, off) {
  if (!off) return p
  if (side === 'L' || side === 'R') return { x: p.x, y: p.y + off, side: p.side }
  if (side === 'T' || side === 'B') return { x: p.x + off, y: p.y, side: p.side }
  return p
}
// —— 主工艺纵向链折返连线（LF 折返后 RH→连铸→热轧 逐台向下的链式连接） ——
// 两端盒不在同一横向主带时（纵向距离 >140），钢流线从端口伸出后在「两带之间的空档」横向转移，
// 再直落/直入目标口，形成 4~7 段的干净折线。端口 side 组合为当前主链实际出现的三类：
// LF.out(R)→RH.in(L)、RH.out(R)→caster.in(T)、caster.out(R)→rolling.in(L)。
function _foldChain(p1a, s1, p2a, s2, f, t) {
  const p1s = stubPoint(p1a, s1)
  const p2s = stubPoint(p2a, s2)
  if (f.y > t.y) return null // 只处理上→下的链式流
  const ex = f.x + boxW(f) + 10 // 出盒右侧通道
  if (s1 === 'R' && (s2 === 'L' || s2 === 'T')) {
    const band = t.y - 46 // 目标盒上方的空档
    return [p1a, p1s, { x: ex, y: p1s.y }, { x: ex, y: band }, { x: p2s.x, y: band }, p2s, p2a]
  }
  if (s1 === 'B' && s2 === 'L') {
    return [p1a, p1s, { x: p2s.x, y: p1s.y }, p2s, p2a]
  }
  return null
}

function lineOf(c, routes) {
  const pts = routes.path.get(c.id)
  if (!pts || pts.length < 2) return null
  const r = routes.list.find((x) => x.c.id === c.id)
  const p1 = r ? r.p1 : pts[0]
  const p2 = r ? r.p2 : pts[pts.length - 1]
  const d = pts.map((p, i) => (i ? `L ${p.x} ${p.y}` : `M ${p.x} ${p.y}`)).join(' ')
  // 标签置于最长水平段中点（上移 4px 防压线）
  let mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2, best = -1
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].y === pts[i - 1].y) {
      const len = Math.abs(pts[i].x - pts[i - 1].x)
      if (len > best) { best = len; mx = (pts[i].x + pts[i - 1].x) / 2; my = pts[i].y }
    }
  }
  return { d, mx, my: my - 4, p1: pts[0], p2: pts[pts.length - 1], pts }
}
const lines = computed(() => {
  // 2D 工艺流程图定位：管线只沿折线中点标「物料名」小标签，不再挂数据卡数值。
  const routes = _lineRoutes()
  const out = []
  for (const c of conns.value) {
    const g = lineOf(c, routes)
    if (!g) continue
    out.push({
      id: c.id, d: g.d, mx: g.mx, my: g.my,
      sw: c.feedback ? 1.6 : 2.6,
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

function fitAll() {
  if (!svg.value || !nodes.value.length) { zoom.value = 1; pan.value = { x: 0, y: 0 }; return }
  const rect = svg.value.getBoundingClientRect()
  // 矩形化：zoom 同时受整体 bounds 宽高约束（取 min），让矩形画布完整适配视口；
  // 兜底下调到 0.28，避免矩形化后宽高变大被人为压缩。
  const bw = bounds.value.w, bh = bounds.value.h
  const z = Math.min((rect.width * 0.92) / bw, (rect.height * 0.92) / bh)
  zoom.value = Math.max(0.28, Math.min(1.1, z))
  // 让矩形画布在视口居中：屏中心 = pan + 世界中心 × z → pan = 屏中心 - 世界中心 × z
  const centerX = bounds.value.x + bw / 2
  const centerY = bounds.value.y + bh / 2
  pan.value = {
    x: rect.width / 2 - centerX * z,
    y: rect.height / 2 - centerY * z,
  }
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

function fmt(n) {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
const totals = computed(() => (store.resultForView && store.resultForView.totals) || {})

let ro = null
let _prevLeftOpen = null
onMounted(() => {
  // 2D 工艺流程图进入时收起左侧栏（资源/编排树），让 SVG 容器撑大、主设备屏幕占比↑；
  // 退出时恢复原状态，不影响其他视图。
  _prevLeftOpen = store.leftOpen
  store.leftOpen = false
  relayout()
  ro = new ResizeObserver(() => fitAll())
  if (wrap.value) ro.observe(wrap.value)
})
onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  if (_prevLeftOpen !== null) store.leftOpen = _prevLeftOpen
})
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
  padding: 8px 16px 8px 54px;
  background: #fff;
  border-bottom: 1px solid #dde3ea;
  box-shadow: 0 1px 3px rgba(20, 40, 60, 0.06);
  z-index: 2;
}
.t2d-kpi.fs { padding-right: 96px; }
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
/* 辅助系统分组虚线框 */
.t2d-grp { pointer-events: none; }
.t2d-grp-frame {
  fill: rgba(226, 234, 242, 0.45);
  stroke: #9fb2c4; stroke-width: 1.3; stroke-dasharray: 7 5;
}
.t2d-grp-dot { fill: #8a97a5; }
.t2d-grp-title { font-size: 12px; font-weight: 600; fill: #44566a; }
.t2d-grp-n { font-size: 10px; fill: #98a5b2; }
/* 组中组二级虚线框 */
.t2d-subgrp { pointer-events: none; }
.t2d-subgrp-frame {
  fill: rgba(246, 250, 253, 0.6);
  stroke: #b9c6d4; stroke-width: 1; stroke-dasharray: 4 4;
}
.t2d-subgrp-title { font-size: 11px; font-weight: 600; fill: #5a6b7d; }
.t2d-subgrp-n { font-size: 9px; fill: #a2afbc; }
/* 管线 */
.t2d-link { opacity: 0.92; pointer-events: none; }
.t2d-mid { pointer-events: none; }
.t2d-mat {
  font-size: 10px; fill: #6b7785; letter-spacing: 0.02em;
  pointer-events: none;
  paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round;
}

/* —— 设备节点 —— */
.t2d-node { cursor: pointer; }
.t2d-node .t2d-fig { transition: filter 0.15s; }
.t2d-node:hover .t2d-fig { filter: drop-shadow(0 2px 6px rgba(44, 110, 158, 0.35)); }
.t2d-node.on .t2d-fig { filter: drop-shadow(0 0 8px rgba(196, 127, 23, 0.45)); }
/* 名称浮签 */
.t2d-name {
  font-size: 12px; font-weight: 700; fill: #2b4a6e; letter-spacing: 0.02em;
  paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round;
}
.t2d-node.aux .t2d-name { fill: #5a6a78; font-weight: 600; }
.t2d-node.on .t2d-name { fill: #c47f17; }
/* 主工艺底部悬浮实时 KPI */
.t2d-kpis {
  font-size: 10px; font-family: -apple-system, "Consolas", monospace;
  paint-order: stroke; stroke: rgba(242, 244, 246, 0.9); stroke-width: 3px; stroke-linejoin: round;
}
.t2d-kpi-c { fill: #9a4d33; font-weight: 700; }
.t2d-kpi-e { fill: #33475b; }
.t2d-kpi-sep { fill: #8a97a5; }
.t2d-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #8a97a5; font-size: 14px; background: #f2f4f6;
}
</style>