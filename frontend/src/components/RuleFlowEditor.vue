<!-- ============ 规则控制 · 可编排视图 ============
     与「流程编排 FlowEditor」完全不同的语义：
       流程编排 = 物料流 / 工艺拓扑（节点=工艺·物料·设备，连线=物流）
       规则编排 = 控制逻辑（节点=可调/传感/IF，连线=执行顺序）
     三类模块用三种颜色区分：可调（可设定数值）· 传感（只读观测）· IF 条件（if/elif/else 分支）。
     拖拽左侧「可调设备 / 传感设备」到画布即建节点；IF 模块默认 if-else，可手动添加 elif。
     每个条件分支的输出端口可继续往下连接可调或传感节点并进行设置（只有可调可设定数值）。 -->
<template>
  <div class="rfe">
    <!-- ══════════ 工具条 ══════════ -->
    <div class="rfe-bar">
      <button class="rf-b pri" @click="addIf">{{ t('+ if 模块') }}</button>
      <button class="rf-b" @click="addDev('adj')" :disabled="!adjList.length">{{ t('+ 可调设备') }}</button>
      <button class="rf-b" @click="addDev('sen')" :disabled="!senList.length">{{ t('+ 传感设备') }}</button>
      <span class="rf-sep"></span>
      <button class="rf-b" title="Ctrl+Z" :disabled="!canUndo" @click="undo">{{ t('撤销') }}</button>
      <button class="rf-b" title="Ctrl+Shift+Z / Ctrl+Y" :disabled="!canRedo" @click="redo">{{ t('重做') }}</button>
      <button class="rf-b" title="Ctrl+C" :disabled="!selNode" @click="copySel">{{ t('复制') }}</button>
      <button class="rf-b" title="Ctrl+X" :disabled="!selNode" @click="cutSel">{{ t('剪切') }}</button>
      <button class="rf-b" title="Ctrl+V" :disabled="!clipboard" @click="paste">{{ t('粘贴') }}</button>
      <span class="rf-sp"></span>
      <span class="rf-lg"><i class="lg-d adj"></i>{{ t('可调') }}</span>
      <span class="rf-lg"><i class="lg-d sen"></i>{{ t('传感') }}</span>
      <span class="rf-lg"><i class="lg-d ifn"></i>{{ t('条件') }}</span>
      <span class="rf-sp"></span>
      <span class="rf-cnt mono">{{ nodes.length }} {{ t('模块') }} · {{ edges.length }} {{ t('连线') }}</span>
      <span class="rf-cnt mono">{{ t('本轮动作') }} {{ lastActs.length }}</span>
      <button class="rf-b" @click="fitView" :disabled="!nodes.length">{{ t('适应') }}</button>
      <button class="rf-b" @click="clearAll" :disabled="!nodes.length">{{ t('清空') }}</button>
      <button class="rf-b ghost" @click="showLog = !showLog">{{ t('日志') }}{{ log.length ? '(' + log.length + ')' : '' }}</button>
      <span class="rf-zoom mono">{{ Math.round(view.z * 100) }}%</span>
    </div>

    <!-- ══════════ 画布 ══════════ -->
    <div class="rfe-cv" ref="cvEl"
         @mousedown="onCvDown" @wheel.prevent="onWheel">
      <div class="rfe-vp" :style="vpStyle">
        <svg class="rfe-svg" :width="CV_W" :height="CV_H">
          <path v-for="e in edges" :key="'h' + e.id" class="rf-e-hit" :d="edgeD(e)" @mousedown.stop="selEdge = e.id" />
          <path v-for="e in edges" :key="e.id" class="rf-e"
                :class="{ on: e.id === selEdge, act: activeEdge.has(e.id) }" :d="edgeD(e)" />
          <path v-if="link" class="rf-e tmp" :d="tmpD" />
          <g v-if="selEdge && edgeMid" class="rf-eg" @mousedown.stop="delEdge(selEdge)">
            <circle class="rf-ebg" :cx="edgeMid.x" :cy="edgeMid.y" r="8" />
            <text class="rf-ex" :x="edgeMid.x" :y="edgeMid.y + 3.6">✕</text>
          </g>
        </svg>

        <!-- ─────── 可调 / 传感 节点 ─────── -->
        <div v-for="n in devNodes" :key="n.id" class="rf-node" :data-nid="n.id"
             :class="[n.kind, { sel: n.id === selNode, act: activeNode.has(n.id), miss: isMissing(n) }]"
             :style="nodeStyle(n)" @mousedown.stop="startMove(n, $event)">
          <span class="rf-pt in"></span>

          <div class="rf-hd" @mousedown.stop="startMove(n, $event)">
            <i class="rf-ic">{{ n.kind === 'adj' ? '⚙' : '◉' }}</i>
            <span class="rf-nm" :title="n.label">{{ n.label }}</span>
            <em class="rf-ut">{{ n.unitName }}</em>
            <button class="rf-x" :title="t('删除模块')" @mousedown.stop @click.stop="delNode(n)">✕</button>
          </div>

          <div class="rf-bd">
            <template v-if="n.kind === 'adj'">
              <em class="rf-lb">{{ t('设定值') }}</em>
              <input class="rf-num" type="number" v-model.number="n.value"
                     :min="spMin(n.devId)" :max="spMax(n.devId)" :step="spStep(n.devId)"
                     @mousedown.stop @focus="histBegin" @change="commitVal(n)" />
              <i class="rf-u">{{ n.unit }}</i>
            </template>
            <template v-else>
              <em class="rf-lb">{{ t('实时值') }}</em>
              <b class="rf-v mono">{{ fmt(liveOf(n.devId)) }}</b>
              <i class="rf-u">{{ n.unit }}</i>
            </template>
          </div>
          <div class="rf-ft">
            <span v-if="n.kind === 'adj'" class="rf-hint mono">{{ t('量程') }} {{ fmt(spMin(n.devId)) }} ~ {{ fmt(spMax(n.devId)) }}</span>
            <span v-else class="rf-hint">{{ t('只读，不可设定') }}</span>
            <span v-if="!isLinked(n)" class="rf-warn">{{ t('未接入条件分支') }}</span>
          </div>

          <span class="rf-pt out" @mousedown.stop="startLink(n, 'out')"></span>
        </div>

        <!-- ─────── IF 条件节点 ─────── -->
        <div v-for="n in ifNodes" :key="n.id" class="rf-node ifn" :data-nid="n.id"
             :class="{ sel: n.id === selNode }" :style="nodeStyle(n)" @mousedown.stop="selNode = n.id">
          <span class="rf-pt in"></span>

          <div class="rf-hd" @mousedown.stop="startMove(n, $event)">
            <i class="rf-ic">⑃</i>
            <span class="rf-nm">{{ t('条件判断') }}</span>
            <em class="rf-ut mono">if / elif / else</em>
            <button class="rf-x" :title="t('删除模块')" @mousedown.stop @click.stop="delNode(n)">✕</button>
          </div>

          <div v-for="b in n.branches" :key="b.id" class="rf-br"
               :class="[b.type, { act: activeBranch === n.id + ':' + b.id }]">
            <div class="rf-br1">
              <span class="rf-bt">{{ b.type === 'if' ? t('如果') : b.type === 'elif' ? t('否则如果') : t('否则') }}</span>
              <template v-if="b.type !== 'else'">
                <select class="rf-sel src" v-model="b.src" @mousedown.stop @focus="histBegin" @change="histCommit">
                  <option value="">{{ t('跟随输入') }}</option>
                  <option v-for="d in devNodes" :key="d.id" :value="d.id">{{ d.label }}</option>
                </select>
                <select class="rf-sel op" v-model="b.op" @mousedown.stop @focus="histBegin" @change="histCommit">
                  <option v-for="o in OPS" :key="o.v" :value="o.v">{{ o.l }}</option>
                </select>
                <input class="rf-num sm" type="number" v-model.number="b.val" @mousedown.stop @focus="histBegin" @change="histCommit" />
              </template>
              <span v-else class="rf-el">{{ t('以上都不满足') }}</span>
              <button v-if="b.type === 'elif'" class="rf-bx" :title="t('删除该分支')" @mousedown.stop @click.stop="delBranch(n, b)">✕</button>
            </div>
            <div class="rf-br2">
              <span class="rf-tg" :class="{ none: !branchTarget(n, b) }">
                {{ branchTarget(n, b) ? '→ ' + branchTarget(n, b).label : t('未连接下游') }}
              </span>
              <span class="rf-sv mono" v-if="b.type !== 'else'">{{ branchSrcTxt(n, b) }}</span>
            </div>
            <span class="rf-pt out" @mousedown.stop="startLink(n, b.id)"></span>
          </div>

          <div class="rf-nft">
            <button class="rf-add" @mousedown.stop @click.stop="addBranch(n)">+ {{ t('elif') }}</button>
          </div>
        </div>

        <!-- ─────── 模块实时值：点选卡片后直接显示在其下方 ─────── -->
        <div v-if="selDev" class="rf-insp" :style="inspStyle(selDev)" @mousedown.stop>
          <div class="ri-hd">
            <i class="ri-d" :class="selDev.kind"></i>
            <b>{{ selDev.label }}</b>
            <span class="ri-t">{{ selDev.kind === 'adj' ? t('可调设备') : t('传感设备') }}</span>
            <button class="ri-x" :title="t('关闭')" @click.stop="selNode = ''">✕</button>
          </div>
          <div class="ri-v"><b class="mono">{{ fmt(liveOf(selDev.devId)) }}</b><i>{{ selDev.unit || '' }}</i></div>
          <svg class="ri-sp" viewBox="0 0 240 40" preserveAspectRatio="none">
            <polyline v-if="spark(selDev.devId)" class="sp-l" :points="spark(selDev.devId)" />
            <text v-else class="sp-e" x="120" y="24">{{ t('暂无历史数据') }}</text>
          </svg>
          <div v-if="selDev.kind === 'adj'" class="ri-r"><em>{{ t('设定值') }}</em><b class="mono">{{ fmt(curSp(selDev.devId)) }}{{ selDev.unit || '' }}</b></div>
          <div v-if="selDev.kind === 'adj'" class="ri-r"><em>{{ t('量程') }}</em><b class="mono">{{ fmt(spMin(selDev.devId)) }} ~ {{ fmt(spMax(selDev.devId)) }}</b></div>
          <div class="ri-r"><em>{{ t('最新采样') }}</em><b class="mono">{{ lastTsTxt(selDev.devId) }}</b></div>
        </div>
      </div>

      <div v-if="!nodes.length" class="rf-empty">
        <p class="t1">{{ t('从左侧「可调设备 / 传感设备」拖拽到画布，或点击「+ if 模块」开始编排') }}</p>
        <p class="t2">{{ t('规则逻辑：传感/可调 → IF 条件 → 命中的分支 → 下游可调（自动写入设定值）或传感（仅观测）') }}</p>
      </div>
    </div>

    <!-- ══════════ 校验 ══════════ -->
    <div v-if="issues.length" class="rfe-iss">
      <div class="iss-h">{{ t('编排校验') }} · {{ issues.length }}</div>
      <div v-for="(s, i) in issues" :key="i" class="iss-r">· {{ s }}</div>
    </div>

    <!-- ══════════ 日志 ══════════ -->
    <div v-if="showLog" class="rfe-log">
      <div v-if="!log.length" class="lg-e">{{ t('暂无执行记录') }}</div>
      <div v-for="(r, i) in log" :key="i" class="lg-r">
        <span class="mono dim">{{ tsTxt(r.ts) }}</span>
        <span class="lg-t">{{ r.txt }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useSimStore } from '../stores/sim'
import { DEVICE_MAP } from '../data/flowLibrary'
import { ADJUSTABLE_MAP } from '../data/attachLibrary'
import { t } from '../i18n'

const props = defineProps({
  // { nodes: [], edges: [] } —— 由父组件（模型）持有的响应式对象，本组件就地读写，持久化由父组件负责
  graph: { type: Object, required: true },
  // 运行状态由编排页右上角的「运行」按钮驱动，本组件不再自带运行开关
  running: { type: Boolean, default: false },
  period: { type: Number, default: 2 },
})

// 画布自身发生增删改（含撤销/重做）时通知编排页：左栏勾选随之同步，保持「勾选 ⇄ 模块」一致
const emit = defineEmits(['canvas-change'])

const store = useSimStore()

// ─────────── 几何常量 ───────────
const CV_W = 4200
const CV_H = 3000
// 原点余量：把世界原点 (0,0) 向右下推 ORIGIN 像素渲染，于是 -ORIGIN ~ 0 的负坐标仍在画布内可见。
// 模块才能往左 / 往上自由拖动布局（否则坐标只能 ≥ 0 = 死死贴在画布左上角，往上拖完全没反应）。
const ORIGIN = 400
const DEV_W = 208
const DEV_H = 84
const IF_W = 300
const IF_HD = 30       // 头部
const IF_BR = 46       // 每条分支（两行：条件 + 下游提示）
const IF_FT = 28       // 底部 +elif
const OPS = [
  { v: '>', l: '>' }, { v: '>=', l: '≥' }, { v: '<', l: '<' },
  { v: '<=', l: '≤' }, { v: '==', l: '=' }, { v: '!=', l: '≠' },
]

const nodes = computed(() => (props.graph && props.graph.nodes) || [])
const edges = computed(() => (props.graph && props.graph.edges) || [])
const ifNodes = computed(() => nodes.value.filter((n) => n.kind === 'if'))
const devNodes = computed(() => nodes.value.filter((n) => n.kind !== 'if'))

// ─────────── 设备候选（与 AI 群控左栏同源） ───────────
const all = computed(() => store.allDevices || [])
const adjList = computed(() => all.value.filter((d) => d.adjustable))
const senList = computed(() => all.value.filter((d) => !d.adjustable))

function findDev(id) {
  if (!id) return null
  // store.findDevice 返回 { device, unitId, unitName, unitType } 包装，这里只取设备本体
  try {
    const i = store.findDevice(id) || null
    return i ? (i.device || i) : null
  } catch (e) { return null }
}
function spCfg(id) {
  const d = findDev(id)
  if (!d) return null
  const tm = d.type ? DEVICE_MAP[d.type] : null
  if (tm && tm.setpoint) return tm.setpoint
  const at = d.type ? ADJUSTABLE_MAP[d.type] : null
  return (at && at.setpoint) || null
}
function spMin(id) { const c = spCfg(id); return c ? Number(c.min) : 0 }
function spMax(id) { const c = spCfg(id); return c ? Number(c.max) : 100 }
function spStep(id) {
  const r = spMax(id) - spMin(id)
  if (r >= 1000) return 10
  if (r >= 100) return 1
  if (r >= 10) return 0.1
  return 0.01
}
function liveOf(id) {
  if (!id) return null
  const lv = store.deviceLiveOf(id)
  if (lv != null) return Number(lv)
  const h = store.deviceHistoryOf(id)
  if (h && h.length) return Number(h[h.length - 1].v)
  const d = findDev(id)
  if (d && d.live != null) return Number(d.live)
  if (d && d.reading != null) return Number(d.reading)
  return null
}
function isMissing(n) { return n.kind !== 'if' && !findDev(n.devId) }

// ─────────── 视图（平移 / 缩放） ───────────
const view = reactive({ x: 0, y: 0, z: 1 })
const vpStyle = computed(() => ({
  // +ORIGIN：让负坐标区域（画布左上方）也落在可视范围内，见 ORIGIN 注释
  transform: `translate(${view.x + ORIGIN}px, ${view.y + ORIGIN}px) scale(${view.z})`,
}))
const cvEl = ref(null)
const selNode = ref('')
const selEdge = ref('')

function onWheel(e) {
  const el = cvEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  // 换算到「未平移前的世界坐标」基准（与 toWorld 一致），保证以光标为锚点缩放
  const mx = e.clientX - r.left - ORIGIN
  const my = e.clientY - r.top - ORIGIN
  const nz = Math.min(1.8, Math.max(0.35, view.z * (e.deltaY < 0 ? 1.1 : 1 / 1.1)))
  view.x = mx - ((mx - view.x) * nz) / view.z
  view.y = my - ((my - view.y) * nz) / view.z
  view.z = nz
}
function toWorld(cx, cy) {
  const r = cvEl.value ? cvEl.value.getBoundingClientRect() : { left: 0, top: 0 }
  return { x: (cx - r.left - view.x - ORIGIN) / view.z, y: (cy - r.top - view.y - ORIGIN) / view.z }
}

// ─────────── 鼠标交互（移动 / 平移 / 连线） ───────────
let drag = null
const link = ref(null)          // { node, port, x, y }
const tmpD = computed(() => {
  if (!link.value) return ''
  return bez(outPort(link.value.node, link.value.port), { x: link.value.x, y: link.value.y })
})

function onCvDown(e) {
  if (e.button !== 0) return
  // 光标落在模块卡片上时不平移画布（否则按住卡片拖动会变成整块画布平移 = 「拖不动」）
  if (e.target && e.target.closest && e.target.closest('[data-nid]')) return
  selNode.value = ''
  selEdge.value = ''
  drag = { kind: 'pan', sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y }
}
function startMove(n, e) {
  selNode.value = n.id
  histBegin()   // 拖拽前的位置入历史，整个拖拽合并为一步
  drag = { kind: 'node', id: n.id, sx: e.clientX, sy: e.clientY, ox: n.x, oy: n.y }
}
function startLink(n, port) {
  const p = outPort(n, port)
  link.value = { node: n, port, x: p.x, y: p.y }
  drag = { kind: 'link' }
}
/** 把卡片落到光标下（世界坐标），并按画布范围夹取：
 *  下界 -ORIGIN（可拖到画布左 / 上方可见区），上界 画布尺寸 - 卡片尺寸（不越出右 / 下边界）。 */
function moveNodeTo(cx, cy) {
  if (!drag || drag.kind !== 'node') return
  const n = nodes.value.find((x) => x.id === drag.id)
  if (!n) return
  const clampX = (v) => Math.round(Math.min(CV_W - nodeW(n), Math.max(-ORIGIN, v)))
  const clampY = (v) => Math.round(Math.min(CV_H - nodeH(n), Math.max(-ORIGIN, v)))
  n.x = clampX(drag.ox + (cx - drag.sx) / view.z)
  n.y = clampY(drag.oy + (cy - drag.sy) / view.z)
}
// 拖到画布边缘时自动平移视图：卡片才能继续往上 / 左（或下 / 右）拖出可视区，而不是卡在边上
const EDGE = 30, PAN_STEP = 14
let panRaf = 0
let lastPt = { x: 0, y: 0 }
function stopAutoPan() { if (panRaf) { cancelAnimationFrame(panRaf); panRaf = 0 } }
function autoPanTick() {
  panRaf = 0
  if (!drag || drag.kind !== 'node' || !cvEl.value) return
  const el = cvEl.value
  const r = el.getBoundingClientRect()
  // 只有光标真的越出画布边界才平移（否则在画布内部靠近边缘也算，容易误触发）
  let dx = 0, dy = 0
  if (lastPt.x < r.left) dx = PAN_STEP
  else if (lastPt.x > r.right) dx = -PAN_STEP
  if (lastPt.y < r.top) dy = PAN_STEP
  else if (lastPt.y > r.bottom) dy = -PAN_STEP
  if (!dx && !dy) return
  view.x += dx
  view.y += dy
  // 视图平移后光标对应的世界坐标变了：补偿拖拽起点，让卡片始终黏在光标下而不是跟着画布跑
  drag.ox -= dx / view.z
  drag.oy -= dy / view.z
  moveNodeTo(lastPt.x, lastPt.y)
  panRaf = requestAnimationFrame(autoPanTick)
}
function onWinMove(e) {
  if (!drag) return
  if (drag.kind === 'pan') {
    view.x = drag.ox + (e.clientX - drag.sx)
    view.y = drag.oy + (e.clientY - drag.sy)
  } else if (drag.kind === 'node') {
    lastPt = { x: e.clientX, y: e.clientY }
    moveNodeTo(e.clientX, e.clientY)
    if (!panRaf) panRaf = requestAnimationFrame(autoPanTick)
  } else if (drag.kind === 'link' && link.value) {
    const w = toWorld(e.clientX, e.clientY)
    link.value.x = w.x
    link.value.y = w.y
  }
}
function onWinUp(e) {
  if (drag && drag.kind === 'link' && link.value) {
    const el = document.elementFromPoint(e.clientX, e.clientY)
    const host = el && el.closest ? el.closest('[data-nid]') : null
    if (host) finishLink(host.getAttribute('data-nid'))
  }
  histCommit()   // 节点拖拽结束，位置变化合并入历史
  stopAutoPan()
  drag = null
  link.value = null
}
function finishLink(toId) {
  const from = link.value ? link.value.node : null
  const port = link.value ? link.value.port : 'out'
  if (!from || !toId || toId === from.id) return
  histBegin()
  // 一个输出端口只允许一条出线（条件分支需要唯一走向）
  for (let i = edges.value.length - 1; i >= 0; i--) {
    if (edges.value[i].from === from.id && edges.value[i].port === port) edges.value.splice(i, 1)
  }
  edges.value.push({ id: 'e' + Math.random().toString(36).slice(2, 8), from: from.id, port, to: toId })
  histCommit()
}
function onKey(e) {
  const tag = (e.target && e.target.tagName) || ''
  const typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA'
  if (e.ctrlKey || e.metaKey) {
    if (typing) return
    const k = String(e.key || '').toLowerCase()
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
    else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); redo() }
    else if (k === 'c') { e.preventDefault(); copySel() }
    else if (k === 'x') { e.preventDefault(); cutSel() }
    else if (k === 'v') { e.preventDefault(); paste() }
    return
  }
  if (e.key !== 'Delete' && e.key !== 'Backspace') return
  if (typing) return
  if (selEdge.value) { delEdge(selEdge.value); e.preventDefault() }
  else if (selNode.value) { delNode(nodes.value.find((n) => n.id === selNode.value)); e.preventDefault() }
}

// ─────────── 节点 CRUD ───────────
let seq = 1
function nid(p) { return p + '_' + Date.now().toString(36) + '_' + (seq++) }
function centerWorld() {
  const el = cvEl.value
  if (!el) return { x: 420, y: 240 }
  const r = el.getBoundingClientRect()
  return toWorld(r.left + el.clientWidth / 2, r.top + el.clientHeight / 2)
}
function addIf() {
  histBegin()
  const c = centerWorld()
  const n = nodes.value.length
  nodes.value.push({
    id: nid('if'),
    kind: 'if',
    x: Math.max(12, Math.round(c.x - IF_W / 2 + (n % 4) * 18)),
    y: Math.max(12, Math.round(c.y - 70 + (n % 4) * 14)),
    branches: [
      { id: 'b1', type: 'if', src: '', op: '>', val: 0 },
      { id: 'b2', type: 'else', src: '', op: '>', val: 0 },
    ],
  })
  histCommit()
}
function addDev(kind) {
  const list = kind === 'adj' ? adjList.value : senList.value
  if (!list.length) return
  addDevById(kind, list[0], null)
}
function addDevById(kind, d, at) {
  histBegin()
  const c = at || centerWorld()
  const v = kind === 'adj'
    ? Number(Number(d && d.setpoint != null ? d.setpoint : spMin(d.id)).toFixed(3))
    : null
  nodes.value.push({
    id: nid(kind),
    kind,
    devId: d.id,
    label: d.label || d.id,
    unit: d.unit || '',
    unitName: d.unitName || '',
    value: v,
    x: Math.max(12, Math.round(c.x - DEV_W / 2)),
    y: Math.max(12, Math.round(c.y - DEV_H / 2)),
  })
  histCommit()
}
function addBranch(n) {
  histBegin()
  // elif 插在 else 之前
  const ei = n.branches.findIndex((b) => b.type === 'else')
  const item = { id: 'b' + Date.now().toString(36) + (seq++), type: 'elif', src: '', op: '>', val: 0 }
  if (ei >= 0) n.branches.splice(ei, 0, item)
  else n.branches.push(item)
  histCommit()
}
function delBranch(n, b) {
  histBegin()
  const i = n.branches.indexOf(b)
  if (i >= 0) n.branches.splice(i, 1)
  for (let k = edges.value.length - 1; k >= 0; k--) {
    if (edges.value[k].from === n.id && edges.value[k].port === b.id) edges.value.splice(k, 1)
  }
  histCommit()
}
function delNode(n) {
  if (!n) return
  histBegin()
  const i = nodes.value.indexOf(n)
  if (i >= 0) nodes.value.splice(i, 1)
  for (let k = edges.value.length - 1; k >= 0; k--) {
    const e = edges.value[k]
    if (e.from === n.id || e.to === n.id) edges.value.splice(k, 1)
  }
  // 清掉其它 IF 分支里指向它的判定来源
  for (const m of ifNodes.value) for (const b of m.branches) if (b.src === n.id) b.src = ''
  if (selNode.value === n.id) selNode.value = ''
  histCommit()
}
function delEdge(id) {
  histBegin()
  const i = edges.value.findIndex((e) => e.id === id)
  if (i >= 0) edges.value.splice(i, 1)
  if (selEdge.value === id) selEdge.value = ''
  histCommit()
}
function clearAll() {
  histBegin()
  nodes.value.splice(0, nodes.value.length)
  edges.value.splice(0, edges.value.length)
  selNode.value = ''
  selEdge.value = ''
  histCommit()
}
function clampVal(n) {
  const v = Number(n.value)
  if (!Number.isFinite(v)) return
  n.value = Math.min(spMax(n.devId), Math.max(spMin(n.devId), v))
}

// ─────────── 撤销 / 重做 ───────────
// 快照式历史：每次变更前捕获 { nodes, edges } 快照；拖拽移动、连续输入合并为一步。
const undoStack = ref([])
const redoStack = ref([])
const HIST_CAP = 60
let preSnap = null
function snapState() { return JSON.stringify({ n: nodes.value, e: edges.value }) }
/** 交互/操作开始前调用：捕获变更前状态（已在捕获中则忽略） */
function histBegin() { if (preSnap == null) preSnap = snapState() }
/** 操作结束调用：有实际变化才入栈，并清空重做栈 */
function histCommit() {
  if (preSnap == null) return
  const now = snapState()
  if (now !== preSnap) {
    undoStack.value.push(JSON.parse(preSnap))
    if (undoStack.value.length > HIST_CAP) undoStack.value.shift()
    redoStack.value = []
    emit('canvas-change')
  }
  preSnap = null
}
function applyState(s) {
  nodes.value.splice(0, nodes.value.length, ...JSON.parse(JSON.stringify(s.n || [])))
  edges.value.splice(0, edges.value.length, ...JSON.parse(JSON.stringify(s.e || [])))
}
const canUndo = computed(() => undoStack.value.length > 0)
const canRedo = computed(() => redoStack.value.length > 0)
function undo() {
  histCommit()
  if (!undoStack.value.length) return
  redoStack.value.push(JSON.parse(snapState()))
  applyState(undoStack.value.pop())
  selNode.value = ''
  selEdge.value = ''
  emit('canvas-change')
}
function redo() {
  histCommit()
  if (!redoStack.value.length) return
  undoStack.value.push(JSON.parse(snapState()))
  applyState(redoStack.value.pop())
  selNode.value = ''
  selEdge.value = ''
  emit('canvas-change')
}
/** 数值输入整段编辑合并为一步（focus 捕获，change 提交） */
function commitVal(n) { clampVal(n); histCommit() }

// ─────────── 复制 / 剪切 / 粘贴（画布内部剪贴板） ───────────
const clipboard = ref(null)
function cloneNode(n) { return JSON.parse(JSON.stringify(n)) }
function copySel() {
  const n = selNode.value ? nodes.value.find((x) => x.id === selNode.value) : null
  if (!n) return
  clipboard.value = cloneNode(n)
}
function cutSel() {
  const n = selNode.value ? nodes.value.find((x) => x.id === selNode.value) : null
  if (!n) return
  clipboard.value = cloneNode(n)
  delNode(n)
}
function paste() {
  const src = clipboard.value
  if (!src) return
  histBegin()
  const c = cloneNode(src)
  c.id = nid(c.kind === 'if' ? 'if' : c.kind)
  c.x = Math.min(CV_W - nodeW(c) - 12, Math.max(12, (c.x || 40) + 28))
  c.y = Math.min(CV_H - nodeH(c) - 12, Math.max(12, (c.y || 40) + 28))
  if (c.kind === 'if' && Array.isArray(c.branches)) {
    for (const b of c.branches) {
      b.id = 'b' + Date.now().toString(36) + '_' + (seq++)
      if (b.src) b.src = ''   // 分支判定来源指向旧节点，粘贴后需重新指定
    }
  }
  nodes.value.push(c)
  selNode.value = c.id
  selEdge.value = ''
  histCommit()
}

// ─────────── 拖放（左侧设备 → 画布） ───────────



// ─────────── 几何：端口与连线 ───────────
function nodeW(n) { return n.kind === 'if' ? IF_W : DEV_W }
function nodeH(n) { return n.kind === 'if' ? IF_HD + n.branches.length * IF_BR + IF_FT : DEV_H }
function nodeStyle(n) {
  return { left: n.x + 'px', top: n.y + 'px', width: nodeW(n) + 'px', height: nodeH(n) + 'px' }
}
function inPort(n) { return { x: n.x, y: n.y + nodeH(n) / 2 } }
function outPort(n, port) {
  if (n.kind === 'if') {
    let i = n.branches.findIndex((b) => b.id === port)
    if (i < 0) i = 0
    return { x: n.x + IF_W, y: n.y + IF_HD + i * IF_BR + IF_BR / 2 }
  }
  return { x: n.x + DEV_W, y: n.y + DEV_H / 2 }
}
function bez(a, b) {
  const dx = Math.max(28, Math.abs(b.x - a.x) * 0.45)
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`
}
function edgeD(e) {
  const from = nodes.value.find((n) => n.id === e.from)
  const to = nodes.value.find((n) => n.id === e.to)
  if (!from || !to) return ''
  return bez(outPort(from, e.port), inPort(to))
}
const edgeMid = computed(() => {
  const e = edges.value.find((x) => x.id === selEdge.value)
  if (!e) return null
  const from = nodes.value.find((n) => n.id === e.from)
  const to = nodes.value.find((n) => n.id === e.to)
  if (!from || !to) return null
  const a = outPort(from, e.port)
  const b = inPort(to)
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
})
function isLinked(n) {
  if (n.kind === 'if') return true
  return edges.value.some((e) => e.to === n.id || e.from === n.id)
}
function branchTarget(n, b) {
  const e = edges.value.find((x) => x.from === n.id && x.port === b.id)
  if (!e) return null
  return nodes.value.find((x) => x.id === e.to) || null
}
function branchSrcTxt(n, b) {
  const s = srcNodeOf(n, b)
  if (!s) return t('无判定来源')
  const v = liveOf(s.devId)
  return `${s.label} = ${v == null ? '—' : fmt(v)}`
}
/** 判定来源：分支显式指定 > IF 模块输入连线 > 无 */
function srcNodeOf(n, b) {
  if (b.src) {
    const x = nodes.value.find((k) => k.id === b.src)
    if (x && x.kind !== 'if') return x
  }
  const e = edges.value.find((x) => x.to === n.id)
  if (!e) return null
  const s = nodes.value.find((x) => x.id === e.from)
  return s && s.kind !== 'if' ? s : null
}

// ─────────── 校验 ───────────
const issues = computed(() => {
  const out = []
  for (const n of nodes.value) {
    if (n.kind === 'if') {
      if (!n.branches.some((b) => b.type === 'else')) {
        out.push(t('IF 模块缺少 else 分支（建议保留兜底走向）'))
      }
      for (const b of n.branches) {
        const bn = b.type === 'if' ? t('如果') : b.type === 'elif' ? t('否则如果') : t('否则')
        if (b.type !== 'else') {
          if (!srcNodeOf(n, b)) out.push(t('IF 模块「{name}」分支未接入判定来源', { name: bn }))
          if (!Number.isFinite(Number(b.val))) out.push(t('IF 模块「{name}」分支阈值未填写', { name: bn }))
        }
        if (!branchTarget(n, b)) out.push(t('IF 模块「{name}」分支未连接下游模块', { name: bn }))
      }
    } else {
      if (isMissing(n)) out.push(t('模块「{name}」对应的设备已不存在', { name: n.label }))
      if (n.kind === 'adj' && !Number.isFinite(Number(n.value))) out.push(t('可调模块「{name}」未设定数值', { name: n.label }))
      if (!isLinked(n)) out.push(t('模块「{name}」未接入任何模块，不会被执行', { name: n.label }))
    }
  }
  return out
})

// ─────────── 执行（由编排页右上角「运行」驱动） ───────────
const showLog = ref(false)
const log = ref([])
const lastActs = ref([])
const activeNode = ref(new Set())
const activeEdge = ref(new Set())
const activeBranch = ref('')
let runTimer = null

function cmp(a, op, b) {
  const x = Number(a)
  const y = Number(b)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false
  switch (op) {
    case '>': return x > y
    case '>=': return x >= y
    case '<': return x < y
    case '<=': return x <= y
    case '==': return Math.abs(x - y) < 1e-9
    case '!=': return Math.abs(x - y) >= 1e-9
    default: return false
  }
}
function pushLog(txt) {
  log.value.unshift({ ts: Date.now(), txt })
  if (log.value.length > 40) log.value.length = 40
}
/** 执行一遍：IF 命中分支 → 写入下游可调设定值（传感仅观测）→ 继续往下串联 */
function runOnce(withLog) {
  const acts = []
  const an = new Set()
  const ae = new Set()
  let ab = ''
  const visited = new Set()
  const onBr = (v) => { if (!ab) ab = v }
  for (const n of ifNodes.value) {
    if (visited.has(n.id)) continue
    evalIf(n, visited, 0, acts, an, ae, onBr)
  }
  for (const a of acts) {
    if (a.write) store.setDeviceSetpoint(a.devId, a.value)
  }
  lastActs.value = acts
  activeNode.value = an
  activeEdge.value = ae
  activeBranch.value = ab
  if (withLog) {
    if (!acts.length) pushLog(t('本轮无命中（检查判定来源与阈值）'))
    else for (const a of acts) pushLog(a.txt)
  }
  return acts
}
function evalIf(n, visited, depth, acts, an, ae, onBranch) {
  if (depth > 8 || visited.has(n.id)) return
  visited.add(n.id)
  let hit = null
  for (const b of n.branches) {
    if (b.type === 'else') continue
    const s = srcNodeOf(n, b)
    const v = s ? liveOf(s.devId) : null
    if (v != null && cmp(v, b.op, b.val)) { hit = b; break }
  }
  if (!hit) hit = n.branches.find((b) => b.type === 'else') || null
  if (!hit) return
  onBranch(n.id + ':' + hit.id)
  for (const e of edges.value.filter((x) => x.from === n.id && x.port === hit.id)) {
    ae.add(e.id)
    const tgt = nodes.value.find((x) => x.id === e.to)
    if (!tgt) continue
    an.add(tgt.id)
    if (tgt.kind === 'adj') {
      const v = Number(tgt.value)
      if (Number.isFinite(v)) {
        acts.push({ write: true, devId: tgt.devId, value: v, txt: `${tgt.label} ← ${t('写入')} ${fmt(v)}${tgt.unit || ''}` })
      }
    } else {
      acts.push({ write: false, devId: tgt.devId, txt: `${tgt.label}（${t('仅观测，不写入')}）` })
    }
    // 继续往下串联
    const nx = edges.value.find((x) => x.from === tgt.id)
    if (nx) {
      const nn = nodes.value.find((x) => x.id === nx.to)
      if (nn && nn.kind === 'if') evalIf(nn, visited, depth + 1, acts, an, ae, onBranch)
    }
  }
}
function startTimer() {
  stopTimer()
  runOnce(true)
  runTimer = setInterval(() => runOnce(true), Math.max(1, Number(props.period) || 1) * 1000)
}
function stopTimer() {
  if (runTimer) { clearInterval(runTimer); runTimer = null }
}
watch(() => props.running, (on) => { if (on) startTimer(); else stopTimer() }, { immediate: true })
watch(() => props.period, () => { if (props.running) startTimer() })

// ─────────── 视图操作 ───────────
function fitView() {
  const ns = nodes.value
  if (!ns.length || !cvEl.value) return
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const n of ns) {
    x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y)
    x1 = Math.max(x1, n.x + nodeW(n)); y1 = Math.max(y1, n.y + nodeH(n))
  }
  const pad = 40
  const w = cvEl.value.clientWidth
  const h = cvEl.value.clientHeight
  const z = Math.min(1.4, Math.max(0.35, Math.min((w - pad * 2) / (x1 - x0), (h - pad * 2) / (y1 - y0))))
  view.z = z
  // -ORIGIN：抵消渲染时的原点余量（见 ORIGIN 注释），否则适应视图后整体偏右 / 下
  view.x = (w - (x1 - x0) * z) / 2 - x0 * z - ORIGIN
  view.y = (h - (y1 - y0) * z) / 2 - y0 * z - ORIGIN
}

// ─────────── 格式化 ───────────
function fmt(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 1 : 2 })
}
function p2(n) { return String(n).padStart(2, '0') }
function tsTxt(ts) {
  const d = new Date(ts)
  return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
}

// ─────────── 模块选中 → 卡片下方直接显示实时值 ───────────
const selDev = computed(() => {
  const n = selNode.value ? nodes.value.find((x) => x.id === selNode.value) : null
  return n && n.kind !== 'if' ? n : null
})
/** 检查器贴在被点选卡片的正下方（画布世界坐标，随缩放平移一起动） */
function inspStyle(n) {
  return { left: Math.max(-ORIGIN + 4, n.x) + 'px', top: (n.y + nodeH(n) + 8) + 'px' }
}
/** 当前设定值（store 覆盖 → 设备实例 → 模板默认） */
function curSp(id) {
  const d = findDev(id)
  if (!d) return null
  if (store.deviceSetpoints[id] != null) return Number(store.deviceSetpoints[id])
  if (d.setpoint != null && Number.isFinite(Number(d.setpoint))) return Number(d.setpoint)
  const c = spCfg(id)
  return c ? Number(c.def) : null
}
/** 迷你趋势：最近 60 个点映射到 240×40 */
function spark(id) {
  let h = []
  try { h = store.deviceHistoryOf(id) || [] } catch (e) { h = [] }
  const pts = h.slice(-60)
  if (pts.length < 2) return ''
  let lo = Infinity, hi = -Infinity
  for (const p of pts) {
    const v = Number(p && p.v)
    if (!Number.isFinite(v)) continue
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return ''
  const span = (hi - lo) || 1
  return pts.map((p, i) => {
    const v = Number(p && p.v)
    const x = (i / (pts.length - 1)) * 240
    const y = Number.isFinite(v) ? 38 - ((v - lo) / span) * 34 : 20
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
function lastTsTxt(id) {
  let h = []
  try { h = store.deviceHistoryOf(id) || [] } catch (e) { h = [] }
  if (!h.length) return '—'
  const ts = Number(h[h.length - 1] && h[h.length - 1].t) || 0
  if (!ts) return '—'
  return tsTxt(ts < 1e12 ? ts * 1000 : ts)
}

// ─────────── 生命周期 ───────────
onMounted(() => {
  window.addEventListener('mousemove', onWinMove)
  window.addEventListener('mouseup', onWinUp)
  window.addEventListener('keydown', onKey)
  if (nodes.value.length) setTimeout(fitView, 0)
})
onBeforeUnmount(() => {
  stopAutoPan()
  stopTimer()
  window.removeEventListener('mousemove', onWinMove)
  window.removeEventListener('mouseup', onWinUp)
  window.removeEventListener('keydown', onKey)
})

defineExpose({ runOnce, fitView })
</script>

<style scoped>
.rfe { display: flex; flex-direction: column; min-height: 0; }

/* ══════════ 工具条 ══════════ */
.rfe-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 8px; background: var(--panel-2); border: 1px solid var(--border);
  border-bottom: 0; border-radius: 3px 3px 0 0;
}
.rf-b {
  padding: 2px 9px; font-size: 11px; font-family: inherit; color: var(--muted);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; cursor: pointer;
}
.rf-b:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent-d); }
.rf-b:disabled { opacity: .45; cursor: not-allowed; }
.rf-b.pri { color: #fff; background: var(--accent-d); border-color: transparent; font-weight: 500; }
.rf-b.pri:hover:not(:disabled) { filter: brightness(1.08); color: #fff; }
.rf-b.ghost { background: transparent; }
.rf-sep { flex: 0 0 auto; width: 1px; height: 14px; background: var(--line); }
.rf-sp { flex: 1 1 auto; }
.rf-lg { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; color: var(--muted); }
.lg-d { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.lg-d.adj { background: #D97A21; }
.lg-d.sen { background: #17957F; }
.lg-d.ifn { background: #7A5AA8; }
.rf-cnt { font-size: 10px; color: var(--faint); }
.rf-zoom { font-size: 10px; color: var(--faint); min-width: 34px; text-align: right; }

/* ══════════ 画布 ══════════ */
.rfe-cv {
  position: relative; flex: 1 1 auto; min-height: 420px; overflow: hidden;
  border: 1px solid var(--border);
  background: radial-gradient(circle at 1px 1px, var(--line) 1px, transparent 0) 0 0 / 22px 22px, var(--panel);
}
.rfe-vp { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
.rfe-svg { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
.rf-e-hit { fill: none; stroke: transparent; stroke-width: 14; pointer-events: stroke; cursor: pointer; }
.rf-e { fill: none; stroke: var(--muted); stroke-width: 1.6; stroke-linecap: round; pointer-events: none; }
.rf-e.on { stroke: var(--accent-d); stroke-width: 2.4; }
.rf-e.act { stroke: #2E8B57; stroke-width: 2.6; }
.rf-e.tmp { stroke: var(--accent-d); stroke-dasharray: 5 4; }
.rf-eg { cursor: pointer; pointer-events: all; }
.rf-ebg { fill: var(--red); }
.rf-ex { fill: #fff; font-size: 10px; text-anchor: middle; }

.rf-empty {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px; padding: 0 40px;
  text-align: center; pointer-events: none;
}
.rf-empty .t1 { font-size: 12px; color: var(--muted); }
.rf-empty .t2 { font-size: 10.5px; color: var(--faint); max-width: 520px; line-height: 1.7; }

/* ══════════ 节点通用 ══════════ */
/* 模块实时值：贴在卡片正下方（画布世界坐标） */
.rf-insp {
  /* 只作展示：不拦截鼠标，避免压住下方卡片的拖动/点击（仅关闭按钮可点） */
  pointer-events: none;
  position: absolute; z-index: 6; width: 208px; box-sizing: border-box;
  display: flex; flex-direction: column; gap: 4px; padding: 7px 9px 8px;
  border: 1px solid var(--border); border-top: 2px solid var(--accent-d); border-radius: 3px;
  background: var(--panel); box-shadow: 0 3px 12px rgba(0, 0, 0, .16);
}
.ri-hd { display: flex; align-items: center; gap: 5px; }
.ri-d { width: 7px; height: 7px; border-radius: 50%; background: #888; flex: 0 0 auto; }
.ri-d.adj { background: #D97A21; }
.ri-d.sen { background: #17957F; }
.ri-hd b { font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-t {
  flex: 0 0 auto; padding: 0 5px; border-radius: 8px; font-size: 9px; line-height: 14px;
  background: var(--bar); color: var(--muted); border: 1px solid var(--border);
}
.ri-x {
  margin-left: auto; flex: 0 0 auto; padding: 0 3px; border: 0; background: none; cursor: pointer;
  pointer-events: auto;
  font-family: inherit; font-size: 11px; color: var(--faint);
}
.ri-x:hover { color: var(--red); }
.ri-v { display: flex; align-items: baseline; gap: 3px; }
.ri-v b { font-size: 19px; font-weight: 600; color: var(--accent-d); line-height: 1.1; }
.ri-v i { font-style: normal; font-size: 10px; color: var(--faint); }
.ri-sp { width: 100%; height: 40px; }
.ri-sp .sp-l { fill: none; stroke: var(--accent-d); stroke-width: 1.4; vector-effect: non-scaling-stroke; }
.ri-sp .sp-e { fill: var(--faint); font-size: 9px; text-anchor: middle; }
.ri-r { display: flex; align-items: baseline; justify-content: space-between; font-size: 10px; }
.ri-r em { font-style: normal; color: var(--faint); }
.ri-r b { color: var(--muted); font-weight: 600; }

.rf-node {
  position: absolute; box-sizing: border-box; border-radius: 4px;
  background: var(--panel); border: 1px solid var(--border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .10); font-size: 11px; color: var(--text); user-select: none;
}
.rf-node::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; border-radius: 4px 0 0 4px;
}
.rf-node.sel { border-color: var(--accent-d); box-shadow: 0 0 0 2px var(--accent-l); }
.rf-node.act { box-shadow: 0 0 0 2px rgba(46, 139, 87, .45); }
.rf-node.miss { opacity: .6; border-style: dashed; }

/* 三类模块配色：可调=橙 / 传感=青 / 条件=紫 */
.rf-node.adj::before { background: #D97A21; }
.rf-node.adj .rf-hd { background: rgba(217, 122, 33, .13); }
.rf-node.adj .rf-ic { color: #D97A21; }
.rf-node.adj .rf-pt { border-color: #D97A21; }
.rf-node.sen::before { background: #17957F; }
.rf-node.sen .rf-hd { background: rgba(23, 149, 127, .13); }
.rf-node.sen .rf-ic { color: #17957F; }
.rf-node.sen .rf-pt { border-color: #17957F; }
.rf-node.ifn::before { background: #7A5AA8; }
.rf-node.ifn .rf-hd { background: rgba(122, 90, 168, .14); }
.rf-node.ifn .rf-ic { color: #7A5AA8; }
.rf-node.ifn .rf-pt { border-color: #7A5AA8; }

.rf-hd {
  display: flex; align-items: center; gap: 5px; height: 30px; padding: 0 4px 0 7px;
  border-bottom: 1px solid var(--border); cursor: move; border-radius: 3px 3px 0 0;
}
.rf-ic { font-style: normal; font-size: 11px; flex: 0 0 auto; }
.rf-nm {
  flex: 1 1 auto; min-width: 0; font-size: 11px; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rf-ut { font-style: normal; flex: 0 0 auto; font-size: 9px; color: var(--faint); }
.rf-x {
  flex: 0 0 auto; width: 14px; height: 14px; line-height: 12px; padding: 0;
  font-size: 9px; color: var(--faint); background: none; border: 0; cursor: pointer; font-family: inherit;
}
.rf-x:hover { color: var(--red); }

/* ══════════ 可调 / 传感 主体 ══════════ */
.rf-bd { display: flex; align-items: center; gap: 5px; padding: 5px 8px 0; }
.rf-lb { font-style: normal; flex: 0 0 auto; font-size: 10px; color: var(--muted); }
.rf-num {
  flex: 1 1 auto; min-width: 0; padding: 2px 4px; font-size: 11px; font-family: var(--mono);
  text-align: right; color: var(--text); background: var(--panel);
  border: 1px solid var(--border); border-radius: 3px; outline: none;
}
.rf-num:focus { border-color: var(--accent2); }
.rf-num.sm { width: 64px; flex: 0 0 auto; }
.rf-u { font-style: normal; flex: 0 0 auto; font-size: 9.5px; color: var(--faint); }
.rf-v { flex: 1 1 auto; font-size: 12px; font-weight: 600; color: var(--accent-d); text-align: right; }
.rf-ft { display: flex; align-items: center; gap: 6px; padding: 3px 8px 5px; }
.rf-hint { font-size: 9px; color: var(--faint); }
.rf-warn { margin-left: auto; font-size: 9px; color: #C0562B; }

/* ══════════ IF 分支 ══════════ */
.rf-br {
  position: relative; box-sizing: border-box; height: 46px;
  display: flex; flex-direction: column; justify-content: center; gap: 2px;
  padding: 0 8px 0 10px; border-top: 1px dashed var(--line);
}
.rf-br.act { background: rgba(46, 139, 87, .13); }
.rf-br1 { display: flex; align-items: center; gap: 4px; }
.rf-bt {
  flex: 0 0 auto; font-size: 9.5px; padding: 0 4px; border-radius: 8px; line-height: 15px;
  color: #7A5AA8; background: rgba(122, 90, 168, .14); border: 1px solid rgba(122, 90, 168, .35);
}
.rf-br.else .rf-bt { color: var(--muted); background: var(--bar); border-color: var(--border); }
.rf-sel {
  min-width: 0; padding: 1px 2px; font-size: 10.5px; font-family: inherit; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none;
}
.rf-sel.src { flex: 1 1 auto; width: 60px; }
.rf-sel.op { flex: 0 0 auto; width: 42px; text-align: center; }
.rf-el { flex: 1 1 auto; font-size: 10px; color: var(--faint); }
.rf-bx {
  flex: 0 0 auto; width: 13px; height: 13px; line-height: 11px; padding: 0; font-size: 8.5px;
  color: var(--faint); background: none; border: 0; cursor: pointer; font-family: inherit;
}
.rf-bx:hover { color: var(--red); }
.rf-br2 { display: flex; align-items: center; gap: 6px; padding: 2px 0 0 2px; }
.rf-tg {
  font-size: 9.5px; color: var(--accent-d); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 156px;
}
.rf-tg.none { color: var(--faint); }
.rf-sv { margin-left: auto; font-size: 9px; color: var(--faint); }
.rf-nft {
  box-sizing: border-box; height: 28px; display: flex; align-items: center;
  padding: 0 8px 0 10px; border-top: 1px dashed var(--line);
}
.rf-add {
  padding: 0; font-size: 10px; color: #7A5AA8; background: none;
  border: 0; cursor: pointer; font-family: inherit;
}
.rf-add:hover { text-decoration: underline; }

/* ══════════ 端口 ══════════ */
.rf-pt {
  position: absolute; width: 12px; height: 12px; border-radius: 50%;
  background: var(--panel); border: 2px solid var(--muted); box-sizing: border-box;
  cursor: crosshair; z-index: 2;
}
.rf-pt:hover { border-color: var(--accent-d); background: var(--accent-l); }
.rf-pt.in { left: -7px; top: 50%; transform: translateY(-50%); }
.rf-pt.out { right: -7px; top: 50%; transform: translateY(-50%); }

/* ══════════ 执行 / 校验 / 日志 ══════════ */
.rfe-run {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 6px 8px;
  border: 1px solid var(--border); border-top: 0; background: var(--panel-2);
}
.rf-chk { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); cursor: pointer; }
.rf-chk input { accent-color: var(--accent-d); width: 12px; height: 12px; }
.rf-lb2 { font-style: normal; font-size: 10.5px; color: var(--muted); }
.rf-stat { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--faint); }
.rf-stat .dot { width: 7px; height: 7px; border-radius: 50%; background: #888; }
.rf-stat.on { color: var(--green); }
.rf-stat.on .dot { background: var(--green); animation: rfe-pulse 1s infinite; }
@keyframes rfe-pulse { 50% { opacity: .35; } }

.rfe-iss {
  padding: 5px 8px 7px; border: 1px solid var(--border); border-top: 0;
  background: rgba(188, 59, 48, .06);
}
.iss-h { font-size: 10px; font-weight: 600; color: var(--red); padding-bottom: 3px; }
.iss-r { font-size: 10px; color: var(--muted); line-height: 1.6; }

.rfe-log {
  max-height: 132px; overflow-y: auto; padding: 5px 8px;
  border: 1px solid var(--border); border-top: 0; background: var(--panel);
}
.lg-e { font-size: 10px; color: var(--faint); text-align: center; padding: 4px 0; }
.lg-r { display: flex; gap: 8px; font-size: 10px; padding: 1px 0; }
.lg-r .dim { flex: 0 0 auto; color: var(--faint); }
.lg-t { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.mono { font-family: var(--mono); }
</style>


