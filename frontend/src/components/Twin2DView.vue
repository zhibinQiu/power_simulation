<template>
  <div class="twin2d">
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
          <!-- 管线流向改为「沿线运动的箭头」（见下方 animateMotion），不再使用末端静态 marker -->
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

          <!-- ===== 程序化设备图形的伪 3D 材质（供 data/twin2dFigures.js 使用） =====
               横向渐变模拟圆柱受光（光源左上：左暗→中偏左最亮→右暗），
               任何竖直筒体一填就有体积感；热态版本用于炉缸/转炉等高温部位。 -->
          <linearGradient id="g-cyl" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#5d6b79"/><stop offset="0.34" stop-color="#dfe6ed"/>
            <stop offset="0.6" stop-color="#aab6c2"/><stop offset="1" stop-color="#4e5b68"/>
          </linearGradient>
          <linearGradient id="g-cyl-hot" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#6e2c10"/><stop offset="0.34" stop-color="#ffb04a"/>
            <stop offset="0.62" stop-color="#d2601c"/><stop offset="1" stop-color="#5f2510"/>
          </linearGradient>
          <!-- 顶面/封头：比侧壁亮一档，与侧壁形成明暗交替 -->
          <linearGradient id="g-top" x1="0" y1="0" x2="0.9" y2="1">
            <stop offset="0" stop-color="#f4f8fb"/><stop offset="1" stop-color="#96a3b1"/>
          </linearGradient>
          <!-- 箱体/炉墙：左上亮、右下暗 -->
          <linearGradient id="g-box" x1="0" y1="0" x2="0.3" y2="1">
            <stop offset="0" stop-color="#dae2ea"/><stop offset="1" stop-color="#78868f"/>
          </linearGradient>
          <linearGradient id="g-box-hot" x1="0" y1="0" x2="0.3" y2="1">
            <stop offset="0" stop-color="#e8b07a"/><stop offset="1" stop-color="#8d4320"/>
          </linearGradient>
          <!-- 钢液/铁水：自上而下由亮黄过渡到暗红 -->
          <linearGradient id="g-molten" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#ffd98a"/><stop offset="0.45" stop-color="#ff9d3c"/>
            <stop offset="1" stop-color="#a83208"/>
          </linearGradient>
          <!-- 炉膛/弧光热核（径向） -->
          <radialGradient id="g-hearth" cx="0.5" cy="0.42" r="0.62">
            <stop offset="0" stop-color="#fff6c9"/><stop offset="0.45" stop-color="#ffab3d"/>
            <stop offset="1" stop-color="#a83208"/>
          </radialGradient>
          <!-- 轧辊/托辊：径向金属 + 偏心亮心 -->
          <radialGradient id="g-roll" cx="0.38" cy="0.34" r="0.72">
            <stop offset="0" stop-color="#eef3f8"/><stop offset="0.55" stop-color="#a9b5c2"/>
            <stop offset="1" stop-color="#55626f"/>
          </radialGradient>
          <!-- 主体投影：伪 3D 的主要来源之一（设备从背景上「浮」起来） -->
          <filter id="f-fig" x="-35%" y="-35%" width="180%" height="190%">
            <feDropShadow dx="0.3" dy="0.5" stdDeviation="0.45" flood-color="#0d1b2a" flood-opacity="0.45"/>
          </filter>
          <!-- 接地柔影 / 烟气：用**径向渐变**而非 feGaussianBlur。
               渐变是纯填充、零滤镜开销；模糊滤镜会在每帧动画（管线流向箭头）触发重新栅格化，
               是 2D 视图掉帧的主因之一，视觉上两者几乎没有差别。 -->
          <radialGradient id="g-ground" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stop-color="#0b1a2b" stop-opacity="0.85"/>
            <stop offset="0.55" stop-color="#0b1a2b" stop-opacity="0.45"/>
            <stop offset="1" stop-color="#0b1a2b" stop-opacity="0"/>
          </radialGradient>
          <radialGradient id="g-puff" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stop-color="#eef4fa" stop-opacity="0.95"/>
            <stop offset="0.6" stop-color="#e8eef4" stop-opacity="0.5"/>
            <stop offset="1" stop-color="#e8eef4" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <!-- 世界坐标系根节点：视图变换**不绑定响应式数据**，由 applyView() 直接写到 <svg> 的
             CSS transform 上（见下）。原因：① 拖拽/缩放是每帧事件，若走 Vue 响应式，每帧都要对
             上千个 SVG 节点做一次 vdom diff + patch；② 用 CSS transform 而不是 SVG transform
             属性，浏览器可以把整幅图提升为合成层，平移只做合成而不重绘内容。 -->
        <g>
          <!-- 网格底纹（工业图低对比网格） -->
          <g class="t2d-grid" stroke="#dfe4ea" stroke-width="1">
            <path v-for="l in gridV" :key="'gv'+l" :d="`M${l} 0 V${bounds.h}`"/>
            <path v-for="l in gridH" :key="'gh'+l" :d="`M0 ${l} H${bounds.w}`"/>
          </g>

          <!-- 设备节点：主工艺与辅助设备均为独立节点，统一参与下方 nodes 分层排布（见 relayout） -->

          <!-- 管线（正交折线 → 管道形态。中点标物料名小标签，不参与点击）
               管道 = 三层同路径描边叠加（见 PIPE_* 常量）：
                 ① 管壁：深色外描边，比管体每侧宽出 PIPE_EDGE_ADD/2 → 形成管子轮廓与厚度感；
                 ② 管体：物料色实心，管道主体（不透明，多线共线叠加不会变色）；
                 ③ 高光：细白线居中，模拟圆柱管顶面反光（低透明度，共线段叠加仍在可控范围）。
               折角用 round linejoin → 直角转弯呈「弯管」观感；反馈回流为虚线管（dash 三层同步）。
               流向表达：末端静态箭头已移除，改为「沿折线运动的小箭头」——
               箭头从源设备端口出发，经折线各折角抵达目标设备端口，直观表达物料流向。 -->
          <g>
            <path v-for="c in lines" :key="'pe'+c.id" :d="c.d" fill="none" :stroke="PIPE_EDGE_COLOR"
              :stroke-width="c.pipeEdgeW" :stroke-dasharray="c.dash" :stroke-opacity="c.pipeEdgeOp"
              stroke-linecap="round" stroke-linejoin="round" class="t2d-pipe"/>
            <path v-for="c in lines" :key="'pb'+c.id" :d="c.d" fill="none" :stroke="c.color"
              :stroke-width="c.pipeW" :stroke-dasharray="c.dash"
              stroke-linecap="round" stroke-linejoin="round" class="t2d-pipe"/>
            <path v-for="c in lines" :key="'ph'+c.id" :d="c.d" fill="none" stroke="#ffffff"
              :stroke-width="c.pipeHiW" :stroke-dasharray="c.dash" :stroke-opacity="c.pipeHiOp"
              stroke-linecap="round" stroke-linejoin="round" class="t2d-pipe"/>
            <!-- 动态流向箭头：path 直接复用折线 d（随布局重排自动跟随），rotate=auto 使箭头始终指向
                 当前段切线方向；opacity 与位移同周期淡入淡出，避免箭头在起点/终点突兀出现或消失。
                 每条 conn 都承载自己的箭头：母线汇流组内三台热风炉各有一个箭头从炉底出发，
                 在「母线带 → 高炉顶」段共线并入同一根总管（组内周期统一 + 相位均分，间距恒定）。
                 配色：箭头 = **管道物料色加深一档**（fill = 物料色 × FLOW_DARKEN，stroke = × FLOW_DARKEN_EDGE），
                 用「深色实心块 + 更深轮廓」从管体上脱开 —— 既保留物料色语义，也不像纯白箭头那样扎眼。
                 尺寸略宽于管径（PIPE_W + PIPE_EDGE_ADD ≈ 8.8），凸出管壁保证可辨。 -->
            <polygon v-for="c in lines" :key="'f'+c.id" class="t2d-flow" :fill="c.arrowFill"
              :stroke="c.arrowEdge" :stroke-width="FLOW_STROKE_W" stroke-linejoin="round"
              :points="c.feedback ? FLOW_PTS_FB : FLOW_PTS">
              <animateMotion :path="c.d" :dur="c.dur" :begin="c.begin" calcMode="linear" rotate="auto" repeatCount="indefinite"/>
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.06;0.94;1"
                :dur="c.dur" :begin="c.begin" repeatCount="indefinite"/>
            </polygon>
            <circle v-for="c in lines" :key="'m'+c.id" :cx="c.mx" :cy="c.my" :r="c.pipeW * 0.54" fill="#fff"
              :stroke="c.color" stroke-width="1.6" class="t2d-mid"/>
            <!-- 物料卡片：管道旁独立小卡片，上行材料名、下行流动速率（速率来自后端读数解析，
                 无量测点的管道只显示材料名）。卡片落在管道最长水平段旁，位置由 cards 计算并避让设备盒。 -->
            <g v-for="c in cards" :key="'k'+c.id" class="t2d-card" :transform="`translate(${c.x},${c.y})`">
              <!-- 卡片底：白底 + 物料色细边；左侧色条标记物料（与管道配色一致） -->
              <rect class="t2d-card-bg" x="0" y="0" :width="c.w" :height="c.h" rx="5"
                :stroke="c.color" stroke-opacity="0.45"/>
              <rect class="t2d-card-bar" x="1" y="1" width="2.6" :height="c.h - 2" rx="1.3" :fill="c.color"/>
              <!-- 卡片高度统一为两行：无速率的管道只显示材料名，垂直居中不显空 -->
              <text class="t2d-card-mat" :fill="c.color" :x="CARD_PAD_X"
                :y="CARD_PAD_Y + 10 + (c.rate ? 0 : CARD_LINE_H / 2)">{{ c.matName }}</text>
              <text v-if="c.rate" class="t2d-card-rate" :x="CARD_PAD_X" :y="CARD_PAD_Y + CARD_LINE_H + 10.5">
                <tspan class="t2d-card-val" :fill="c.rate.src === 'live' ? CARD_VAL_LIVE : CARD_VAL_SIM">{{ formatRate(c.rate.value) }}</tspan>
                <tspan class="t2d-card-unit" dx="2.5" :fill="c.rate.src === 'live' ? CARD_VAL_LIVE : CARD_VAL_SIM">{{ c.rate.unit }}</tspan>
              </text>
            </g>
          </g>

          <!-- 设备节点：无卡片底，设备平面图直接作为主体（参考水泥行业图：设备本体 + 名称浮签 + 实时数据） -->
          <g v-for="n in nodes" :key="n.id" :transform="`translate(${n.x},${n.y})`"
            :class="['t2d-node', { on: isSel(n), aux: isAux(n) }]"
            @click.stop="onNode(n)" @mouseenter="hovered = n.id" @mouseleave="hovered = null">
            <!-- 设备名称浮签（贴设备图形上缘，见 nameY） -->
            <text class="t2d-name" :x="boxW(n)/2" :y="nameY(n)" text-anchor="middle">{{ n.name }}</text>

            <!-- 设备主体：程序化绘制的伪 3D 图形（data/twin2dFigures.js，零图片资源）。
                 图形自带 viewBox → 显示盒宽高比 = 图形宽高比，图形四缘即显示盒四缘，
                 连线端点贴该盒（figRect），设备与管线之间不留空隙；描边用 non-scaling-stroke，
                 缩放时始终保持细线质感。 -->
            <DeviceFigure :type="n.repType || n.type" :box="figBox(n)"/>
            <!-- 高炉温度分区：与炉体图形共用同一份归一化轮廓（BF_PROFILE），天然对齐，
                 不再需要按 PNG 像素逐行标定（旧方案换图必错位） -->
            <BfTempOverlay v-if="n.type === 'blast_furnace'" :box="figBox(n)" :node="n"/>


            <!-- 底部实时 KPI（仅主工艺，悬浮在设备下方） -->
            <text v-if="isMain(n)" :x="boxW(n)/2" :y="boxH(n) - 7" text-anchor="middle" class="t2d-kpis">
              <tspan class="t2d-kpi-c">CO₂ {{ fmt(unitOf(n).co2_total) }} t/h</tspan>
              <tspan class="t2d-kpi-sep">　·　</tspan>
              <tspan class="t2d-kpi-e">能耗 {{ fmt(unitOf(n).energy_total) }} GJ/h</tspan>
            </text>
          </g>
        </g>
      </svg>
      <!-- 适配画布：原顶部 KPI 条已移除，按钮改为画布右下角悬浮（双击画布同效） -->
      <button type="button" class="t2d-fit" @click.stop="fitAll()" :title="t('适配画布（双击也可）')">{{ t('适配') }}</button>
    </div>

    <!-- 空方案提示 -->
    <div v-if="!nodes.length" class="t2d-empty">{{ t('暂无可编排工艺方案，请先在「流程编排」中构建工艺路线') }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, onUpdated, watch, nextTick } from 'vue'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'
import { MATERIAL_MAP, PROCESS_MAP } from '../data/flowLibrary'
import { T2D_GEOM, T2D_IMG_SCALE } from '../data/twin2dIcons'
import { figureAspect } from '../data/twin2dFigures'
import { resolvePipeRate, formatRate } from '../utils/pipeRate'
import BfTempOverlay from './BfTempOverlay.vue'
import DeviceFigure from './DeviceFigure.vue'

const store = useSimStore()
const wrap = ref(null)
const svg = ref(null)

const PAD = 56

// —— 布局常量：全厂统一拓扑分层(2026-09-09 需求重构) ——
// 不再把辅助设备合并成「系统模块 / 分组框」(孪生平台形态作废)：主工艺与全部辅助设备都是
// 独立节点，统一按方案连线(排除 feedback 回流)做「最长路径」分层 —— 无上游的原始节点
// (原料源/辅助源)落 rank0 竖列，下游逐层向右推进；每台设备只占一列，供料边只指向更右的
// 层，杜绝「前段→后段」连线横穿整条产线。
const TOP = 100            // 每列首台设备顶 y
const ROW_GAP_Y = 44       // 同列内上下相邻设备盒净空（含名称/KPI 与端口余量）
const COL_GAP_X = 84       // 相邻层列间距：设备盒右缘 → 下一列设备盒左缘的空档（路由竖道）

// —— 布局（深拷贝方案节点，在 2D 画布上独立排布，不污染编辑画布） ——
const nodes = ref([])
const conns = ref([])
const bounds = ref({ x: 0, y: 0, w: 1000, h: 600 })
const mainBand = ref({ l: 80, r: 900, top: 100, bot: 700 })

function relayout() {
  // —— 建图逻辑(2026-09-09 vC)：主工艺拓扑骨架 + 辅助设备外挂 ——
  // 用户要求改变建图方式：
  //   1) 先将主流程设备(main)按拓扑分层建图 —— 仅 main↔main 正向边做最长路径分层，
  //      rank0 原料源(焦炉→烧结→球团 / DRI竖炉→电炉)合并为同一「源列」自上而下竖排，
  //      主链(高炉→预处理→…→热轧)顶对齐主链行从左向右推进；
  //   2) 详细的辅助设备(aux)作为「外挂节点」，不再占主链列位 —— 每台 aux 沿其
  //      非 feedback 正向服务链锚定到被服务的主工艺设备，挂在主设备正下方；
  //      同链辅助(供氧→鼓风机→热风炉→高炉)纵向续排成「服务通道」，连线竖直短接。
  const raw = store.scheme && store.scheme.nodes ? store.scheme.nodes : []
  const rawC = store.scheme && store.scheme.connections ? store.scheme.connections : []
  const ns = JSON.parse(JSON.stringify(raw)).filter((n) => n && n.kind === 'process')
  const cs = JSON.parse(JSON.stringify(rawC)).filter((c) => c && c.from && c.to)
  let byId = new Map(ns.map((n) => [n.id, n]))
  const baseOrd = new Map(ns.map((n, i) => [n.id, i]))
  const isMainN = (n) => isMain(n)

  // —— A) 主工艺拓扑分层(仅 main↔main 正向边) ——
  const mains = ns.filter((n) => isMainN(n))
  const mset = new Set(mains.map((n) => n.id))
  const rank = new Map(mains.map((n) => [n.id, 0]))
  for (let pass = 0; pass <= mains.length; pass++) {
    let ch = false
    for (const c of cs) {
      if (c.feedback) continue
      const f = byId.get(c.from), t = byId.get(c.to)
      if (!f || !t || !mset.has(f.id) || !mset.has(t.id)) continue
      const v = rank.get(f.id) + 1
      if (v > rank.get(t.id)) { rank.set(t.id, v); ch = true }
    }
    if (!ch) break
  }
  const maxRank = Math.max(0, ...rank.values())
  const byRank = []
  for (let r = 0; r <= maxRank; r++) byRank.push([])
  for (const m of mains) byRank[rank.get(m.id)].push(m)

  // rank0 主源(原料源)合并为同一「源列」，按工艺顺序自上而下竖排一列(焦炉→烧结→球团 /
  // DRI竖炉→电炉)，避免三源横排时 焦炉/烧结机→高炉 的箭头横穿 球团 等设备；
  // rank≥1 主工艺一列一台，顶对齐主链行向右推进。
  const MAIN_SOURCE_ORDER = ['coke_oven', 'sinter_plant', 'pelletizing', 'dri_midrex', 'eaf']
  const SRC_IDX = new Map(MAIN_SOURCE_ORDER.map((t, i) => [t, i]))
  const srcOrd = (a, b) => {
    const ia = SRC_IDX.has(a.type) ? SRC_IDX.get(a.type) : 999
    const ib = SRC_IDX.has(b.type) ? SRC_IDX.get(b.type) : 999
    if (ia !== ib) return ia - ib
    return baseOrd.get(a.id) - baseOrd.get(b.id)
  }
  const colMain = [(byRank[0] || []).slice().sort(srcOrd)]   // colMain[c] = 该列自上而下的主设备数组
  for (let r = 1; r <= maxRank; r++) {
    for (const m of (byRank[r] || []).slice().sort((a, b) => baseOrd.get(a.id) - baseOrd.get(b.id))) {
      colMain.push([m])
    }
  }

  // —— B) 辅助设备锚定：沿非 feedback 正向边走，记录 (被服务main, 跳数) ——
  // depth=1 直达主设备(热风炉/引风机/喷吹…)，depth>1 为链路中继(鼓风机→热风炉 之类)
  const anchor = new Map()          // aux.id -> { mainId, depth } | null(游离)
  for (const a of ns) {
    if (isMainN(a)) continue
    let cur = a, depth = 0
    const seen = new Set([a.id])
    let anchored = null
    for (let k = 0; k < 30 && !anchored; k++) {
      let nxt = null
      for (const c of cs) {
        if (c.feedback || c.from !== cur.id) continue
        const v = byId.get(c.to)
        if (v && !seen.has(v.id)) { nxt = v; break }
      }
      if (!nxt) break
      cur = nxt; depth++
      if (isMainN(cur)) anchored = cur.id
      else seen.add(cur.id)
    }
    anchor.set(a.id, anchored ? { mainId: anchored, depth } : null)
  }

  // —— B1) 同类辅助合并(2026-09-10 用户需求)：**同类型**的多台辅助在 2D 显示层合成一台
  // 节点 —— 高炉送风簇 三套「供氧→鼓风机→热风炉」→ 一套竖链；全厂集中供氧/多台引风机
  // 也各并为一台(如 供氧系统 供 预处理/转炉/送风链，引风机 服务 烧结机+球团)。
  // 数据层 store.scheme 仍按真实设备建模不动，这里只聚合 2D 显示口径：
  //   - 代表节点取 baseOrd 最小的一台(通常是未带序号的首台，名称即类型中文名；
  //     若代表是第 N 台则把名称还原为类型中文名，去掉「热风炉3」之类序号)；
  //   - 非代表节点从画布移除，其连线端点改写到代表节点；
  //   - 改写后按 (from,to,toPort,material,feedback) 去重：多台→同一目标的同端口连线
  //     合成一条，母线汇流(≥2 源)不再触发。
  // 合并后节点的落位锚定取组内**最深服务链**(见下方重锚定)，其余目标的连线由管线
  // 经主带上方/下方走廊绕行(如 引风机 挂烧结机左侧、另有管线接球团)。
  {
    const groups = new Map()      // key(type) -> [auxId..]
    for (const a of ns) {
      if (isMainN(a)) continue
      if (!groups.has(a.type)) groups.set(a.type, [])
      groups.get(a.type).push(a.id)
    }
    const mergeMap = new Map()    // 被合并 auxId -> { rep, ports: Map(旧端口id -> 代表端口id) }
    for (const ids of groups.values()) {
      if (ids.length < 2) continue
      const rep = byId.get(ids[0])
      rep.name = (PROCESS_MAP[rep.type] || {}).label || rep.name
      // 合并组重锚定：取组内**最深**的服务链(如全厂供氧系统的深链
      // 供氧→鼓风机→热风炉→高炉，depth3 锚到高炉送风簇，而非 铁水预处理 depth1)
      // —— 深链成员在通道内竖直短接；若沿用首台锚定(浅链)，供氧会被压在
      // 铁水预处理正下方，向上接鼓风机的管线被预处理盒堵死，只能绕全图外圈。
      // 同深取首台自身(id_fan 两台都 depth1 → 维持 烧结机 锚定不动)。
      let best = anchor.get(ids[0])
      for (let i = 1; i < ids.length; i++) {
        const a2 = anchor.get(ids[i])
        if (a2 && (!best || a2.depth > best.depth)) best = a2
      }
      if (best) anchor.set(ids[0], best)
      for (let i = 1; i < ids.length; i++) {
        // 端口映射：被合并实例与代表节点同模板，按「方向+物料」对齐到代表端口
        // （三台鼓风机各吹各自热风炉的 in 口，端口 id 不同 —— 不映射则去重键不一致，
        //   会残留 3 条平行线）
        const dup = byId.get(ids[i])
        const pm = new Map()
        for (const dir of ['in', 'out']) {
          const a = (dup.ports && dup.ports[dir]) || []
          const b = (rep.ports && rep.ports[dir]) || []
          const used = new Set()
          for (const pa of a) {
            const t = b.find((p) => p.material === pa.material && !used.has(p.id))
            if (t) { pm.set(pa.id, t.id); used.add(t.id) }
          }
        }
        mergeMap.set(ids[i], { rep: ids[0], ports: pm })
      }
    }
    if (mergeMap.size) {
      for (const c of cs) {
        {
          const m = mergeMap.get(c.from)
          if (m) { c.from = m.rep; c.fromPort = m.ports.get(c.fromPort) || c.fromPort }
        }
        {
          const m = mergeMap.get(c.to)
          if (m) { c.to = m.rep; c.toPort = m.ports.get(c.toPort) || c.toPort }
        }
      }
      const seen = new Set()
      for (let i = cs.length - 1; i >= 0; i--) {
        const c = cs[i]
        const k = [c.from, c.to, c.toPort, c.material, c.feedback ? 1 : 0].join('|')
        if (seen.has(k)) cs.splice(i, 1)
        else seen.add(k)
      }
      const drop = new Set(mergeMap.keys())
      for (let i = ns.length - 1; i >= 0; i--) if (drop.has(ns[i].id)) ns.splice(i, 1)
      // byId 重建：E) 段以 byId.has 过滤脏连线，必须与裁减后的 ns 一致
      byId = new Map(ns.map((n) => [n.id, n]))
    }
  }

  // 每个主设备收集其外挂辅助 → 组织成「服务通道」：直达主设备的 aux 为通道根，
  // 其上游(aux→aux 回溯)纵向续在同一通道 —— 保证 供氧→鼓风机→热风炉→高炉 竖直短接。
  const chainsOf = new Map()      // mainId -> [ [aux..], [aux..], ... ](根在前，越深越靠下)
  const usedAux = new Set()
  for (const m of mains) {
    const mid = m.id
    const list = ns.filter((a) => {
      if (isMainN(a)) return false
      const mt = anchor.get(a.id)
      return !!mt && mt.mainId === mid
    })
    const roots = list.filter((a) => anchor.get(a.id).depth === 1)
      .sort((a, b) => baseOrd.get(a.id) - baseOrd.get(b.id))
    const chains = roots.map((r) => [r])
    for (const r of roots) usedAux.add(r.id)
    const deeper = list.filter((a) => anchor.get(a.id).depth > 1)
      .sort((a, b) => {
        const da = anchor.get(a.id).depth, db = anchor.get(b.id).depth
        if (da !== db) return da - db
        return baseOrd.get(a.id) - baseOrd.get(b.id)
      })
    for (const a of deeper) {
      // 找该 aux 的 forward 目标：在**全部**正向连线里取第一条「目标已在本主设备
      // 某条通道中」的连线 —— 不能只看第一条连线：同类合并后的节点(如全厂供氧系统)
      // 首条出线可能指向别的目标(→铁水预处理)，按首条判定会误判为游离节点
      let tgt = null
      for (const c of cs) {
        if (c.feedback || c.from !== a.id) continue
        const v = byId.get(c.to)
        if (v && chains.some((c2) => c2.some((x) => x.id === v.id))) { tgt = v; break }
      }
      const ch = chains.find((c2) => tgt && c2.some((x) => x.id === tgt.id))
      if (ch) { ch.push(a); usedAux.add(a.id) }
    }
    chainsOf.set(mid, chains)
  }

  // —— B2) 独立下挂链抽取(2026-09-09 用户需求：喷吹系统放到高炉下面) ——
  // 高炉默认 top 上挂送风簇，但其中 root=injector 的喷吹链要求单独挂在高炉正下方，
  // 与三套「热风炉→鼓风机→供氧」送风链分开摆放 —— 抽出的链进 bottomOf[mainId]，
  // placeMainAux 时先在其主设备下方单独排布。
  const bottomOf = new Map()
  for (const m of mains) {
    const chains = chainsOf.get(m.id) || []
    const bChains = []
    const tChains = []
    for (const ch of chains) {
      if (ch[0] && ch[0].type === 'injector') bChains.push(ch)
      else tChains.push(ch)
    }
    if (bChains.length) bottomOf.set(m.id, bChains)
    if (tChains.length !== chains.length) chainsOf.set(m.id, tChains)
  }
  const orphans = ns.filter((a) => !isMainN(a) && !usedAux.has(a.id))
    .sort((a, b) => baseOrd.get(a.id) - baseOrd.get(b.id))

  // —— C) 坐标：源列主源自上而下竖排；下游主列顶对齐同一条「主链行」向右推进 ——
  // 外挂方位(2026-09-09 微调)：
  //   'bottom' 默认：簇在主设备下方竖直续链(供氧系统/供氧系统2 等)
  //   'left'   ：引风机 放在主源(烧结机/球团)左侧并排 —— 不再占源列纵向空间
  //   'top'    ：高炉送风簇放在高炉上方，簇内自下而上 depth 升序(热风炉→鼓风机→供氧)，
  //              即 供氧系统(顶)→鼓风机(中)→热风炉(底,贴高炉) 竖直短接
  const AUX_SIDE = { sinter_plant: 'left', pelletizing: 'left', blast_furnace: 'top' }
  const sideOf = (m) => AUX_SIDE[m.type] || 'bottom'
  // —— 手工落位干预(2026-09-11 用户需求) ——
  // 卡片要贴在管道旁，几处设备贴得太紧、缝隙塞不下卡片，按用户指定位置手工挪开：
  //   AUX_PIN  ：改挂到指定主设备的指定方位。被 pin 的辅助**仍留在原服务簇里参与占位
  //              计算**(chainH/chainW 不变)，只是不执行自动落位 —— 否则簇高变化会连带
  //              推动主链行中线，整幅图跟着位移。
  //   AUX_SHIFT：在当前落位基础上做纯平移(单位 px)，用于「挪一点」这类微调。
  //   AUX_PIN.alignRow：落位后再把**垂直中线**对齐到指定设备(同级辅助)，使两者之间的
  //              横连成为一条直线；与 side:'top' 联用时 = 主设备正上方那一列 + 指定行。
  const AUX_PIN = {
    // 供氧系统原为高炉送风簇的共享型链根(挂鼓风机右侧)，改挂铁水预处理正上方：
    // 它本来就直供预处理/转炉，落在这里三段连线都变短，也让出送风簇右侧的卡片位。
    // alignRow:'blower' —— 纵向与鼓风机同排(两者盒高都是 140，行对齐即盒顶对齐)，
    // 「供氧系统→鼓风机」的氧气线整段水平，不再先上折再左行。
    oxy_supply: { main: 'hot_metal_pretreat', side: 'top', alignRow: 'blower' },
  }
  const AUX_SHIFT = {
    injector: [0, 46],     // 喷吹系统：下移，让开高炉底部与「喷吹煤粉」卡片之间的横缝
    id_fan: [-34, 0],      // 引风机：左移，拉开与烧结机左缘的间距，给「抽力」卡片腾位
  }
  const AUX_GAP = 16        // 主设备(边) → 外挂区首层净空
  const LINK_GAP_Y = 14     // 服务通道内上下级辅助净空
  const CHAIN_GX = 16       // 相邻服务通道横向净空
  const chainW = (ch) => Math.max(0, ...ch.map((n) => boxW(n)))
  const chainH = (ch) => ch.reduce((s, a, i) => s + boxH(a) + (i ? LINK_GAP_Y : 0), 0)
  const auxSpanW = (chains) => {
    if (!chains.length) return 0
    return chains.reduce((s, ch) => s + chainW(ch), 0) + (chains.length - 1) * CHAIN_GX
  }
  const auxSpanH = (chains) => (chains.length ? Math.max(0, ...chains.map(chainH)) : 0)
  const chainsOfM = (m) => chainsOf.get(m.id) || []
  // 左挂簇宽(引风机类):主设备左缘向左让出的水平空间
  const leftPadOf = (m) => (sideOf(m) === 'left' && chainsOfM(m).length
    ? AUX_GAP + Math.max(0, ...chainsOfM(m).map(chainW)) : 0)
  // 某台辅助直接服务的「主设备」集合 —— 同类合并后 供氧系统/引风机 会同时服务多台主设备，
  // 这类「共享型」辅助的落位必须兼顾多个目标，不能只顺着自己那条服务链竖直叠放。
  const mainTargetsOf = (a) => {
    const s = new Set()
    for (const c of cs) {
      if (c.feedback || c.from !== a.id || !mset.has(c.to)) continue
      s.add(c.to)
    }
    return [...s]
  }
  // 通道「横向伸出量」= 该通道内所有辅助服务到的最右主设备的**拓扑位置序**
  // （列序号 × 1000 + 列内序号；-∞ 记最左）。用于同排横排时的左右次序：伸出越远的越靠右，
  // 出线才不会被同排左侧邻居的节点盒挡住。
  // 注意：这里必须用「拓扑序」而不是节点 x —— placeMainAux 在源列阶段就被调用，
  // 右侧各列的主设备 x 此时尚未落位(是 undefined)，用 x 会算出 NaN、排序静默失效。
  const colPosOf = new Map()
  colMain.forEach((col, ci) => col.forEach((mm, ri) => colPosOf.set(mm.id, ci * 1000 + ri)))
  const chainReachOf = (ch) => {
    let r = -Infinity
    for (const a of ch) {
      for (const t of mainTargetsOf(a)) {
        if (colPosOf.has(t)) r = Math.max(r, colPosOf.get(t))
      }
    }
    return r
  }
  // 按方位摆放某台主设备的外挂簇(须在 m.x/m.y 确定后调用)
  const placeMainAux = (m) => {
    // 0) 独立下挂链(喷吹系统等抽出的特殊链)：先以主设备中心横排、挂在主设备底
    const bch = bottomOf.get(m.id)
    if (bch && bch.length) {
      const center = m.x + boxW(m) / 2
      let x0 = center - auxSpanW(bch) / 2
      const rootY = m.y + boxH(m) + AUX_GAP
      for (const ch of bch) {
        const cw = chainW(ch)
        const ccx = x0 + cw / 2
        x0 += cw + CHAIN_GX
        let yy = rootY
        for (const a of ch) {
          a.x = ccx - boxW(a) / 2
          a.y = yy
          yy += boxH(a) + LINK_GAP_Y
        }
      }
    }
    const chains = chainsOfM(m)
    if (!chains.length) return
    const side = sideOf(m)
    if (side === 'left') {
      // 引风机等:右缘贴主设备左缘、整簇垂直居中于主设备盒
      const stackH = chains.reduce((s, ch) => s + chainH(ch), 0) + (chains.length - 1) * LINK_GAP_Y
      let cy = m.y + (boxH(m) - stackH) / 2
      for (const ch of chains) {
        const cw = chainW(ch)
        const x = m.x - AUX_GAP - cw
        for (const a of ch) {
          a.x = x + (cw - boxW(a)) / 2
          a.y = cy
          cy += boxH(a) + LINK_GAP_Y
        }
        cy -= LINK_GAP_Y                      // 撤销链尾多算的间距，链间仍留 LINK_GAP_Y
      }
      return
    }
    if (side === 'top') {
      // 送风簇(高炉)：竖直叠链，自下而上 depth 升序(热风炉 底贴 主设备顶)。
      // —— 轴对齐(2026-09-10)：整簇按**图形外接盒中心**对齐到主设备顶口的 x(见 axisX)，
      //    而不是把「盒左缘」对齐主设备盒左缘。旧口径下 热风炉/鼓风机 的图形中心(x=735)
      //    与高炉顶口夹取后的 x(= 高炉图形左缘+8 = 779) 相差 44px，导致 热风炉→高炉
      //    每次都要先横挪一段再下落(小折角)。按轴对齐后 供氧→鼓风机→热风炉→高炉
      //    三段竖连的 x 完全相同 → 全为直线。
      const mr = figRect(m)
      const axisX = Math.min(Math.max(mr.x + mr.w / 2, mr.x + 8), mr.x + mr.w - 8)
      const botY = m.y - AUX_GAP
      for (const ch of chains) {
        // 链根(最深一级，如全厂供氧系统)若同时服务 ≥2 台**主设备**，它是「共享型」公用设备：
        // 竖直叠在簇顶会让它的跨设备连线从画布顶部绕一整圈(供氧→转炉 曾达 1277px)。
        // 改为挂在「下游节点」同一行的右侧 —— 跨设备连线变成「右行 + 下落」短折线，
        // 与下游的横连也保持直线(同排对齐)。
        const tail = ch[ch.length - 1]
        const sideRoot = ch.length > 1 && mainTargetsOf(tail).length >= 2 ? tail : null
        const col = sideRoot ? ch.slice(0, -1) : ch
        let cyBot = botY
        let right = -Infinity
        for (const a of col) {
          const b = figBox(a)                    // 图形外接盒（节点内偏移），用于轴对齐
          a.x = axisX - (b.x + b.w / 2)          // 图形中心落在竖直通道轴上
          a.y = cyBot - boxH(a)
          cyBot = a.y - LINK_GAP_Y
          right = Math.max(right, a.x + boxW(a))
        }
        if (sideRoot && !AUX_PIN[sideRoot.type]) {
          const down = col[col.length - 1]        // 链根的下一级(如鼓风机)
          sideRoot.x = right + AUX_GAP
          sideRoot.y = down.y + (boxH(down) - boxH(sideRoot)) / 2   // 同排 → 横连为直线
        }
      }
      return
    }
    // bottom(默认):簇在主设备正下方以主设备中心横排，链内自上而下 depth 升序。
    // 横排左→右按「目标伸出量」升序：服务目标越靠右的辅助越靠右放 —— 否则它向右的
    // 出线会被同排左侧邻居的节点盒挡住，只能绕到底部车道再爬回目标(短流程 供氧系统
    // →LF/RH 曾达 721/1133px、4 个折角；换序后降为 2 折角的直角折线)。
    const ordered = [...chains].sort((p, q) => chainReachOf(p) - chainReachOf(q))
    const center = m.x + boxW(m) / 2
    let x0 = center - auxSpanW(ordered) / 2
    const rootY = m.y + boxH(m) + AUX_GAP
    for (const ch of ordered) {
      const cw = chainW(ch)
      const ccx = x0 + cw / 2
      x0 += cw + CHAIN_GX
      let yy = rootY
      for (const a of ch) {
        a.x = ccx - boxW(a) / 2
        a.y = yy
        yy += boxH(a) + LINK_GAP_Y
      }
    }
  }
  // 列宽 = 主设备(或 bottom/top 簇横宽) + 左挂让位；左挂簇不计入列宽(独占左侧让位)
  const colW = colMain.map((col) => {
    const padL = Math.max(0, ...col.map(leftPadOf))
    const span = Math.max(0, ...col.map((m) => {
      const bspan = auxSpanW(bottomOf.get(m.id) || [])
      return Math.max(boxW(m), auxSpanW(chainsOfM(m)), bspan)
    }))
    return padL + span
  })
  const orphanColW = orphans.length ? Math.max(...orphans.map((n) => boxW(n))) : 0
  if (orphanColW) colW.push(orphanColW)
  const colX = []
  let cx = 80
  for (let i = 0; i < colW.length; i++) { colX.push(cx); cx += colW[i] + COL_GAP_X }

  // 1) 源列(col0)：主源自上而下竖排(左挂引风机占主源左侧让位，不再撑高列)；bottom 挂才占纵向空间。
  //    这里只算「各台相对源列起点的纵向偏移」(自身高度 + bottom 外挂 + 间距)，绝对 y 由第 3 步统一落位
  //    —— 因为主链行中线与源列起点互相依赖（烧结机中线要落在主链行上），必须先解耦。
  const srcCol = colMain[0]
  const c0PadL = Math.max(0, ...srcCol.map(leftPadOf))
  const srcOff = []
  {
    let acc = 0
    for (let i = 0; i < srcCol.length; i++) {
      srcOff.push(acc)
      acc += boxH(srcCol[i])
      if (sideOf(srcCol[i]) === 'bottom' && chainsOfM(srcCol[i]).length) acc += AUX_GAP + auxSpanH(chainsOfM(srcCol[i]))
      if (i < srcCol.length - 1) acc += ROW_GAP_Y
    }
  }

  // 2) 主链行 = 主链设备的**垂直中线**所在水平线 rowMid（2026-09-10 中线对齐改版）
  //    背景：新图组里 高炉(1248×2887 比 0.43)/铁水预处理(812×1680 比 0.48)/DRI竖炉(比 0.42)
  //    是极竖长图，只有加高节点盒才能把图形撑满；各盒高不再相同后，若仍按「盒顶对齐」，
  //    各设备盒中心高低不一 → sideAnchorOf 取对端中心 y → 主带 R→L 连线两端 y 不等(dy≠0)，
  //    会出现「stub + 竖爬段」台阶。改为按中心对齐：各主设备中心同高，主带连线严格水平。
  //    三步定序：① 短流程源列锚 → ② 上挂簇顶约束 → ③ 长流程源列锚定（烧结机中线落行上）。
  const anchorIdx = srcCol.findIndex((m) => m.type === 'sinter_plant')
  const rowH = Math.max(...mains.map((m) => boxH(m)))   // 最高主设备盒（决定主链行中线的最低位置）
  const midOf = (m) => boxH(m) / 2
  let rowMid = TOP + rowH / 2
  if (anchorIdx < 0) {
    const fwdSrc = srcCol.filter((m) =>
      cs.some((c) => !c.feedback && c.from === m.id && mset.has(c.from) && mset.has(c.to)))
    if (fwdSrc.length === 1) {
      const s = fwdSrc[0]
      rowMid = TOP + srcOff[srcCol.indexOf(s)] + midOf(s)
    } else if (fwdSrc.length > 1) {
      const cys = fwdSrc.map((m) => TOP + srcOff[srcCol.indexOf(m)] + midOf(m))
      rowMid = Math.max(TOP + rowH / 2, (Math.min(...cys) + Math.max(...cys)) / 2)
    }
  }
  //    ② 上挂簇顶不得贴画布顶:主链行最高盒的盒顶至少让出 AUX_GAP + 簇深 + 顶部留白(30)
  for (const m of mains) {
    if (sideOf(m) !== 'top' || !chainsOfM(m).length) continue
    rowMid = Math.max(rowMid, AUX_GAP + auxSpanH(chainsOfM(m)) + 30 + midOf(m))
  }
  //    ③ 源列锚定(长流程)：源列含烧结机时，让**烧结机的中线**落在主链行上(与高炉同高)，
  //       烧结矿→高炉 走水平直连；源列整体下移、各台相对间距与次序不变。
  //       源列起点会顶到 TOP(`want < TOP`)时**以对齐为准、把主链行一起下移**到
  //       TOP + 源列偏移 —— 不能放弃对齐：送风簇层数变化会改变 rowMid(如 3 层→2 层)，
  //       若此处让 rowMid 优先就会让烧结机与高炉差几像素、水平直连失效。
  let srcY0 = TOP
  if (anchorIdx >= 0) {
    const sSinter = srcCol[anchorIdx]
    const want = rowMid - midOf(sSinter) - srcOff[anchorIdx]
    if (want >= TOP) srcY0 = want
    rowMid = srcY0 + srcOff[anchorIdx] + midOf(sSinter)
  }

  // 3) 源列落位(绝对 y = 源列起点 + 相对偏移)
  //    水平方向**在列内居中**（而非左对齐）：源列里原料设备盒宽不等（烧结机/球团 430、
  //    焦炉 340），左对齐会让各台中心错开 45px —— 列内纵向流（焦炉→烧结机 焦炭回供）
  //    会从"竖直线"退化成斜折线，源列右侧也参差不齐。
  const c0Span = Math.max(...srcCol.map((m) => boxW(m)))
  for (let i = 0; i < srcCol.length; i++) {
    const m = srcCol[i]
    m.x = colX[0] + c0PadL + (c0Span - boxW(m)) / 2
    m.y = srcY0 + srcOff[i]
    placeMainAux(m)
  }

  // 4) 其余列：每列一台主设备，**中线对齐**主链行(盒高不同也不会出现中心高差)；外挂簇按方位摆放
  for (let ci = 1; ci < colMain.length; ci++) {
    const m = colMain[ci][0]
    m.x = colX[ci] + (colW[ci] - boxW(m)) / 2
    m.y = Math.round(rowMid - midOf(m))
    placeMainAux(m)
  }
  if (orphans.length) {
    let yy = TOP
    const ocx = colX[colW.length - 1] + orphanColW / 2
    for (const a of orphans) { a.x = ocx - boxW(a) / 2; a.y = yy; yy += boxH(a) + ROW_GAP_Y }
  }

  // 5) 手工落位干预(2026-09-11 用户需求)：见上方 AUX_PIN/AUX_SHIFT 说明。
  //    必须放在所有自动落位之后：这里只做最终覆写，不参与列宽/簇高的解算。
  for (const a of ns) {
    const pin = AUX_PIN[a.type]
    if (pin) {
      const t = mains.find((m) => m.type === pin.main)
      if (t) {
        const b = figBox(a)                       // 图形外接盒(含图内偏移)，用于轴对齐
        if (pin.side === 'top' || pin.side === 'bottom') {
          const tr = figRect(t)
          const axisX = Math.min(Math.max(tr.x + tr.w / 2, tr.x + 8), tr.x + tr.w - 8)
          a.x = Math.round(axisX - (b.x + b.w / 2))
          a.y = Math.round(pin.side === 'top' ? t.y - AUX_GAP - boxH(a) : t.y + boxH(t) + AUX_GAP)
          // 指定行对齐：与同级设备垂直中线等高 —— 行对齐后两者横连即为直线
          const rowDev = pin.alignRow ? ns.find((n) => n.type === pin.alignRow) : null
          if (rowDev) a.y = Math.round(rowDev.y + (boxH(rowDev) - boxH(a)) / 2)
        } else {
          a.x = Math.round(pin.side === 'left' ? t.x - AUX_GAP - boxW(a) : t.x + boxW(t) + AUX_GAP)
          a.y = Math.round(t.y + (boxH(t) - boxH(a)) / 2)
        }
      }
    }
    const sh = AUX_SHIFT[a.type]
    if (sh) { a.x += sh[0]; a.y += sh[1] }
  }

  // —— D) 主带 = 全部设备包围盒(路由走廊基准) ——
  if (ns.length) {
    mainBand.value = {
      l: Math.min(...ns.map((n) => n.x)),
      r: Math.max(...ns.map((n) => n.x + boxW(n))),
      top: Math.min(...ns.map((n) => n.y)),
      bot: Math.max(...ns.map((n) => n.y + boxH(n))),
    }
  }

  // —— E) 显示连线：与 scheme 一一对应，剔除端点缺失的脏连线 ——
  const dcs = []
  for (const c of cs) {
    if (!byId.has(c.from) || !byId.has(c.to)) continue
    dcs.push({ id: c.id, from: c.from, fromPort: c.fromPort, to: c.to, toPort: c.toPort, material: c.material, feedback: !!c.feedback })
  }

  // —— F) 包围盒：内容区 + 回流车道预留，保证「适配」后全部可见 ——
  const rectL = ns.length ? Math.min(80, ...ns.map((n) => n.x)) : 80
  const rectT = ns.length ? Math.min(TOP, ...ns.map((n) => n.y)) : TOP
  const rectR = ns.length ? Math.max(...ns.map((n) => n.x + boxW(n))) : 1200
  const rectB = ns.length ? Math.max(...ns.map((n) => n.y + boxH(n))) : 400
  let bwdN = 0
  for (const c of cs) {
    if (!c.feedback) continue
    const f = byId.get(c.from), t = byId.get(c.to)
    if (!f || !t) continue
    if ((f.x + boxW(f) - 13) - (t.x + 13) > FWD_TOL) bwdN++
  }
  const floor = rectB + 26 + bwdN * LANE_STEP + 20
  const pad = PAD
  bounds.value = { x: rectL - pad, y: rectT - pad, w: rectR - rectL + pad * 2, h: Math.max(rectB, floor) - rectT + pad * 2 }
  nodes.value = ns
  conns.value = dcs
  nextTick(fitAll)
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
  // 端口扩展间距 12：多入口设备（如高炉）仅按端口数保守补高，防止顶部名称/
  // 底部 KPI 与密集入口互压；实际统一尺寸仍以 T2D_GEOM 高度为准（端口数扩展几乎不触发）。
  const h = Math.max(g.h, 96 + (cnt - 1) * 12)
  return isMain(n) ? h + KPI_H : h
}

// 连线端点锚定（2026-09-09 用户约束改版）：不强制按端口模板固定进出侧（旧规「出必右、
// 入必左/上/下」已废弃）。连线两端一律按「对端盒中心相对自身中心的主导轴」在 上/下/左/右
// 四侧中自动贴边 —— 分层列内同列上下相邻的纵向流自然走上(T)下(B)，横向邻接流走 左(L)右(R)。
// 锚点取对端中心在该边上的投影并夹取到边内可用区间：
//   - L/R 边 y ∈ 名称带之下 ~ 底边之上（主设备 30..H-40；辅助设备 24..H-16）；
//   - T/B 边 x ∈ 盒缘内 8..W-8（避开四角与名称浮签居中区）。
// （2026-09-11 按用户要求回退：曾试过「L/R 夹到图形盒内缩 22%、T/B 按设备轮廓剖面吸附
//   端点」，但轮廓剖面会在设备带支架/附件的一侧把端点拉到很低处（如 供氧→转炉 落到
//   76% 高度、引风机→球团 落到 48%），观感反而不如贴盒缘，故恢复为上述口径。）
function sideAnchorOf(n, peer) {
  const W = boxW(n), H = boxH(n)
  const cx = n.x + W / 2, cy = n.y + H / 2
  const px = peer.x + boxW(peer) / 2, py = peer.y + boxH(peer) / 2
  const nx = (px - cx) / (W / 2), ny = (py - cy) / (H / 2)
  const side = Math.abs(ny) >= Math.abs(nx) ? (ny >= 0 ? 'B' : 'T') : (nx >= 0 ? 'R' : 'L')
  // 贴边坐标取「设备图形外接盒」(figRect)：有 PNG 图时已裁掉透明留白，
  // 连线端点落在设备本体边缘而非节点盒缘 —— 消除留白造成的设备↔管线空隙。
  const r = figRect(n)
  if (side === 'T' || side === 'B') {
    const x = Math.min(Math.max(px, r.x + 8), r.x + r.w - 8)
    return { x, y: side === 'T' ? r.y : r.y + r.h, side }
  }
  const main = isMain(n)
  const yTop = n.y + (main ? 30 : 24)
  const yBot = n.y + H - (main ? 40 : 16)
  return { x: side === 'L' ? r.x : r.x + r.w, y: Math.min(Math.max(py, yTop), yBot), side }
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

// —— 设备图形显示盒（节点局部坐标）——
// 图形由 data/twin2dFigures.js 程序化绘制，每种设备自带 viewBox（自然比例：高炉竖长、
// 烧结机扁长、风机近方）。这里按该比例等比 contain 到图带（名称带下方 → KPI/底部上方），
// 并按 T2D_IMG_SCALE 做「视觉面积归一」：显示盒面积 = 图带面积 × sc²，再由比例反解两维 ——
// 极端比例设备不会被压成细条，与中等比例设备观感大小一致（沿用 PNG 时代的调校结论）。
// 返回的 x/y/w/h 即「图形真实边界」在节点内的位置：图形四缘 = 显示盒四缘，
// 连线端点直接贴该盒（见 figRect/sideAnchorOf），设备与管线严丝合缝。
function figBox(n) {
  const W = boxW(n), H = boxH(n)
  const main = isMain(n)
  const top = 24
  const bot = H - (main ? 26 : 10)
  const availH = Math.max(24, bot - top)
  const availW = Math.max(24, W - 6)
  const sc = T2D_IMG_SCALE[n.type] || 1
  const ar = figureAspect(n.repType || n.type)     // 宽 / 高
  let w = Math.sqrt(availW * availH * sc * sc * ar)
  let h = w / ar
  if (w > availW) { w = availW; h = w / ar }
  if (h > availH) { h = availH; w = h * ar }
  return { x: (W - w) / 2, y: top + (availH - h) / 2, w, h }
}
// 设备「图形外接盒」(绝对坐标)：连线端点/障碍判定以此为准，保证端点贴在设备本体边缘。
function figRect(n) {
  const b = figBox(n)
  return { x: n.x + b.x, y: n.y + b.y, w: b.w, h: b.h }
}
// 名称浮签的纵向位置（节点内坐标）：紧贴「设备图形外接盒」上缘 8px。
// 原为固定 y=18 —— 对图形盒垂直居中且偏下的扁长图（烧结机 4.2:1、球团 3.0:1、热轧机 2.2:1）
// 图形盒上缘离节点顶很远，名称会浮在图形上方几十像素的空白里（烧结机曾达 86px），
// 看起来像贴着上一台设备。改为跟随图形盒后，所有设备的「名称→设备」间距一致。
function nameY(n) {
  const rel = figRect(n).y - n.y
  return Math.max(14, Math.round(rel - 8))
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
// 颜色加深（箭头用）：RGB 等比例缩放 → 保持同一色系，只把明度压暗。
// k < 1 越深。比 HSL 往返转换更短，对物料色这种中等明度的色板足够自然。
function shade(hex, k) {
  const h = String(hex).replace('#', '')
  const v = [0, 2, 4].map((i) => {
    const x = Math.round(parseInt(h.slice(i, i + 2), 16) * k)
    return Math.max(0, Math.min(255, x)).toString(16).padStart(2, '0')
  })
  return '#' + v.join('')
}

function unitOf(n) {
  const units = store.resultForView && store.resultForView.units ? store.resultForView.units : []
  return units.find((x) => x.id === n.id) || {}
}
function isSel(n) { return store.selectedUnitId === n.id || store.selectedFlowId === n.id }

// —— 管线正交路径(工业流程图) ——
// 端点口径(2026-09-09 用户约束改版)：连线端不再按设备 in/out 端口模板固定进出侧，
// 一律按「对端方位」自动贴 上/下/左/右 侧（见 sideAnchorOf）。
// 路由原则：每条线尽量「少转折、每段笔直」，杜绝网格锯齿(旧 A* 兜底会拉出一串 10px 小台阶，
// 视觉上像“波动”)。做法：
//   1) 先试直连 H-then-V（同目标同侧多线各自走独立「入口接近列」，不共线）；
//   2) 若穿第三方设备框，枚举「候选走廊」(直连高度 / 主行顶上方走廊 / 主行底下方车道 /
//      源组/目标组顶底空带) ×「候选竖列」(源口列 / 源组右缘外 / 主带左右外侧 / 目标左右外)，
//      用穿盒检测过滤，取「不穿任何设备框」中路径最短者 → 每段都是长直段；
//   3) 极端兜底走主带顶大走廊，几乎不会进入。
// 端点重叠(同节点同侧同坐标)沿边按 ±k*14 错开，保持束状整齐。
const FWD_TOL = 100
const LINE_STEP = 14
const BUS_GAP = 30  // 母线带离源组盒底的间距（>STUB 让竖直段明显、便于看清箭头从源出发的路径）
const LANE_STEP = 16
const STUB = 8   // 端口引线长度：端口已贴设备图缘，stub 只需短引段把箭头/线头送到图缘外即可
const UPPER_GAP = 22
const OBST_PAD = 4

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
// 单线端点手工修正表(2026-09-11 用户需求)：只改列出的连线端点，其它连线维持 sideAnchorOf。
// 键 = 'fromType>toType:material'（与 CARD_PIN 同口径）；from/to 指定该端「贴 figRect 的某侧」：
//   R/L：x = 图形该侧缘，y = 对端中心 y 夹取到「图形纵区间」内（不再用节点盒区间 ——
//        节点盒含名称带/KPI 带比图形大，供氧→转炉源端曾因此悬到图形下方留白 9px）；
//   T/B：y = 图形该侧缘，x = 图形横向中点。
//   dx/dy：在贴边结果上再平移（如转炉图形盒顶缘仅氧枪尖(中心右 +10)是实心，角上是透明留白）。
const ENDPOINT_PIN = {
  'oxy_supply>bof:oxygen': { from: { side: 'R' }, to: { side: 'T', dx: 10 } },
}
function _figSideAnchor(n, peer, side, dx = 0, dy = 0) {
  const r = figRect(n)
  if (side === 'T' || side === 'B') return { x: r.x + r.w / 2 + dx, y: (side === 'T' ? r.y : r.y + r.h) + dy, side }
  const py = peer.y + boxH(peer) / 2
  return { x: (side === 'L' ? r.x : r.x + r.w) + dx, y: Math.min(Math.max(py, r.y + 4), r.y + r.h - 4) + dy, side }
}
function _lineRoutes() {
  const mainTop = mainBand.value.top, mainBot = mainBand.value.bot
  const list = []
  for (const c of conns.value) {
    const f = nodes.value.find((n) => n.id === c.from)
    const t = nodes.value.find((n) => n.id === c.to)
    if (!f || !t) continue
    // 端点一律按「对端方位」自动贴边(上/下/左/右 四侧)，不区分固定 in/out 端口侧
    let p1 = sideAnchorOf(f, t)
    let p2 = sideAnchorOf(t, f)
    // 单线修正：仅 ENDPOINT_PIN 命中的连线覆盖端点（见上方注释）
    const ep = ENDPOINT_PIN[`${f.repType || f.type}>${t.repType || t.type}:${c.material}`]
    if (ep) {
      if (ep.from) p1 = _figSideAnchor(f, t, ep.from.side, ep.from.dx, ep.from.dy)
      if (ep.to) p2 = _figSideAnchor(t, f, ep.to.side, ep.to.dx, ep.to.dy)
    }
    list.push({ c, p1, p2, f, t })
  }
  // 端点错开：同一节点同一侧「落点坐标相同」的多线在沿边方向错开 ±k*LINE_STEP。
  // 旧「同端口 id」分组已无意义 —— 几何锚定后，(节点,侧,沿边坐标) 相同即视觉完全共线。
  const coordOf = (p) => (p.side === 'L' || p.side === 'R' ? Math.round(p.y) : Math.round(p.x))
  const srcSt = {}
  {
    const m = {}
    for (const r of list) {
      const k = r.f.id + '|' + r.p1.side + '|' + coordOf(r.p1)
      ;(m[k] = m[k] || []).push(r)
    }
    // 同源同侧多线的错开位：按「目标距离」**降序**分配 —— 最远的目标拿最靠外的口，
    // 近目标先拐入自己的目标竖列，远目标的横段从近目标竖段的**外侧**越过(不横穿)。
    // 距离按出口轴向取(R/L 比横距,T/B 比纵距)；「外侧」的方位见 outwardOf。
    const distOf = (r) => (r.p1.side === 'L' || r.p1.side === 'R'
      ? Math.abs(r.p2.x - r.p1.x) : Math.abs(r.p2.y - r.p1.y))
    // 错开方向：以「最外侧口」在**目标一侧的反方向**为准 —— 远目标的横段必须从近目标
    // 竖段的「外侧」越过，才不会横穿近目标那段竖直。出口轴为横(R/L)时垂直向是 y：
    // 目标在下方(y 增大) → 外侧是上方，远目标取更小的 y；目标在上方 → 外侧是下方，
    // 远目标取更大的 y。出口轴为纵(T/B)时同理用 x 判定(左右)。
    // 若只按「远目标取上方」写死：短流程 供氧→LF/RH(目标在上方)会把远目标 RH 顶到靠近
    // 目标口的一侧，其横段必穿近目标 LF 的竖爬段(实测交点 555,789)。
    const outwardOf = (arr) => {
      const side = arr[0].p1.side
      let sum = 0
      for (const r of arr) sum += side === 'L' || side === 'R' ? r.p2.y - r.p1.y : r.p2.x - r.p1.x
      return sum >= 0 ? 1 : -1
    }
    for (const arr of Object.values(m)) if (arr.length > 1) {
      const sorted = [...arr].sort((a, b) => distOf(b) - distOf(a))
      const outward = outwardOf(arr)
      sorted.forEach((r, i) => { srcSt[r.c.id] = outward * (i - (sorted.length - 1) / 2) * LINE_STEP })
    }
  }
  const dstOff = {}
  {
    const m = {}
    for (const r of list) {
      const k = r.t.id + '|' + r.p2.side + '|' + coordOf(r.p2)
      ;(m[k] = m[k] || []).push(r)
    }
    for (const arr of Object.values(m)) if (arr.length > 1) arr.forEach((r, i) => {
      dstOff[r.c.id] = (i - (arr.length - 1) / 2) * LINE_STEP
    })
  }
  // —— 共享目标端口的多源「母线汇流」预解析 ——
  // 目标：三台热风炉 → 高炉(同一 hot_blast 入口)不再画 3 条平行入线，合并为
  // 「母线带 + 支线逐级横接 + 干线单线入端口」一条热风总管。
  // 分组：同 (to,toPort) 且 ≥2 条 conn。
  // 走向：以「目标中心相对源组包围盒中心」的主导轴判定母线带方位(不再依赖各源
  //   sideAnchorOf 的原出口侧 —— top 簇中超出目标盒范围的源会被判成 L/R 而破坏同侧
  //   假设，这是旧实现「母线不合并」的根因)：
  //   - 目标在源组下方(B)：全部源口强制 B(盒底)出、母线带在源组底外 STUB、
  //     目标口强制 T(顶)入 —— 支线各从源底竖下 8px 到带、横接下一条源槽，
  //     最后一条(干线)沿带横到目标顶口竖落 8px 进盒；
  //   - 目标在源组右方(R)：源口强制 R(盒右)出、母线带在源组顶上方(旧位)，
  //     目标口维持 sideAnchorOf 结果 —— 兼容旧横排布局。
  // 收益：热风炉1/2/3 共用一根热风总管进风口带，避免画面 3 个独立 stub/3 条平行入线。
  const busData = new Map()
  {
    const m = {}
    for (const r of list) { const k = r.c.to + '|' + r.c.toPort; (m[k] = m[k] || []).push(r) }
    for (const arr of Object.values(m)) {
      if (arr.length < 2) continue
      const t = arr[0].t
      const fr = new Map(arr.map((r) => [r.c.id, figRect(r.f)]))
      const frt = figRect(t)
      const gx0 = Math.min(...[...fr.values()].map((b) => b.x))
      const gx1 = Math.max(...[...fr.values()].map((b) => b.x + b.w))
      // 母线带位置按「节点盒缘」而非图形缘推算：源口贴图形边缘后，若母线带也贴图形外，
      // 带会落在源盒内部高度上，水平段将横穿相邻源盒而被穿盒检测拒绝 → 退回三线直连。
      const gy0box = Math.min(...arr.map((r) => r.f.y))
      const gy1box = Math.max(...arr.map((r) => r.f.y + boxH(r.f)))
      const ax = (t.x + boxW(t) / 2 - (gx0 + gx1) / 2) / Math.max(1, (gx1 - gx0) / 2)
      const ay = (t.y + boxH(t) / 2 - (gy0box + gy1box) / 2) / Math.max(1, (gy1box - gy0box) / 2)
      const sd = Math.abs(ay) >= Math.abs(ax) ? (ay >= 0 ? 'B' : null) : (ax >= 0 ? 'R' : null)
      if (!sd) continue
      // 母线带：B 走源组盒底外 BUS_GAP（≥ STUB 使竖直段可见、箭头沿「源底 → 母线带 → 横移 → 高炉」路径清晰可辨）；
      //        R 走源组盒顶上方(旧位，源口竖上引带)。
      if (sd === 'B' && t.y - gy1box < STUB * 2) continue
      const yBus = sd === 'B' ? gy1box + BUS_GAP : gy0box - 16
      // 源口统一重定向到母线走向侧，并贴在「设备图形边缘」(figRect)：B → 图形底；R → 图形右
      for (const r of arr) {
        const b = fr.get(r.c.id)
        if (sd === 'B') {
          r.p1 = { side: 'B', x: Math.min(Math.max(t.x + boxW(t) / 2, b.x + 8), b.x + b.w - 8), y: b.y + b.h }
        } else {
          r.p1 = { side: 'R', x: b.x + b.w, y: Math.min(Math.max(t.y + boxH(t) / 2, b.y + 8), b.y + b.h - 8) }
        }
      }
      // 源槽位（按源口 x 排序）：决定组内顺序（末位为干线），用于相位均分与支线标记
      const rows = arr
        .map((r) => ({ r, slot: sd === 'B' ? r.p1.x : r.p1.x + STUB }))
        .sort((a, b) => a.slot - b.slot)
      // 目标口统一重定向：B 走向从母线带垂直投影进目标图形顶(T)。
      // 全部源（含支线）统一到同一目标口 —— 三条支线在「母线带 → 目标」段完全共线，
      // 视觉上合并为一根总管，且**每条 conn 的路径都真实抵达目标设备**（热风炉1/2/3 三条线都连到高炉）。
      if (sd === 'B') {
        const gcx = (gx0 + gx1) / 2
        const tx = Math.min(Math.max(gcx, frt.x + 8), frt.x + frt.w - 8)
        for (const r of arr) r.p2 = { side: 'T', x: tx, y: frt.y }
      }
      busData.set(arr[0].c.to + '|' + arr[0].c.toPort, { rows, yBus })
      // 母线组端口错开清零（共用单端口,不再 ±14 错开生成多个 stub）
      for (const x of arr) delete dstOff[x.c.id]
    }
  }
  // 同目标「同缘列」(to+side+x 相同)的多条入线：进入端口的竖列与上方走廊需错开分道，
  // 否则多条线会共用同一竖列/同一走廊高度 → SVG 完全共线（后画的盖住先画的）。
  // colIdx 给每条冲突线一个组内序号，走廊/兜底分支按序号左移竖列、抬高走廊。
  const colIdx = new Map()
  {
    const m = {}
    for (const r of list) {
      const k = r.t.id + '|' + r.p2.side + '|' + Math.round(r.p2.x)
      if (r.p2.side !== 'L') continue
      ;(m[k] = m[k] || []).push(r)
    }
    for (const arr of Object.values(m)) if (arr.length > 1) arr.forEach((r, i) => { colIdx.set(r.c.id, i) })
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
    // 同目标同侧多线（colIdx>0）：各线走独立「入口接近列」，避免共用同一竖列而完全共线。
    // L 入口列在盒左退回 colK*LINE_STEP、R 入口在盒右推进 colK*LINE_STEP；单线退化为 stub 点。
    const colK = colIdx.get(c.id)
    const colP = colK === undefined ? p2s
      : { x: s2 === 'L' ? p2a.x - STUB - colK * LINE_STEP
          : s2 === 'R' ? p2a.x + STUB + colK * LINE_STEP : p2a.x, y: p2a.y }
    // 0) 共享目标端口的「母线汇流」：全部源同路径 —— 源底竖下 STUB 到母线带 →
    //    沿带横移到目标口正上方 → 竖落 STUB 进目标图形顶。
    //    支线与干线走同一条折线（在「母线带 → 目标」段完全共线，视觉合并为一根总管），
    //    因此三条热风炉连线的箭头轨迹都完整抵达高炉；每条线各带一个箭头（组内相位均分防追尾）。
    const busKey = c.to + '|' + c.toPort
    if (busData.has(busKey)) {
      const bus = busData.get(busKey)
      const idx = bus.rows.findIndex((row) => row.r.c.id === c.id)
      if (idx >= 0) {
        const seg = _dedupe([p1a, p1s, { x: p1s.x, y: bus.yBus }, { x: p2s.x, y: bus.yBus }, p2s, p2a])
        if (seg.length >= 2 && !_hasCross(seg, obs)) pts = seg
      }
    }
    // 0.5) 回流弧（feedback 虚线）：仅「真右→左跨厂回流」才优先走整图底缘下方车道
    //   —— 短距回供(如 焦炉→烧结 的焦粉回供)直接走直连短竖线，不绕场。
    if (!pts && c.feedback && f.x > t.x + FWD_TOL) {
      const under = []
      for (let k = 0; k < 3; k++) {
        const cy = mainBot + 10 + k * LANE_STEP
        const seg = _dedupe([p1a, p1s, { x: p1s.x, y: cy }, { x: p2s.x, y: cy }, p2s, p2a])
        if (seg.length >= 2 && !_hasCross(seg, obs)) under.push(seg)
      }
      if (under.length) pts = under.sort((a, b) => _pathLen(a) - _pathLen(b))[0]
    }
    // 1) 直连：横向到「入口接近列」再沿列直落入口高度、横插进盒(同侧多线各自错列，互不共线)
    if (!pts) {
      const flat = colK === undefined
        ? _dedupe([p1a, p1s, { x: p2s.x, y: p1s.y }, p2s, p2a])
        : _dedupe([p1a, p1s, { x: colP.x, y: p1s.y }, { x: colP.x, y: p2a.y }, p2s, p2a])
      if (flat.length >= 2 && !_hasCross(flat, obs)) pts = flat
    }
    if (!pts) {
      // 2) 候选走廊枚举：横移带 cy × 竖列 bx 的网格组合，取不穿盒的最短折线
      //    —— 同缘列多线(组内序号 colK>0)：竖列左移 colK*14、走廊最低通道抬高 colK 档，
      //       使烧结/球团等长走廊入线不在同一 y 水平带、同一竖列上重叠。
      const p2c = colP // 与直连同一条「入口接近列」
      const cySet = new Set([
        p1s.y, p2c.y,
        mainTop - UPPER_GAP,
        mainTop - UPPER_GAP - LINE_STEP,
        mainTop - UPPER_GAP - LINE_STEP * 2,
        mainBot + 24,
        mainBot + 24 + LANE_STEP,
        mainBot + 24 + LANE_STEP * 2,
      ])
      if (colK) { for (let j = 0; j < colK; j++) cySet.delete(mainTop - UPPER_GAP - j * LINE_STEP) }
      const bxSet = new Set([
        p1s.x,
        f.x + boxW(f) + 16,
        mainBand.value.r + 14,
        mainBand.value.l - 14,
        t.x - 14,
        t.x + boxW(t) + 14,
      ])
      const cand = []
      for (const bx of bxSet) {
        for (const cy of cySet) {
          const seg = _dedupe([p1a, p1s, { x: bx, y: p1s.y }, { x: bx, y: cy }, { x: p2c.x, y: cy }, p2c, p2a])
          if (seg.length >= 2 && !_hasCross(seg, obs)) cand.push(seg)
        }
      }
      // 4) 兜底：主带顶大走廊（多通道错开），仍无则取穿盒最少者
      if (!cand.length) {
        for (let k = 0; k < 6; k++) {
          const cy = mainTop - 24 - k * LINE_STEP
          const seg = _dedupe([p1a, p1s, { x: p1s.x, y: p1s.y }, { x: p1s.x, y: cy }, { x: p2c.x, y: cy }, p2c, p2a])
          if (seg.length >= 2 && !_hasCross(seg, obs)) { cand.push(seg); break }
        }
      }
      if (!cand.length) {
        const outer = [
          _dedupe([p1a, p1s, { x: mainBand.value.r + 20, y: p1s.y }, { x: mainBand.value.r + 20, y: mainTop - 24 }, { x: p2c.x, y: mainTop - 24 }, p2c, p2a]),
          _dedupe([p1a, p1s, { x: mainBand.value.r + 20, y: p1s.y }, { x: mainBand.value.r + 20, y: mainBot + 24 }, { x: p2c.x, y: mainBot + 24 }, p2c, p2a]),
        ]
        pts = outer.sort((a, b) => _crossCount(a, obs) - _crossCount(b, obs) || _pathLen(a) - _pathLen(b))[0]
      } else {
        pts = cand.sort((a, b) => _pathLen(a) - _pathLen(b))[0]
      }
    }
    path.set(c.id, pts)
  }
  // 母线组：同目标端口多源汇流的全部 conn（含支线与干线）→ connId 映射到组 key。
  // busBranch = 组内非干线的那些（idx < last），仅作标记（审计/识别用）。
  // 三条 conn 路径均抵达目标，因此**每条都承载自己的流向箭头**（表示每台源设备都在输出），
  // 组内由 lines computed 统一周期 + 相位均分，使共线段上的多个箭头保持稳定间距不追尾。
  const busBranch = new Set()
  const busGroup = new Map()
  for (const [key, bus] of busData.entries()) {
    const rows = bus.rows
    for (const row of rows) busGroup.set(row.r.c.id, key)
    for (let i = 0; i < rows.length - 1; i++) busBranch.add(rows[i].r.c.id)
  }
  return { list, srcSt, dstOff, path, busBranch, busGroup }
}
function applyOff(p, side, off) {
  if (!off) return p
  if (side === 'L' || side === 'R') return { x: p.x, y: p.y + off, side: p.side }
  if (side === 'T' || side === 'B') return { x: p.x + off, y: p.y, side: p.side }
  return p
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
  // onH：锚点确实落在水平段上（false = 全竖直管道，锚点退化为两端点中点）。
  // 物料卡片据此选择排布轴：水平管道 → 卡片上下并排；竖直管道 → 卡片左右并排。
  return { d, mx, my: my - 4, onH: best > 0, p1: pts[0], p2: pts[pts.length - 1], pts }
}
// 流向箭头线速度（图形坐标 px/s）：调小 = 箭头更舒缓、调大 = 更急促。
// 全图箭头速度只由此常量控制（每帧位移 = 速度 × 时间，与线长解耦）。
const FLOW_SPEED = 130
const FLOW_DUR_MIN = 1.6
const FLOW_DUR_MAX = 8

// —— 管道形态参数（图形坐标 px）——
// 连线不再是单根细线，而是「管壁 + 管体 + 高光」三层同路径描边叠出的管道。
// 调管道粗细只改 PIPE_W（虚线回流管 PIPE_W_FB）；调轮廓厚度只改 PIPE_EDGE_ADD。
const PIPE_W = 7            // 管道主体（管体）宽度
const PIPE_W_FB = 4.5       // 回流虚线管主体宽度（比正流细，语义弱化）
const PIPE_EDGE_ADD = 1.8   // 管壁比管体每侧宽出 0.9px → 细深色轮廓，不压管体
const PIPE_HI_RATIO = 0.42  // 高光宽度 = 管体 × 0.42（居中细白线，圆柱反光）
const PIPE_EDGE_COLOR = '#202a34'

// —— 流向箭头参数（图形坐标 px）——
// 箭头色 = **管道物料色加深**（不是白色）：管体是物料色，箭头取同色系压暗一档，
// 靠「深色实心块 + 更深描边」从管体上脱开，既不破坏管道的物料色语义，也不会白得扎眼。
// 调深浅只改 FLOW_DARKEN / FLOW_DARKEN_EDGE（越小越深）；调大小只改 FLOW_PTS / FLOW_PTS_FB。
const FLOW_DARKEN = 0.68        // 箭头填充 = 物料色 × 0.68（比管体深约 32%）
const FLOW_DARKEN_EDGE = 0.44   // 箭头描边 = 物料色 × 0.44（同色系更深轮廓，勾出箭头形状）
const FLOW_STROKE_W = 1.2
const FLOW_PTS = '-9,-5.6 9,0 -9,5.6'      // 正流箭头（宽 18 / 高 11.2，略凸出管壁）
const FLOW_PTS_FB = '-7.5,-4.6 7.5,0 -7.5,4.6' // 回流虚线管箭头（比正流略小，语义弱化）
const lines = computed(() => {
  // **只算几何**（折线路由 / 管径 / 箭头节奏），不含任何实时读数 —— 材料流动速率见 rates。
  // 为什么必须拆开：实时遥测（WebSocket /api/ws/feed）每几秒推送一次，而 lines 一旦依赖它，
  // 每次推送都会连带重算全部折线路由、并让 40 条管线的三层描边与 SMIL 动画元素进入 diff，
  // 表现为「每隔几秒卡一下」。拆开后推送只会更新卡片里的速率文本。
  const routes = _lineRoutes()
  const out = []
  const byIdNode = new Map(nodes.value.map((n) => [n.id, n]))
  for (const c of conns.value) {
    const g = lineOf(c, routes)
    if (!g) continue
    // 流向箭头运动时长按折线实际长度归一（FLOW_SPEED px/s）：短线快速掠过、长管线匀速缓行，
    // 避免「同一时长」下长线箭头飞奔、短线箭头爬行。相位按序错开，防止全图箭头同时到达终点。
    let len = 0
    for (let i = 1; i < g.pts.length; i++) {
      len += Math.abs(g.pts[i].x - g.pts[i - 1].x) + Math.abs(g.pts[i].y - g.pts[i - 1].y)
    }
    const dur = Math.min(FLOW_DUR_MAX, Math.max(FLOW_DUR_MIN, len / FLOW_SPEED))
    const fb = !!c.feedback
    const pipeW = fb ? PIPE_W_FB : PIPE_W
    // 稳定标识（源类型>目标类型:物料）—— 卡片手工落位表 CARD_PIN 按此键匹配，
    // 不能用连线 id（每次载入模板都是新生成的 uid）。
    const aN = byIdNode.get(c.from), bN = byIdNode.get(c.to)
    out.push({
      id: c.id,
      key: `${aN ? aN.repType || aN.type : '?'}>${bN ? bN.repType || bN.type : '?'}:${c.material}`,
      d: g.d, mx: g.mx, my: g.my, onH: g.onH,
      pipeW,
      pipeEdgeW: pipeW + PIPE_EDGE_ADD,
      pipeHiW: Math.max(1, pipeW * PIPE_HI_RATIO),
      pipeEdgeOp: fb ? 0.65 : 0.7,
      pipeHiOp: fb ? 0.25 : 0.42,
      dash: fb ? '6 5' : '0',
      feedback: fb,
      color: fb ? '#8a97a5' : portColor(c.material),
      // 箭头色：物料色加深两档（填充 / 轮廓），与管体同色系但更沉，避免白色箭头抢眼。
      arrowFill: shade(fb ? '#8a97a5' : portColor(c.material), FLOW_DARKEN),
      arrowEdge: shade(fb ? '#8a97a5' : portColor(c.material), FLOW_DARKEN_EDGE),
      matName: matName(c.material),
      isBusBranch: routes.busBranch ? routes.busBranch.has(c.id) : false,
      busKey: routes.busGroup ? (routes.busGroup.get(c.id) || null) : null,
      dur: `${dur.toFixed(2)}s`,
      begin: `-${((out.length * 0.53) % dur).toFixed(2)}s`,
    })
  }
  // 母线组（同目标端口多源汇流）内统一节奏：取组内最长周期为共同周期，相位按组内序号均分。
  // 这样三台热风炉各有一个箭头从自己炉底出发 → 沿母线带 → 汇入同一根总管进高炉，
  // 且彼此保持恒定间距依次推进（不会因各线速度不同而追尾重叠成一个箭头）。
  const grp = new Map()
  for (const l of out) {
    if (!l.busKey) continue
    if (!grp.has(l.busKey)) grp.set(l.busKey, [])
    grp.get(l.busKey).push(l)
  }
  for (const arr of grp.values()) {
    const dur = Math.max(...arr.map((l) => parseFloat(l.dur)))
    arr.forEach((l, i) => {
      l.dur = `${dur.toFixed(2)}s`
      l.begin = `-${((i * dur) / arr.length).toFixed(2)}s`
    })
  }
  return out
})

// —— 材料流动速率（与管线几何解耦，随实时读数变化）——
// 按「材料 → 计量点」规则从后端下发的读数解析（见 utils/pipeRate.js）：
//   ① 实时遥测 store.deviceLive（WebSocket /api/ws/feed 推送的现场设备读数）
//   ② 未关联/未上报时回退 baseline 里后端算出的仿真读数
//   ③ 工辅介质（鼓风/热风/供氧/抽力/喷煤）取该工辅的运行工况参数
// upstream 用于「预处理铁水」这类无独立计量设备的管道反向复用上游铁水计量。
// 返回 Map<connId, rate>；无计量点的管道不在表里（卡片只显示材料名）。
const rates = computed(() => {
  const m = new Map()
  const byIdNode = new Map(nodes.value.map((n) => [n.id, n]))
  const baseById = new Map(((store.baseline && store.baseline.units) || []).map((u) => [u.id, u]))
  const devsOfUnit = new Map()
  for (const d of store.allDevices) {
    if (!devsOfUnit.has(d.unitId)) devsOfUnit.set(d.unitId, [])
    devsOfUnit.get(d.unitId).push(d)
  }
  const rateCtxOf = (conn, seen) => ({
    unit: (id) => byIdNode.get(id) || null,
    devices: (id) => devsOfUnit.get(id) || [],
    live: (devId) => (store.deviceLive[devId] != null ? store.deviceLive[devId] : null),
    // 上游工序主产物产量（后端 UnitResult.steel_output，t/h），作为无计量点管道的兜底口径
    out: (id) => { const u = baseById.get(id); return u ? u.steel_output : null },
    upstream: (mats) => {
      const up = conns.value.find((x) => x.to === conn.from && mats.includes(x.material) && !seen.has(x.id))
      if (!up) return null
      seen.add(up.id)
      return resolvePipeRate(up, rateCtxOf(up, seen))
    },
  })
  for (const c of conns.value) {
    const r = resolvePipeRate(c, rateCtxOf(c, new Set([c.id])))
    if (r) m.set(c.id, r)
  }
  return m
})

// —— 管道旁的「物料卡片」：材料名 + 流动速率 ——
// 用户要求：材料信息不再贴着管道书写，改为在管道旁边立一张独立小卡片。
// 锚点取管道最长水平段的中点（与 lineOf 的标签锚点同一处），默认贴在管道上方、与管壁留间隙；
// 该位置若被设备盒或已放置的卡片占用，依次尝试 下方 → 更上方 → 更下方，保证卡片
// 既不压管道、也不压设备、彼此不叠。
const CARD_PAD_X = 8      // 卡片内左右留白
const CARD_PAD_Y = 5      // 卡片内上下留白
const CARD_LINE_H = 13    // 卡片内行高（材料名行 / 速率行）
const CARD_GAP = 6        // 卡片边缘与管壁外缘的间隙
const CARD_SHIFT = 24     // 上下方都被占用时，向更外侧再让出的距离
const CARD_SCAN = 8       // 兜底避让的扫描步长
const CARD_SCAN_MAX = 480 // 兜底避让的扫描范围（需大于一台设备盒宽，才能横越到设备外侧）
const CARD_SIDE_MIN = 64  // 竖直线卡片开始横向绕开相邻设备的阈值（小于此值只沿管道方向让位）
// 速率数值配色：实时遥测读数用深色（可信度最高），仿真/工况回退值用灰色弱化。
const CARD_VAL_LIVE = '#2b3a4a'
const CARD_VAL_SIM = '#96a1ad'
// 文字宽度估算：SVG 无自动排版，中文按 1em、西文数字按 0.56em 估算，用于定卡片宽度。
function estTextW(s, fs) {
  let w = 0
  for (const ch of String(s)) w += /[\u2e80-\u9fff\uff00-\uffef\u3000-\u303f]/.test(ch) ? fs : fs * 0.56
  return w
}

// —— 卡片手工落位表（用户逐条指定）——
// 键 = `${源type}>${目标type}:${material}`，与 lines 输出的 key 一致。
//   side：卡片相对管道的方位（right/left/above/below），按管壁外缘 + CARD_GAP 贴管；
//   dx/dy：在基准位上的微调（用于避开设备名称浮签这类细碎障碍）。
// 被指定的卡片改用「图形边界」(figRect) 参与避让 —— 设备节点盒含名称带、KPI 带与大量
// 左右留白，若仍按节点盒避让，卡片根本落不进「管道贴身处」这条窄缝，会被逼到很远处。
const CARD_PIN = {
  // 热风卡片：热风炉→高炉 的竖直短管右侧。x 右移 5px：热风炉图形下缘(513)与高炉名称浮签
  // 上缘(555)之间只有 42px，卡片高 36px 两头都贴死；让到名称右侧后可用带扩到 60px。
  'hot_blast_stove>blast_furnace:hot_blast': { side: 'right', dx: 5 },
  // 抽力卡片：引风机→烧结机 的水平短管上方（落在引风机与烧结机图形之间的空档）
  'id_fan>sinter_plant:draft': { side: 'above' },
  // 焦炭卡片：焦炉→烧结机 的回流虚线管右侧（贴管）。dx 右移 20px：烧结机换图后
  // 名称浮签（x 390~431）正好压在该管右侧的贴身位上，右移后落在名称右侧留白带。
  'coke_oven>sinter_plant:coke': { side: 'right', dx: 20 },
}
// 手工落位求值：先试基准位，再沿管道方向逐级外移让开设备（保持「贴管」的观感）。
// valid(rect) 由调用方注入（判定该矩形是否可用），返回矩形或 null（落不下则回落通用避让）。
function pinRectOf(l, w, h, valid) {
  const pin = CARD_PIN[l.key]
  if (!pin) return null
  const ay = l.my + 4                                  // 管道锚点真实 y（lineOf 内已上移 4px）
  const half = l.pipeEdgeW / 2 + CARD_GAP
  const base = {
    right: [l.mx + half, ay - h / 2],
    left: [l.mx - half - w, ay - h / 2],
    above: [l.mx - w / 2, ay - half - h],
    below: [l.mx - w / 2, ay + half],
  }[pin.side]
  if (!base) return null
  const bx = base[0] + (pin.dx || 0), by = base[1] + (pin.dy || 0)
  const at = (x, y) => { const t = { x: Math.round(x), y: Math.round(y), w, h }; return valid(t) ? t : null }
  const t0 = at(bx, by)
  if (t0) return t0
  // 让位轴 = 管道走向：水平管道左右滑动、竖直管道上下滑动
  const slideY = pin.side === 'right' || pin.side === 'left'
  for (let d = CARD_SCAN; d <= CARD_SCAN_MAX; d += CARD_SCAN) {
    const a = at(bx, by - d)
    if (a) return a
    const b = slideY ? at(bx, by + d) : at(bx + d, by)
    if (b) return b
  }
  return null
}
// 卡片尺寸：宽度取「材料名」与「速率文本预留宽」的较大者 —— **不随速率变化**。
// 否则实时读数每次刷新都会改变卡片宽度 → 触发下面那套 O(n²) 避让布局重算（每几秒一次全图重排）。
// 尺寸统一后卡片也更整齐。
const CARD_RATE_W = 62        // 速率行预留宽（够放 "1,234.5 t/h"）
const cardLayout = computed(() => {
  // 避让对象取「节点盒」而非设备图形外接盒：卡片带白底，若压在设备名浮签或底部 KPI 带上
  // 会遮住文字，故按整个节点占位（含名称带与 KPI 带）避让。
  const boxes = nodes.value.map((n) => ({ x: n.x, y: n.y, w: boxW(n), h: boxH(n) }))
  const figs = nodes.value.map((n) => figRect(n))
  const bd = bounds.value
  const hitBox = (r) => boxes.some((b) => r.x < b.x + b.w + 4 && r.x + r.w + 4 > b.x && r.y < b.y + b.h + 4 && r.y + r.h + 4 > b.y)
  // 图形边界（裁除透明留白后的图形外接盒，不含名称带/KPI 带）—— 仅供 CARD_PIN 指定的卡片使用。
  const hitFig = (r) => figs.some((b) => r.x < b.x + b.w + 2 && r.x + r.w + 2 > b.x && r.y < b.y + b.h + 2 && r.y + r.h + 2 > b.y)
  const oob = (r) => r.x < bd.x || r.y < bd.y || r.x + r.w > bd.x + bd.w || r.y + r.h > bd.y + bd.h
  const occupied = []
  const hitCard = (r) => occupied.some((o) => r.x < o.x + o.w + 3 && r.x + r.w + 3 > o.x && r.y < o.y + o.h + 3 && r.y + r.h + 3 > o.y)
  // 管线占位：只避让设备与其他卡片时，卡片会被塞到别的管线上遮住流向（如「鼓风(风量)」
  // 曾压住 供氧系统→鼓风机 的氧气线）。这里把全部管道的正交段按管壁半宽膨胀成矩形，
  // 卡片不得与之相交 —— 贴身位本身留了 CARD_GAP 间隙，故靠近自己的管道不会被误判。
  // 按线 id 分组存放：手工落位的卡片要豁免「自己那条管道」，否则贴管位恒被判冲突。
  const pipeSegs = new Map()
  for (const l of lines.value) {
    const nums = String(l.d).match(/-?\d+(?:\.\d+)?/g) || []
    const pts = []
    for (let i = 0; i + 1 < nums.length; i += 2) pts.push([+nums[i], +nums[i + 1]])
    const pad = l.pipeEdgeW / 2
    const arr = []
    for (let i = 1; i < pts.length; i++) {
      arr.push({
        x1: Math.min(pts[i - 1][0], pts[i][0]), x2: Math.max(pts[i - 1][0], pts[i][0]),
        y1: Math.min(pts[i - 1][1], pts[i][1]), y2: Math.max(pts[i - 1][1], pts[i][1]), pad,
      })
    }
    pipeSegs.set(l.id, arr)
  }
  const hitPipe = (r, skipId) => {
    for (const [id, segs] of pipeSegs) {
      if (id === skipId) continue
      for (const s of segs) {
        if (r.x - s.pad < s.x2 && r.x + r.w + s.pad > s.x1 && r.y - s.pad < s.y2 && r.y + r.h + s.pad > s.y1) return true
      }
    }
    return false
  }
  const hit = (r, skipId) => hitBox(r) || oob(r) || hitCard(r) || hitPipe(r, skipId)
  const out = []
  for (const l of lines.value) {
    const w = Math.round(Math.max(estTextW(l.matName, 11), CARD_RATE_W) + CARD_PAD_X * 2 + 2)
    const h = Math.round(CARD_PAD_Y * 2 + CARD_LINE_H * 2)
    const lineY = l.my + 4                    // 水平段真实 y（lineOf 内标签锚点已上移 4px）
    const half = l.pipeEdgeW / 2 + CARD_GAP   // 卡片近管侧与管道中心线的距离
    // ① 手工落位（CARD_PIN）：按用户指定方位贴管放置，只避让「图形边界 + 已放卡片 + 其他管线」。
    let r = pinRectOf(l, w, h, (t) => !hitFig(t) && !oob(t) && !hitCard(t) && !hitPipe(t, l.id))
    // ② 贴身位：按锚点所在段的走向给出，水平管道优先上下并排、竖直管道优先左右并排，
    //    再依次退到另一轴与更外侧。
    const near = l.onH
      ? [[l.mx - w / 2, lineY - half - h], [l.mx - w / 2, lineY + half],
         [l.mx + half, l.my - h / 2], [l.mx - half - w, l.my - h / 2],
         [l.mx - w / 2, lineY - half - h - CARD_SHIFT], [l.mx - w / 2, lineY + half + CARD_SHIFT]]
      : [[l.mx + half, l.my - h / 2], [l.mx - half - w, l.my - h / 2],
         [l.mx - w / 2, lineY - half - h], [l.mx - w / 2, lineY + half],
         [l.mx + half + CARD_SHIFT, l.my - h / 2], [l.mx - half - w - CARD_SHIFT, l.my - h / 2]]
    if (!r) {
      for (const [x, y] of near) {
        const t = { x: Math.round(x), y: Math.round(y), w, h }
        if (!hit(t)) { r = t; break }
      }
    }
    // ③ 兜底扫描：工辅通道里相邻设备的缝隙可能比卡片还窄（如「引风机→烧结机」仅 46px），
    //    贴身位会被设备全占。此时优先沿管道方向让位（卡片仍在管道旁、顺着管道滑动，观感贴合），
    //    横向绕开相邻设备只作为最后手段（走远了卡片会与管道脱节，故设阈值后才启用）。
    for (let d = CARD_SCAN; !r && d <= CARD_SCAN_MAX; d += CARD_SCAN) {
      const cand = l.onH
        ? [[l.mx - w / 2, lineY - half - h - d], [l.mx - w / 2, lineY + half + d],
           [l.mx - w / 2 - d, lineY - half - h], [l.mx - w / 2 + d, lineY - half - h],
           [l.mx - w / 2 - d, lineY + half], [l.mx - w / 2 + d, lineY + half]]
        : [[l.mx + half, l.my - h / 2 - d], [l.mx + half, l.my - h / 2 + d],
           [l.mx - half - w, l.my - h / 2 - d], [l.mx - half - w, l.my - h / 2 + d]]
      if (!l.onH && d > CARD_SIDE_MIN) {
        const dx = d - CARD_SIDE_MIN
        cand.push([l.mx + half + dx, l.my - h / 2], [l.mx - half - w - dx, l.my - h / 2])
      }
      for (const [x, y] of cand) {
        const t = { x: Math.round(x), y: Math.round(y), w, h }
        if (!hit(t)) { r = t; break }
      }
    }
    if (!r) { const [x, y] = near[0]; r = { x: Math.round(x), y: Math.round(y), w, h } }   // 四周都挤：仍贴管道，保证不丢信息
    occupied.push(r)
    out.push({ id: l.id, x: r.x, y: r.y, w, h, matName: l.matName, color: l.color })
  }
  return out
})
// 速率单独附加：layout 走缓存，只有 rate 字段随实时读数变化（渲染时仅更新卡片里的两行文本）
const cards = computed(() => cardLayout.value.map((c) => ({ ...c, rate: rates.value.get(c.id) || null })))

// 交互：缩放 / 平移 / 选中
// 视图状态（zoom/pan）**故意不用 ref**：它们每帧都在变，若做成响应式会触发整棵 SVG 的
// vdom 重算。这里用普通变量 + applyView() 直接写 <svg> 的 CSS transform。
// 注意视口基准一律取外层 .t2d-canvas（ref="wrap"）的 rect —— svg 自身被 transform 后
// 它的 getBoundingClientRect 会跟着变，用它算鼠标世界坐标会「越缩越飘」。
let view = { z: 1, x: 0, y: 0 }
const hovered = ref(null)
const dragging = ref(false)
const last = { x: 0, y: 0 }
const cursor = computed(() => (dragging.value ? 'grabbing' : 'grab'))

/** 把当前 zoom/pan 写到 <svg> 的 CSS transform（唯一的视图更新出口）。
 *  用 CSS transform 而非 SVG transform 属性：前者可被浏览器提升为合成层，
 *  拖拽时只做层合成、不重绘内容，实测帧时间明显更低。 */
function applyView() {
  if (!svg.value) return
  const s = svg.value
  if (s.style.transform !== `translate(${view.x}px, ${view.y}px) scale(${view.z})`) {
    s.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.z})`
  }
}

// —— 管线流向动画的暂停/恢复 ——
// 每条管线都有一个常驻 SMIL 动画（animateMotion + opacity），箭头每帧移动都会触发
// 重绘；拖拽/缩放时它与平移重绘叠加，帧率骤降。交互期间直接暂停整个 SVG 的 SMIL 时钟
// （pauseAnimations），停手后再恢复 —— 时间线是暂停而非重置，箭头从原处继续，不会跳。
// 同时把设备投影也临时关掉（走 CSS class，避免触发 Vue 重渲染）：平移/缩放时整幅图每帧重绘，
// 哪怕只剩「每台设备一次」的滤镜，栅格化成本依然可观；交互时去掉、停手恢复，肉眼几乎无感。
let animResumeTimer = null
function pauseFlow() {
  if (animResumeTimer) { clearTimeout(animResumeTimer); animResumeTimer = null }
  if (!svg.value) return
  svg.value.classList.add('dragging')
  if (svg.value.pauseAnimations) svg.value.pauseAnimations()
}
function resumeFlow(delay = 260) {
  if (animResumeTimer) clearTimeout(animResumeTimer)
  animResumeTimer = setTimeout(() => {
    animResumeTimer = null
    if (!svg.value) return
    svg.value.classList.remove('dragging')
    if (svg.value.unpauseAnimations) svg.value.unpauseAnimations()
  }, delay)
}

function fitAll() {
  if (!wrap.value || !nodes.value.length) { view = { z: 1, x: 0, y: 0 }; applyView(); return }
  const rect = wrap.value.getBoundingClientRect()
  // 矩形化：zoom 同时受整体 bounds 宽高约束（取 min），让矩形画布完整适配视口；
  // 兜底下调到 0.28，避免矩形化后宽高变大被人为压缩。
  const bw = bounds.value.w, bh = bounds.value.h
  const z = Math.min((rect.width * 0.92) / bw, (rect.height * 0.92) / bh)
  const nz = Math.max(0.28, Math.min(1.1, z))
  // 让矩形画布在视口居中：屏中心 = pan + 世界中心 × z → pan = 屏中心 - 世界中心 × z
  const centerX = bounds.value.x + bw / 2
  const centerY = bounds.value.y + bh / 2
  view = { z: nz, x: rect.width / 2 - centerX * nz, y: rect.height / 2 - centerY * nz }
  applyView()
}
function onWheel(e) {
  if (!wrap.value) return
  const rect = wrap.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  // 屏幕 → 世界：screen = pan + world × z（变换是 translate 后 scale，pan 单位为屏幕像素），
  // 故 world = (screen - pan) / z。原实现写成 mx / z - pan，与 fitAll 用的语义不一致，
  // 结果是**缩放锚点漂移**（鼠标下的设备会跑开），这里一并修正。
  const worldX = (mx - view.x) / view.z
  const worldY = (my - view.y) / view.z
  const f = e.deltaY < 0 ? 1.12 : 0.88
  const nz = Math.min(3.2, Math.max(0.25, view.z * f))
  // 反解 pan，使同一世界点在缩放后仍落在鼠标处：pan' = mx - world × nz
  view = { z: nz, x: mx - worldX * nz, y: my - worldY * nz }
  applyView()
  pauseFlow()          // 连续滚动期间保持暂停，停手 260ms 后自动恢复
  resumeFlow()
}
function onDown(e) {
  if (e.button !== 0) return
  dragging.value = true
  last.x = e.clientX
  last.y = e.clientY
  pauseFlow()
}
function onMove(e) {
  if (!dragging.value || !svg.value) return
  view = { z: view.z, x: view.x + (e.clientX - last.x) / view.z, y: view.y + (e.clientY - last.y) / view.z }
  last.x = e.clientX
  last.y = e.clientY
  applyView()
}
function onUp() {
  if (!dragging.value) return
  dragging.value = false
  resumeFlow(120)
}

function onNode(n) {
  if (n.kind === 'device') return
  store.pickUnit(n.id)
}

function fmt(n) {
  if (n == null || Number.isNaN(n)) return '—'
  return Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}
let ro = null
let fitTimer = null
let fitted = false
let frozen = false

/** 面板开合动画结束后的容器尺寸：.app 的 grid 正在插值，但**目标列宽/行高**已写在
 *  --lw / --rw / --cmd-h 里（App.vue 的 inline style 是瞬时切换的），二者相减即得增量。
 *  拿不到（全屏态等列数变化）时返回 null，调用方退化为「不冻结」。 */
function targetCanvasSize() {
  const app = document.querySelector('.app')
  if (!app) return null
  const cs = getComputedStyle(app)
  const cols = (cs.gridTemplateColumns || '').split(/\s+/).map(parseFloat)
  const rows = (cs.gridTemplateRows || '').split(/\s+/).map(parseFloat)
  const num = (k) => { const v = parseFloat(cs.getPropertyValue(k)); return Number.isFinite(v) ? v : null }
  const tl = num('--lw'), tr = num('--rw'), tc = num('--cmd-h')
  if (cols.length < 3 || rows.length < 4 || tl == null || tr == null || tc == null) return null
  const w = cols[2] + (cols[1] - tl) + (cols[3] - tr)
  const h = rows[2] + (rows[3] - tc)
  return w > 0 && h > 0 ? { w, h } : null
}

/** 冻结 SVG 元素尺寸。
 *  关键：svg 是「每帧重栅格」的大图层（数千个矢量元素），容器宽度一变它就要整体重画 ——
 *  这才是开合侧栏掉帧的主因（fitAll/transform 本身很便宜）。这里把它固定到
 *  max(当前, 动画结束后的最终) 尺寸：图层大小全程不变 → 不重栅格；画面缩放仍由 fitAll
 *  每帧按**容器**尺寸改 CSS transform（合成层变换，不引发重绘），观感与原先一致。
 *  取 max 是为了保证内容永远画在 svg 盒子内（svg 根元素默认裁剪溢出内容）。 */
function freezeCanvas() {
  if (!svg.value || !wrap.value) return
  const t = targetCanvasSize()
  const r = wrap.value.getBoundingClientRect()
  const w = Math.ceil(Math.max(r.width, t ? t.w : r.width))
  const h = Math.ceil(Math.max(r.height, t ? t.h : r.height))
  svg.value.style.width = w + 'px'
  svg.value.style.height = h + 'px'
}
function unfreezeCanvas() {
  if (!svg.value) return
  svg.value.style.width = ''
  svg.value.style.height = ''
}

// 容器尺寸变化：默认立即重新适配视图。
// **面板开合动画期间**（body.panel-animating，见 App.vue）容器宽度每帧都在变：
//   ① 冻结 SVG 图层尺寸，避免整幅矢量图每帧重栅格；
//   ② 暂停流向动画（SMIL），避免与上面的重绘叠加；
//   ③ 动画结束后解冻 + 补一次 fitAll 精确适配 + 恢复流向动画。
function onCanvasResize() {
  if (!fitted) { fitted = true; fitAll(); return }   // 首次进入必须立即适配（可能正处在收起侧栏的动画里）
  if (document.body.classList.contains('panel-animating')) {
    if (!frozen) { frozen = true; freezeCanvas() }
    pauseFlow()
    fitAll()                                          // 按容器当前尺寸平滑缩放（只改 transform）
    clearTimeout(fitTimer)
    fitTimer = setTimeout(() => {
      fitTimer = null
      frozen = false
      unfreezeCanvas()
      fitAll()
      resumeFlow(0)
    }, 300)
    return
  }
  fitAll()
}
onMounted(() => {
  // 2D 工艺流程图进入时收起左侧栏（资源/编排树），让 SVG 容器撑大、主设备屏幕占比↑。
  // 左侧资源菜单只在用户手动点击（活动栏 / 顶栏开关 / 系统设置）时展开：
  // 退出 2D 回到 3D 不再还原此前的展开态，避免「2D → 3D 自动弹出资源菜单」。
  store.leftOpen = false
  relayout()
  ro = new ResizeObserver(() => onCanvasResize())
  if (wrap.value) ro.observe(wrap.value)
})
onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  if (fitTimer) { clearTimeout(fitTimer); fitTimer = null }
})
// 视图 transform 现在由 JS 直接写 DOM（不经过 Vue），若世界节点因数据变化被重建，
// 属性会丢失 —— 每次更新后补写一次（一次 setAttribute，开销可忽略）。
onUpdated(applyView)
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
/* —— 适配按钮（画布右下角悬浮） —— */
.t2d-fit {
  position: absolute; right: 12px; bottom: 12px; z-index: 3;
  border: 1px solid #cdd5dd; background: #fff; color: #33475b;
  border-radius: 4px; font-size: 12px; padding: 4px 12px; cursor: pointer;
  box-shadow: 0 1px 4px rgba(20, 40, 60, 0.12);
}
.t2d-fit:hover { border-color: #2c6e9e; color: #2c6e9e; }
/* —— 画布 —— */
.t2d-canvas {
  position: relative; flex: 1; overflow: hidden;
  cursor: grab;
}
.t2d-canvas svg {
  width: 100%; height: 100%; display: block;
  /* 视图变换（拖拽/缩放）写在 <svg> 的 CSS transform 上，便于浏览器提升为合成层。
     transform-origin 必须是 0 0 —— 默认的 50% 50% 会让缩放围绕画布中心，与 JS 里
     按左上角计算的 pan 不一致，表现为「缩放时画面乱跑」。 */
  transform-origin: 0 0; will-change: transform;
}
/* 拖拽/缩放期间（svg 上临时挂 .dragging）关闭设备投影：平移时整幅图每帧重绘，
   滤镜是其中最贵的一环；交互结束自动恢复（见 pauseFlow/resumeFlow）。 */
.t2d-canvas.dragging :deep(.t2d-figsvg > g[filter]) { filter: none; }
.t2d-grid { opacity: 0.5; }
/* 管线 */
/* 管道三层描边（管壁 / 管体 / 高光）：同路径叠加，仅承担视觉层次，不参与交互 */
.t2d-pipe { pointer-events: none; }
/* 沿线运动的流向箭头（SMIL animateMotion 驱动，位置/朝向由路径决定，此处只管层次与点击穿透） */
.t2d-flow { pointer-events: none; }
.t2d-mid { pointer-events: none; }
/* 物料卡片：管道旁的独立小卡片（上行材料名、下行流动速率）。
   卡片底为白底 + 物料色细边，左侧色条与管道同色 —— 卡片与管道的从属关系一眼可辨。
   速率数值：实时读数深色、回退值浅灰（配色常量见 script 中的 CARD_VAL_*）。 */
.t2d-card { pointer-events: none; }
.t2d-card-bg { fill: #ffffff; fill-opacity: 0.93; stroke-width: 1.1; }
.t2d-card-mat { font-size: 11px; font-weight: 600; letter-spacing: 0.01em; }
.t2d-card-rate { font-variant-numeric: tabular-nums; }
.t2d-card-val { font-size: 12px; font-weight: 700; letter-spacing: 0.01em; }
.t2d-card-unit { font-size: 9.5px; font-weight: 400; }

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