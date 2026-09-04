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
import { T2D_ICONS, T2D_GEOM, T2D_INOUT } from './twin2dIcons'

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
  // MAIN_GAP：主行间距。主工艺盒整体放大后同步收窄间距，使「主行总宽」基本不变——
  // fitAll 的 zoom 只按主行总宽计算，总宽稳住 → zoom 恒定 → 辅助设备在屏幕上的大小不受影响。
  const MAIN_GAP = 89
  const FOLD_GAP = 116 // 横向主带与折返纵向链之间 / 纵向链层间的净空（留折返横带）
  // 折返：LF(LF 精炼)之后的工序不再继续向右横排成一条直线，而是沿 LF 中心列逐台向下排成
  // 「纵向链」（RH → 连铸 → 热轧），像产线总图一样竖着走下去。主行总宽从 ~3971 压到
  // 横向主带的宽度 → fitAll 的 zoom 随之变大 → 主工艺设备整体更大（这正是放大诉求的另一半）。
  const FOLD_TYPE = 'ladle_furnace'
  const foldI = mainNodes.findIndex((n) => n.type === FOLD_TYPE)
  const rowA = foldI >= 0 ? mainNodes.slice(0, foldI + 1) : mainNodes
  const colB = foldI >= 0 ? mainNodes.slice(foldI + 1) : []
  let x = 80, y = 100
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
  // 按锚 x 升序排；同锚 x 内保留 AUX_SYS_DEF 原声明顺序（稳定排序）
  auxGroups.forEach((g) => { g.anchorX = anchorX(g); g._order = AUX_SYS_DEF.findIndex((d) => d.key === g.key) })
  auxGroups.sort((a, b) => a.anchorX - b.anchorX || a._order - b._order)

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
  // 组外流式排布：每组首选 gx = clamp(锚x - g.w/2, auxX0, auxX0+auxMaxW - g.w)；
  // 若首选位置与当前行已用区间重叠 → 整组换到下一行（gy += lineH + GRP_GAP_Y）后再按锚 x 放。
  // 目标是让每个辅助组贴近其服务的「主设备列」下方，主↔辅连线退化为短竖直 / 单一折点。
  const auxX0 = 80
  const auxY0 = mainBottom != null ? mainBottom + 96 : 100
  const auxMaxW = Math.max(mainW, 900)
  let gy = auxY0, lineH = 0, lineEnd = auxX0
  for (const g of auxGroups) {
    // 占位：用当前行首算出 g.w/g.h（设备 x / 子框 x 会被下面的二次 placeGroup 覆盖）
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
  // 展平二级子框（多类型组才有），模板据此画「组中组」虚线框
  const sf = []
  for (const g of auxGroups) for (const s of g.subs || []) sf.push({ kid: `${g.key}--${s.type}`, label: s.label, count: s.count, x: s.x, y: s.y, w: s.w, h: s.h })
  subFrames.value = sf

  // 计算包围盒（主卡 ∪ 辅助组框），保证「适配」后全部框与连线可见
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  const addBox = (bx, by, bw, bh) => {
    x0 = Math.min(x0, bx); y0 = Math.min(y0, by)
    x1 = Math.max(x1, bx + bw); y1 = Math.max(y1, by + bh)
  }
  for (const n of mainNodes) addBox(n.x, n.y, boxW(n), boxH(n))
  for (const g of auxGroups) addBox(g.x, g.y, g.w, g.h)
  if (x0 === Infinity) { x0 = 0; y0 = 0; x1 = 1200; y1 = 700 }
  // 逆向连线数（估算返回通道占用高度）
  let bwdN = 0
  for (const c of cs) {
    const f = ns.find((n) => n.id === c.from)
    const t = ns.find((n) => n.id === c.to)
    if (!f || !t) continue
    if ((f.x + boxW(f) - 13) - (t.x + 13) > FWD_TOL) bwdN++
  }
  const frameBottom = auxGroups.length ? Math.max(...auxGroups.map((g) => g.y + g.h)) : 0
  const floor = frameBottom + 26 + bwdN * LANE_STEP + 20
  const pad = PAD
  const left = Math.min(x0, 24)   // 返回通道目标竖段向左错开最远可到 x≈25
  bounds.value = { x: left - pad, y: y0 - pad, w: x1 - left + pad * 2, h: Math.max(y1, floor) - y0 + pad * 2 }
  nodes.value = ns
  groups.value = auxGroups
  conns.value = cs
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
  const h = Math.max(g.h, 96 + (cnt - 1) * 24)
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
const headCache = new Map()          // url -> 是否可访问（会话级缓存）
const urlOk = reactive(new Map())    // url -> 探测结果（驱动模板 v-if）
function devImgCands(n) {
  const out = []
  const nm = (n.name || '').trim()
  if (nm) out.push(IMG_DIR + encodeURIComponent(nm) + '.png')
  // 实例名去掉末尾序号（热风炉1 → 热风炉）：多台同类型实例共享「类型图」如 热风炉.png
  const base = nm.replace(/\s*\d+$/, '')
  if (base && base !== nm) out.push(IMG_DIR + encodeURIComponent(base) + '.png')
  if (n.type) out.push(IMG_DIR + n.type + '.png')
  return out
}
async function probeImgs() {
  const list = new Set()
  for (const n of nodes.value) for (const u of devImgCands(n)) list.add(u)
  for (const u of list) {
    if (headCache.has(u)) { urlOk.set(u, headCache.get(u)); continue }
    let ok = false
    try {
      const res = await fetch(u, { method: 'HEAD' })
      // 不能只看 res.ok：dev server 对不存在的路径会 SPA-fallback 返回 200 text/html
      const ct = (res.headers.get('content-type') || '').toLowerCase()
      ok = res.ok && ct.startsWith('image/')
    } catch { ok = false }
    headCache.set(u, ok)
    urlOk.set(u, ok)
  }
}
function devImgOf(n) {
  const nm = (n.name || '').trim()
  if (nm) { const u = IMG_DIR + encodeURIComponent(nm) + '.png'; if (urlOk.get(u)) return u }
  const base = nm.replace(/\s*\d+$/, '')
  if (base && base !== nm) { const u = IMG_DIR + encodeURIComponent(base) + '.png'; if (urlOk.get(u)) return u }
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

// —— 管线正交路径（工业流程图：先水平、后垂直、再水平）——
// 并行展开策略：
//   1. 目标端口共享 → 各自沿 yL = 端口y ± k*14 错开进入；
//   2. 源竖段同列多线 → 源端水平伸出段按 k*14 向右错开再转折；
//   3. 逆向连线 → 走内容区下方「返回通道」，每条独占一条 16px 车道；
//   4. 目标在 T（炉顶装料等）→ 抬到「主行顶上方 UPPER_GAP」的走廊绕开主行；
//   5. 折线穿过第三方设备框 → A* 网格兜底绕行（仅必要时）。
const FWD_TOL = 100
const LINE_STEP = 14
const LANE_STEP = 16
const STUB = 16
const UPPER_GAP = 28
const OBST_PAD = 4
const CELL = 10
const ROUTE_PAD = 32

function _contentBottom() {
  return nodes.value.length ? Math.max(...nodes.value.map((n) => n.y + boxH(n))) : 0
}
function _grpBottom() {
  return groups.value.length ? Math.max(...groups.value.map((g) => g.y + g.h)) : 0
}
function _lineRoutes() {
  const list = []
  for (const c of conns.value) {
    const f = nodes.value.find((n) => n.id === c.from)
    const t = nodes.value.find((n) => n.id === c.to)
    if (!f || !t) continue
    const p1 = portPos(f, 'out', c.fromPort)
    const p2 = portPos(t, 'in', c.toPort)
    list.push({ c, p1, p2, f, t })
  }
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
  const bwd = list.filter((r) => r.p1.x - r.p2.x > FWD_TOL)
  const chBase = Math.max(_contentBottom(), _grpBottom()) + 24
  const bwdLane = {}
  bwd.forEach((r, i) => { bwdLane[r.c.id] = chBase + i * LANE_STEP })
  return { list, srcSt, dstOff, bwdLane }
}
function applyOff(p, side, off) {
  if (!off) return p
  if (side === 'L' || side === 'R') return { x: p.x, y: p.y + off, side: p.side }
  if (side === 'T' || side === 'B') return { x: p.x + off, y: p.y, side: p.side }
  return p
}
// —— 末端撞设备避让（A* 兜底） ——
// 折线段落在原路由（共享端口错位 / 上方走廊 / 底部返回车道 / 通用 H-V）中如有穿过「非端点设备」框者，
// 改走网格 A* 绕开。仅在必要时生效，不影响默认美观。
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
function _routeBounds(p1, p2, obs) {
  let x0 = Math.min(p1.x, p2.x), y0 = Math.min(p1.y, p2.y), x1 = Math.max(p1.x, p2.x), y1 = Math.max(p1.y, p2.y)
  for (let i = 0; i < obs.length; i++) { const r = obs[i]; x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1) }
  return { x0: x0 - ROUTE_PAD, y0: y0 - ROUTE_PAD, x1: x1 + ROUTE_PAD, y1: y1 + ROUTE_PAD }
}
class _MinHeap {
  constructor() { this.a = [] }
  push(x) {
    this.a.push(x); let i = this.a.length - 1
    while (i > 0) { const p = (i - 1) >> 1; if (this.a[p].f <= this.a[i].f) break; const t = this.a[p]; this.a[p] = this.a[i]; this.a[i] = t; i = p }
  }
  pop() {
    if (this.a.length === 0) return null
    const top = this.a[0]; const last = this.a.pop()
    if (this.a.length) {
      this.a[0] = last; let i = 0; const n = this.a.length
      for (;;) {
        const l = i * 2 + 1, r = i * 2 + 2; let m = i
        if (l < n && this.a[l].f < this.a[m].f) m = l
        if (r < n && this.a[r].f < this.a[m].f) m = r
        if (m === i) break
        const t = this.a[m]; this.a[m] = this.a[i]; this.a[i] = t; i = m
      }
    }
    return top
  }
  get size() { return this.a.length }
}
// 网格 A*：返回 [start, ..., end] 折线（含起点终点）；失败返回 null。
function _astarRoute(start, end, obs, br) {
  const x0 = Math.floor(br.x0 / CELL) * CELL
  const y0 = Math.floor(br.y0 / CELL) * CELL
  const x1 = Math.ceil(br.x1 / CELL) * CELL
  const y1 = Math.ceil(br.y1 / CELL) * CELL
  const w = Math.max(2, Math.round((x1 - x0) / CELL))
  const h = Math.max(2, Math.round((y1 - y0) / CELL))
  const N = w * h
  const cellX = (cx) => x0 + cx * CELL + CELL / 2
  const cellY = (cy) => y0 + cy * CELL + CELL / 2
  const idx = (cx, cy) => cy * w + cx
  let sCx = Math.round((start.x - x0) / CELL), sCy = Math.round((start.y - y0) / CELL)
  let eCx = Math.round((end.x - x0) / CELL), eCy = Math.round((end.y - y0) / CELL)
  sCx = Math.min(w - 1, Math.max(0, sCx)); sCy = Math.min(h - 1, Math.max(0, sCy))
  eCx = Math.min(w - 1, Math.max(0, eCx)); eCy = Math.min(h - 1, Math.max(0, eCy))
  const sIdx = idx(sCx, sCy), eIdx = idx(eCx, eCy)
  const g = new Float32Array(N); g.fill(Infinity)
  const came = new Int32Array(N); for (let i = 0; i < N; i++) came[i] = -1
  const closed = new Uint8Array(N)
  g[sIdx] = 0
  const heap = new _MinHeap()
  const heur = (ax, ay, bx, by) => Math.abs(ax - bx) + Math.abs(ay - by)
  heap.push({ cx: sCx, cy: sCy, f: heur(sCx, sCy, eCx, eCy) })
  const dx = [0, 0, 1, -1], dy = [1, -1, 0, 0]
  while (heap.size) {
    const cur = heap.pop()
    const cIdx = idx(cur.cx, cur.cy)
    if (closed[cIdx]) continue
    if (cur.cx === eCx && cur.cy === eCy) {
      const cells = []
      let i = cIdx
      while (i !== -1) { cells.push(i); i = came[i] }
      cells.reverse()
      const out = []
      for (let k = 0; k < cells.length; k++) { const cx = cells[k] % w, cy = Math.floor(cells[k] / w); out.push({ x: cellX(cx), y: cellY(cy) }) }
      if (out.length) { out[0] = start; out[out.length - 1] = end }
      const clean = [out[0]]
      for (let k = 1; k < out.length; k++) { const p = out[k]; const q = clean[clean.length - 1]; if (p.x !== q.x || p.y !== q.y) clean.push(p) }
      if (clean.length >= 2) {
        const a = clean[0], b = clean[1]
        if (a.x !== b.x && a.y !== b.y) clean.splice(1, 0, { x: b.x, y: a.y })
      }
      if (clean.length >= 2) {
        const z = clean[clean.length - 2], e = clean[clean.length - 1]
        if (z.x !== e.x && z.y !== e.y) clean.splice(clean.length - 1, 0, { x: z.x, y: e.y })
      }
      return clean
    }
    closed[cIdx] = 1
    const ax = cellX(cur.cx), ay = cellY(cur.cy)
    for (let d = 0; d < 4; d++) {
      const nx = cur.cx + dx[d], ny = cur.cy + dy[d]
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue
      const nIdx = idx(nx, ny)
      if (closed[nIdx]) continue
      const bx = cellX(nx), by = cellY(ny)
      let blocked = false
      for (let k = 0; k < obs.length; k++) {
        if (_segHitRect(ax, ay, bx, by, obs[k])) { blocked = true; break }
      }
      if (blocked) continue
      const ng = g[cIdx] + 1
      if (ng < g[nIdx]) {
        g[nIdx] = ng
        came[nIdx] = cIdx
        heap.push({ cx: nx, cy: ny, f: ng + heur(nx, ny, eCx, eCy) })
      }
    }
  }
  return null
}

// —— 主工艺纵向链折返连线（LF 折返后 RH→连铸→热轧 逐台向下的链式连接） ——
// 两端盒不在同一横向主带时（纵向距离 >140），钢流线从端口伸出后在「两带之间的空档」横向转移，
// 再直落/直入目标口，形成 4~7 段的干净折线，既不会被 FWD_TOL 误判逆向走底部车道，
// 也不会穿第三方设备（末端仍交给 lineOf 的 _hasCross → A* 兜底）。
// 端口 side 组合为当前主链数据实际出现的三类：LF.out(R)→RH.in(L)、RH.out(R)→caster.in(T)、
// caster.out(B)→rolling.in(L)；未覆盖组合返回 null，由旧逻辑处理。
function _foldChain(p1a, s1, p2a, s2, f, t) {
  const p1s = stubPoint(p1a, s1)
  const p2s = stubPoint(p2a, s2)
  if (f.y > t.y) return null // 只处理上→下的链式流
  const ex = f.x + boxW(f) + 10 // 出盒右侧通道
  if (s1 === 'R' && s2 === 'L') {
    const band = t.y - 46 // 目标盒上方的空档
    return [p1a, p1s, { x: ex, y: p1s.y }, { x: ex, y: band }, { x: p2s.x, y: band }, p2s, p2a]
  }
  if (s1 === 'R' && s2 === 'T') {
    const band = t.y - 46
    return [p1a, p1s, { x: ex, y: p1s.y }, { x: ex, y: band }, { x: p2s.x, y: band }, p2s, p2a]
  }
  if (s1 === 'B' && s2 === 'L') {
    return [p1a, p1s, { x: p2s.x, y: p1s.y }, p2s, p2a]
  }
  return null
}

function lineOf(c, routes) {
  const r = routes.list.find((x) => x.c.id === c.id)
  if (!r) return null
  const { p1, p2 } = r
  const s1 = p1.side || 'R'
  const s2 = p2.side || 'L'
  const p1a = applyOff(p1, s1, routes.srcSt[c.id])
  const p2a = applyOff(p2, s2, routes.dstOff[c.id])
  const p1s = stubPoint(p1a, s1)
  const p2s = stubPoint(p2a, s2)
  const bwd = p1.x - p2.x > FWD_TOL

  // 主工艺纵向链（LF 折返后逐台向下的 RH/连铸/热轧）连线：两端都在主工艺、纵向距离 >140
  // → 用 _foldChain 在两带之间的空档走确定性折线（不判逆向、不走上廊）。
  const vertChain = isMain(r.f) && isMain(r.t) && Math.abs(p1a.y - p2a.y) > 140
  let pts = vertChain ? _foldChain(p1a, s1, p2a, s2, r.f, r.t) : null
  if (!pts) {
  if (bwd) {
    // 逆向：底部返回车道
    const lane = routes.bwdLane[c.id]
    pts = [p1, p1s]
    if (p1s.y !== lane) pts.push({ x: p1s.x, y: lane })
    if (p1s.x !== p2s.x) pts.push({ x: p2s.x, y: lane })
    if (p2s.y !== lane) pts.push({ x: p2s.x, y: p2s.y })
    pts.push(p2s, p2a)
  } else {
    // 正向：源在主行下方、目标在主行内（含主行底缘附近）→ 改走主行顶上方走廊
    //   这样默认就不会「上穿主行」触发 A*（热风炉→高炉侧口、供氧→主工艺设备都受益）。
    //   原 T 口特判保留（哪怕源在主行内，仍走顶部走廊更整齐）。
    const mainTop = mainBand.value.top
    const mainBot = mainBand.value.bot
    const needUpper = (p1a.y > mainBot + 4) && (p2a.y < mainBot + 4)
      || (s2 === 'T' && p1a.y > p2s.y + 4)
    if (needUpper) {
      const cy = mainTop - UPPER_GAP
      pts = [p1, p1s]
      // 若源竖段 x 落在「源设备所属组」的横向范围里,直接抬到 y=cy 会穿过同组兄弟设备
      // （如供氧 5 台同列 → 源 x 落在氧1/氧3 等盒子内）。改为：先抬到组顶上方,水平跳到组边
      // 缘 (escapeX),再上到顶部走廊。escapeX 永远在组外,主干线 5 段以下、无需 A* 兜底。
      const srcGroup = groups.value.find((g) => g.items && g.items.some((n) => n.id === r.f.id))
      const insideSrc = srcGroup && p1s.x >= srcGroup.x - 2 && p1s.x <= srcGroup.x + srcGroup.w + 2
      if (insideSrc) {
        // 逃出源组后,沿「主行带外侧」走（l-12 / r+12）—— 这两条竖线永远在所有主设备之外
        // ，主干线就是 7~8 段、无需 A* 兜底。多目标群（如全厂供氧 5 台对 5 个主设备）会共享
        // 同一侧「总线」，形成梯状整齐布局。
        const escapeX = (p1s.x - (mainBand.value.l - 12))
          < ((mainBand.value.r + 12) - p1s.x)
          ? mainBand.value.l - 12 : mainBand.value.r + 12
        const hopY = srcGroup.y - 14
        if (p1s.y !== hopY) pts.push({ x: p1s.x, y: hopY })
        if (p1s.x !== escapeX) pts.push({ x: escapeX, y: hopY })
        if (hopY !== cy) pts.push({ x: escapeX, y: cy })
        if (escapeX !== p2s.x) pts.push({ x: p2s.x, y: cy })
      } else {
        if (p1s.y !== cy) pts.push({ x: p1s.x, y: cy })
        if (p1s.x !== p2s.x) pts.push({ x: p2s.x, y: cy })
      }
      if (p2s.y !== cy) pts.push({ x: p2s.x, y: p2s.y })
      pts.push(p2s, p2a)
    } else {
      // 通用 H-then-V
      pts = [p1, p1s]
      if (p1s.x !== p2s.x) pts.push({ x: p2s.x, y: p1s.y })
      if (p1s.y !== p2s.y) pts.push(p2s)
      pts.push(p2a)
    }
  }
  }
  // 去掉完全重合的相邻点（折线无意义重复）
  const clean = [pts[0]]
  for (let i = 1; i < pts.length; i++) {
    const p = pts[i]
    if (p.x !== clean[clean.length - 1].x || p.y !== clean[clean.length - 1].y) clean.push(p)
  }
  pts = clean
  // —— 末端撞设备避让：折线若穿过「非端点设备」框 → 改走 A* 避让路径 ——
  const obs = _obstaclesFor(c)
  if (_hasCross(pts, obs)) {
    const br = _routeBounds(p1s, p2s, obs)
    const alt = _astarRoute(p1s, p2s, obs, br)
    if (alt && alt.length >= 2) {
      const merged = [p1, p1s].concat(alt.slice(1, alt.length - 1)).concat([p2s, p2a])
      const cc = [merged[0]]
      for (let i = 1; i < merged.length; i++) { const pp = merged[i]; if (pp.x !== cc[cc.length - 1].x || pp.y !== cc[cc.length - 1].y) cc.push(pp) }
      pts = cc
    }
  }
  const d = pts.map((p, i) => (i ? `L ${p.x} ${p.y}` : `M ${p.x} ${p.y}`)).join(' ')
  // 标签置于最长水平段中点（上移 4px 防压线）
  let mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2, best = -1
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].y === pts[i - 1].y) {
      const len = Math.abs(pts[i].x - pts[i - 1].x)
      if (len > best) { best = len; mx = (pts[i].x + pts[i - 1].x) / 2; my = pts[i].y }
    }
  }
  return { d, mx, my: my - 4, p1: p1a, p2: p2a, pts }
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
  const mainNodes = nodes.value.filter((n) => isMain(n))
  const mainW = mainNodes.length
    ? Math.max(...mainNodes.map((n) => n.x + boxW(n))) - Math.min(...mainNodes.map((n) => n.x)) + 40
    : bounds.value.w
  zoom.value = Math.max(0.38, Math.min(1.1, (rect.width * 0.88) / mainW))
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