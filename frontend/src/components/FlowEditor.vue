<template>
  <div class="flow-canvas" ref="canvasEl"
       @mousedown="onCanvasDown" @wheel.prevent="onWheel" @dragover.prevent @drop="onDrop">
    <div class="viewport" :style="vpStyle">
      <!-- 小组卡片（顶层编排时显示）：与普通工艺节点一致的卡片样式，成员设备折叠为一张卡片并标注台数，双击进入子编排 -->
      <div v-for="g in store.scheme.groups" :key="g.id" v-show="!store.scheme.activeGroupId"
           class="fgroup" :class="{ sel: g.id === store.selectedGroupId }"
           :style="groupStyle(g)"
           @mousedown.stop="onGroupDown(g, $event)"
           @click.stop="store.selectFlowGroup(g.id)"
           @dblclick.stop="store.enterGroup(g.id)"
           @contextmenu.prevent="onGroupContext($event, g)">
        <div class="nh">
          <span class="nhd" :style="{ background: groupColor(g) }"></span>
          <span v-if="groupRenaming !== g.id" class="gname" @click.stop="store.selectFlowGroup(g.id)"
                @dblclick.stop="startGroupRename(g)">{{ g.name }}</span>
          <input v-else class="gname-in" :value="g.name" @click.stop @mousedown.stop
                 @input="g.name = $event.target.value" @keydown.enter.prevent="endGroupRename"
                 @keydown.esc.prevent="endGroupRename" @blur="endGroupRename" />
          <span v-if="g.members && g.members.length" class="ncount" title="小组内设备台数">×{{ g.members.length }}</span>
          <span class="ndel" @mousedown.stop @click.stop="store.removeFlowGroup(g.id)" title="删除小组">✕</span>
        </div>
        <div class="nbody">
          <div v-for="(p, i) in groupPorts(g, 'in')" :key="'gi' + i"
               :class="gphClass(g, 'in', p.material)" :style="portStyle(g, 'in', i)"
               :title="'输入：' + matName(p.material)"
               @mousedown.stop="onGroupPortDown(g, 'in', p, $event)">
            <span class="pdot"></span><span class="plbl">{{ matName(p.material) }}</span>
          </div>
          <div v-for="(p, i) in groupPorts(g, 'out')" :key="'go' + i"
               :class="gphClass(g, 'out', p.material)" :style="portStyle(g, 'out', i)"
               :title="'输出：' + matName(p.material)"
               @mousedown.stop="onGroupPortDown(g, 'out', p, $event)">
            <span class="plbl">{{ matName(p.material) }}</span><span class="pdot"></span>
          </div>
          <div v-if="!g.members || !g.members.length" class="gempty">空组 · 双击进入子编排<br/>拖入设备卡片归入此组</div>
        </div>
      </div>
      <!-- 底层连线：与选中卡片无关的连线保持「卡片在上」的原状 -->
      <svg class="edges" :width="W" :height="H">
        <g v-for="c in bottomConns" :key="c.id">
          <path :d="c.d" :class="[c.gas ? 'pipe-gas' : '']"
                @mousedown.stop @click.stop="store.removeConnection(c.id)" />
          <rect v-if="c.label" :x="c.lx - c.lw / 2 - 3" :y="c.ly - 6" :width="c.lw + 6" height="12" rx="0"
                :fill="c.gas ? '#def4f8' : 'var(--panel)'" pointer-events="none" />
          <text v-if="c.label" :x="c.lx" :y="c.ly" dy="3" text-anchor="middle"
                :class="['edge-label', c.gas ? 'edge-label-gas' : '']">{{ c.label }}</text>
        </g>
        <path v-if="tempConn" :d="tempPath" :class="['temp', dragTarget && dragTarget.valid ? 'ok' : (dragTarget ? 'bad' : '')]" />
      </svg>
      <!-- 顶层连线：选中卡片相关的连线浮到卡片上方，线头接入的出入端口清晰可见 -->
      <svg class="edges-top" :width="W" :height="H">
        <g v-for="c in topConns" :key="c.id">
          <path :d="c.d" :class="[c.gas ? 'pipe-gas' : '']"
                @mousedown.stop @click.stop="store.removeConnection(c.id)" />
          <rect v-if="c.label" :x="c.lx - c.lw / 2 - 3" :y="c.ly - 6" :width="c.lw + 6" height="12" rx="0"
                :fill="c.gas ? '#def4f8' : 'var(--panel)'" pointer-events="none" />
          <text v-if="c.label" :x="c.lx" :y="c.ly" dy="3" text-anchor="middle"
                :class="['edge-label', c.gas ? 'edge-label-gas' : '']">{{ c.label }}</text>
        </g>
      </svg>

      <div v-for="n in visibleNodes" :key="n.id"
           class="fnode" :class="[n.kind, { sel: n.id === store.selectedFlowId, grouped: (n.count || 1) > 1 || !!n.groupId }]"
           :style="nodeStyle(n)">
        <div class="nh" @mousedown="onNodeDragStart(n, $event)" @contextmenu.prevent="onNodeContext($event, n)">
          <span class="nhd" :style="{ background: nodeColor(n) }"></span>
          <span v-if="renaming !== n.id" class="nname" @click.stop="store.selectFlow(n.id)" @dblclick.stop="startRename(n)">{{ n.name }}</span>
          <input v-else class="nname-in" :value="n.name" @click.stop @mousedown.stop
                 @input="n.name = $event.target.value" @keydown.enter.prevent="endRename"
                 @keydown.esc.prevent="endRename" @blur="endRename" />
          <span v-if="(n.count || 1) > 1" class="ncount" title="台数">×{{ n.count }}</span>
          <span class="ndel" @mousedown.stop @click.stop="store.removeFlowNode(n.id)" title="删除节点">✕</span>
        </div>
        <div class="nbody">
          <div v-if="n.kind === 'process'" v-for="(p, i) in n.ports.in" :key="p.id"
               :class="phClass(n, 'in', p.id)" :style="portStyle(n, 'in', i)"
               @mousedown.stop="onPortDown(n, 'in', p.id, $event)"
               @dblclick.stop="onPortDbl(n, 'in', p.id, $event)"
               :title="'输入：' + matName(p.material)">
            <span class="pdot"></span><span class="plbl">{{ matName(p.material) }}</span>
          </div>
          <div v-if="n.kind === 'process'" v-for="(p, i) in n.ports.out" :key="p.id"
               :class="phClass(n, 'out', p.id)" :style="portStyle(n, 'out', i)"
               @mousedown.stop="onPortDown(n, 'out', p.id, $event)"
               @dblclick.stop="onPortDbl(n, 'out', p.id, $event)"
               :title="'输出：' + matName(p.material)">
            <span class="plbl">{{ matName(p.material) }}</span><span class="pdot"></span>
          </div>
          <!-- 添加入口：工辅等无输入端口（或需更多端口）时，点此弹出浮层自由添加输入/输出端口 -->
          <span v-if="n.kind === 'process'" class="addport" title="添加输入/输出端口"
                @mousedown.stop @click.stop="onAddPort(n, $event)">＋</span>
          <div v-if="n.kind === 'material'" :class="phClass(n, 'out', n.ports.out[0].id)" :style="portStyle(n, 'out', 0)"
               @mousedown.stop="onPortDown(n, 'out', n.ports.out[0].id, $event)"
               @dblclick.stop="onPortDbl(n, 'out', n.ports.out[0].id, $event)"
               :title="'输出：' + matName(n.ports.out[0].material)">
            <span class="plbl">{{ matName(n.ports.out[0].material) }}</span><span class="pdot"></span>
          </div>
          <div v-if="n.kind === 'device'" class="devbox">
            <DeviceGlyph :type="devIcon(n.type)" :color="n.metering ? 'var(--muted)' : 'var(--accent2)'" :size="20" />
            <span class="devtag" :class="n.metering ? 'tag-met' : 'tag-adj'">{{ n.metering ? '计量·只读' : '可调·' + (n.setpoint ?? '—') }}</span>
          </div>
        </div>
        <div v-if="estOf(n.id) && n.kind === 'process'" class="nest">≈ {{ fmtCo2(estOf(n.id).co2) }} tCO₂/h</div>
      </div>
    </div>

    <!-- 端口编辑浮层：方向可切换（输入/输出），支持自由增删端口 -->
    <div v-if="editingPort" class="port-pop" :style="popStyle" @mousedown.stop @click.stop>
      <div class="pp-t">端口编辑（{{ editingPort.dir === 'in' ? '输入' : '输出' }}）</div>
      <div class="pp-dir">
        <button :class="{ on: editingPort.dir === 'in' }" @click="setEditDir('in')">输入</button>
        <button :class="{ on: editingPort.dir === 'out' }" @click="setEditDir('out')">输出</button>
      </div>
      <select v-model="editingPort.material" @change="applyPortMaterial">
        <option v-for="m in MATERIALS" :key="m.id" :value="m.id">{{ m.name }}（{{ m.cat }}）</option>
      </select>
      <div class="pp-btns">
        <button @click="addPortHere">＋ 添加{{ editingPort.dir === 'in' ? '输入' : '输出' }}端口</button>
        <button v-if="editingPort.portId" class="danger" @click="removePortHere">－ 删当前</button>
        <button @click="editingPort = null">关闭</button>
      </div>
    </div>

    <!-- 视图缩放/适配/自动布局已统一移至顶栏「编排」工具条；缩放信息显示在命令行窗口 -->

    <!-- 子编排面包屑：进入小组后显示当前组名并提供返回 -->
    <div v-if="store.scheme.activeGroupId" class="group-crumb">
      <button class="crumb-back" @click="store.exitGroup()">← 返回全部流程</button>
      <span class="crumb-name">小组：{{ activeGroupName }}</span>
      <span class="crumb-hint">双击成员卡片可编辑 · 拖入新设备自动归入本组</span>
    </div>

    <div class="flow-legend">
      <span><i class="ln"></i>固体/液体物料</span>
      <span><i class="ln gas"></i>气体/能源管道</span>
      <span class="muted">双击端口改物料 · 拖端口连线 · 点连线删除 · 双击小组卡片进入子编排</span>
    </div>

    <div v-if="!visibleNodes.length" class="flow-empty">
      <template v-if="store.scheme.activeGroupId">该小组内暂无设备。从左侧拖入设备卡片归入本组，或双击小组卡片从外部画布把设备拖进来。</template>
      <template v-else>画布为空。从左侧「主工艺线 / 设备 / 原料」拖入节点，或点击顶部工具条「编排 → 长流程示例 / 短流程示例」一键载入。</template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'
import { MATERIALS, MATERIAL_MAP, PROCESS_MAP, DEVICE_MAP, materialFamily } from '../data/flowLibrary'
import DeviceGlyph from './DeviceGlyph.vue'
import { openContextMenu } from '../composables/contextMenu'
import { openScanDialog } from '../stores/scan'

const store = useSimStore()
const canvasEl = ref(null)
const W = 4000, H = 3000
const NW = 196, HEADER = 32, PORT_Y0 = 46, GAP = 24

const drag = ref(null)          // {type:'node'|'pan'|'connect'|'group', ...}
const tempConn = ref(null)      // {x,y} 画布坐标
const editingPort = ref(null)   // {nodeId, dir, portId, material, sx, sy}
const dragTarget = ref(null)    // 连线拖拽中悬停的合法/非法目标端口 {nodeId, dir, portId, valid}
const renaming = ref('')        // 正在内联重命名的节点 id（空表示无）
const groupRenaming = ref('')   // 正在内联重命名的小组 id（空表示无）

// 当前画布可见节点：顶层小组折叠为一张卡片，成员节点不单独平铺；小组子编排仅显示该组成员
const visibleNodes = computed(() => {
  if (!store.scheme.activeGroupId) return store.scheme.nodes.filter((n) => !n.groupId)
  const g = store.scheme.groups.find((x) => x.id === store.scheme.activeGroupId)
  if (!g) return store.scheme.nodes
  const ids = new Set(g.members || [])
  return store.scheme.nodes.filter((n) => ids.has(n.id))
})
const activeGroupName = computed(() => {
  const g = store.scheme.groups.find((x) => x.id === store.scheme.activeGroupId)
  return g ? g.name : ''
})

function matName(id) { return (MATERIAL_MAP[id] && MATERIAL_MAP[id].name) || id }
function matUnit(id) { return (MATERIAL_MAP[id] && MATERIAL_MAP[id].unit) || '' }
const GAS_UNITS = new Set(['Nm³', 'GJ'])
const GAS_IDS = new Set(['oxygen', 'ngas', 'ldg', 'cog', 'bfg', 'steam', 'waste_heat', 'co2', 'air'])
function isGasMaterial(id) { return GAS_IDS.has(id) || GAS_UNITS.has(matUnit(id)) }
function devIcon(type) { const d = DEVICE_MAP[type]; return d ? d.icon : 'gauge' }
function nodeColor(n) {
  if (n.kind === 'material') return (MATERIAL_MAP[n.type] && MATERIAL_MAP[n.type].color) || '#888'
  if (n.kind === 'device') return n.metering ? 'var(--muted)' : 'var(--accent2)'
  const t = PROCESS_MAP[n.type]
  if (!t) return '#888'
  return t.route === 'steel' ? 'var(--accent2)' : t.route === 'aux' ? 'var(--yellow)' : 'var(--green)'
}
function estOf(id) { const r = store.schemeResult; return r.nodes[id] }
function fmtCo2(v) { return Number(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }

const vpStyle = computed(() => ({
  transform: `translate(${store.flowTf.tx}px, ${store.flowTf.ty}px) scale(${store.flowTf.scale})`,
  transformOrigin: '0 0', width: W + 'px', height: H + 'px', position: 'absolute', top: '0', left: '0',
}))

function nodeH(n) {
  if (n.kind === 'device') return HEADER + 56
  // 端口为绝对定位，节点高度需容纳：头部 + 端口基准偏移 + 各端口间距 + 端口高 + 下边距
  const cnt = n.kind === 'material' ? 1 : Math.max(n.ports.in.length, n.ports.out.length, 1)
  return HEADER + (PORT_Y0 - 7) + (cnt - 1) * GAP + 16 + 12
}
function nodeStyle(n) {
  return { left: n.x + 'px', top: n.y + 'px', width: NW + 'px', minHeight: nodeH(n) + 'px' }
}
// 小组对外端口：优先取成员节点同向端口（与连线锚点一致），否则回退小组声明的 inputs/outputs
function groupPorts(g, dir) {
  const m = (g.members || []).map((id) => store.scheme.nodes.find((n) => n.id === id)).filter(Boolean)
  if (m.length) {
    const p = (m[0].ports && m[0].ports[dir]) || []
    if (p.length) return p
  }
  return (dir === 'in' ? g.inputs : g.outputs) || []
}
// 小组卡片配色：取首个成员节点的品类色（与节点卡片一致），空组用默认蓝色
function groupColor(g) {
  const m = (g.members || []).map((id) => store.scheme.nodes.find((n) => n.id === id)).filter(Boolean)
  return m.length ? nodeColor(m[0]) : 'var(--accent2)'
}
// 小组卡片位置/大小（画布坐标）：位置沿用成员节点包围盒左上角（保证连线锚点与布局稳定），
// 尺寸与普通工艺节点一致（按端口数量自适应高度）；空组用组锚点默认尺寸
function groupBox(g) {
  const members = store.scheme.nodes.filter((n) => g.members && g.members.includes(n.id))
  let x, y
  if (members.length) {
    x = Math.min(...members.map((n) => n.x)) - 22
    y = Math.min(...members.map((n) => n.y)) - 48
  } else {
    x = g.x - 22
    y = g.y - 26
  }
  const cnt = Math.max(groupPorts(g, 'in').length, groupPorts(g, 'out').length, 1)
  const h = HEADER + (PORT_Y0 - 7) + (cnt - 1) * GAP + 16 + 12
  return { x, y, w: NW, h }
}
function groupStyle(g) {
  const b = groupBox(g)
  return {
    left: b.x + 'px', top: b.y + 'px',
    width: b.w + 'px', height: b.h + 'px',
  }
}
// 顶层画布中，节点归属的小组（子编排内返回 null）
function groupOfNode(id) {
  if (store.scheme.activeGroupId) return null
  for (const g of store.scheme.groups) {
    if (g.members && g.members.includes(id)) return g
  }
  return null
}
// 小组对外连线锚点：入=左边界、出=右边界，与卡片第一行端口平齐（折叠后整体连线）
function groupAnchor(g, dir) {
  const b = groupBox(g)
  const y = b.y + (PORT_Y0 - 7) + 6
  return dir === 'in' ? { x: b.x, y } : { x: b.x + b.w, y }
}
// 小组端口高亮：连线拖拽悬停时，方向正确且物料匹配的对外端口高亮（与节点端口一致）
function gphClass(g, dir, material) {
  const d = drag.value
  if (!d || d.type !== 'connect') return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  const needDir = d.fromDir === 'out' ? 'in' : 'out'
  if (dir !== needDir) return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  const dm = dragOutMaterial()
  const ok = !!dm && materialFamily(dm) === materialFamily(material)
  return ['ph', dir === 'in' ? 'port-in' : 'port-out', ok ? 'ph-ok' : 'ph-bad']
}
// 连线端点：顶层画布中端点属于小组时锚定到小组卡片边界（小组作为一个整体连线），
// 否则（独立节点或子编排内部）锚定到节点端口
function connEndpoint(n, dir, portId) {
  const g = groupOfNode(n.id)
  if (g) return groupAnchor(g, dir)
  return portPos(n, dir, portId)
}
function portTop(n, i) { return PORT_Y0 + i * GAP - 7 }
function portStyle(n, dir, i) {
  return dir === 'in'
    ? { left: '8px', top: portTop(n, i) + 'px' }
    : { right: '8px', top: portTop(n, i) + 'px' }
}
function portPos(n, dir, portId) {
  const arr = dir === 'in' ? n.ports.in : n.ports.out
  const i = arr.findIndex((p) => p.id === portId)
  // 锚点取圆点中心：x 在框内(8px+半径)，y 对齐实际圆点中心(头部约32 + 端口基准39 + 半径~5.5)
  const x = dir === 'in' ? n.x + 13 : n.x + NW - 13
  const y = n.y + 76 + i * GAP
  return { x, y }
}
function hashCode(s) { let h = 0; for (let i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0 } return Math.abs(h) }
// 正交路径的偏移通道：多根同向线错开，避免重叠
function orthoLane(connId, feedback) {
  if (feedback) return { outward: 140, tag: 'high-feedback' }
  const lane = hashCode(connId) % 5
  const offsets = [80, 110, 140, 170, 200]
  return { outward: offsets[lane], tag: 'lane-' + lane }
}
// 生成连接路径：编排模式下允许斜线，直接用直线连接源/目标端口
function orthoPath(s, t, outward) {
  return `M ${s.x} ${s.y} L ${t.x} ${t.y}`
}
const connPaths = computed(() => {
  const out = []
  const visIds = new Set(visibleNodes.value.map((n) => n.id))
  for (const c of store.scheme.connections) {
    const fn = store.scheme.nodes.find((n) => n.id === c.from)
    const tn = store.scheme.nodes.find((n) => n.id === c.to)
    if (!fn || !tn) continue
    // 子编排视图只显示组内连线
    if (store.scheme.activeGroupId && (!visIds.has(fn.id) || !visIds.has(tn.id))) continue
    // 顶层视图：同组内部的连线不在顶层显示（进入子编排才可见），小组作为一个整体对外连线
    if (!store.scheme.activeGroupId) {
      const fg = groupOfNode(fn.id), tg = groupOfNode(tn.id)
      if (fg && fg === tg) continue
    }
    const s = connEndpoint(fn, 'out', c.fromPort)
    const t = connEndpoint(tn, 'in', c.toPort)
    const el = orthoLane(c.id, c.feedback)
    const d = orthoPath(s, t, el.outward)
    const lx = ((s.x + t.x) / 2).toFixed(1)
    const ly = ((s.y + t.y) / 2).toFixed(1)
    const label = matName(c.material)
    const gas = isGasMaterial(c.material)
    const lw = [...label].reduce((w, ch) => w + (/[\u4e00-\u9fff]/.test(ch) ? 9 : 5.5), 0)
    // 与选中卡片相连的连线浮到顶层（卡片上方），便于看清接入的出入口
    const top = !!store.selectedFlowId && (fn.id === store.selectedFlowId || tn.id === store.selectedFlowId)
    out.push({ id: c.id, d, label, gas, feedback: c.feedback, lane: el.tag, lx, ly, lw, top })
  }
  return out
})
// 选中卡片相关连线（浮到卡片上方）与其余连线（保持卡片在上）分开渲染
const topConns = computed(() => connPaths.value.filter((c) => c.top))
const bottomConns = computed(() => connPaths.value.filter((c) => !c.top))
const tempPath = computed(() => {
  if (!tempConn.value || !drag.value || drag.value.type !== 'connect') return ''
  const srcN = store.scheme.nodes.find((n) => n.id === drag.value.from)
  if (!srcN) return ''
  const src = connEndpoint(srcN, drag.value.fromDir, drag.value.fromPort)
  const t = tempConn.value
  // 拖拽中的临时连线（允许斜线）
  const d = orthoPath(src, t)
  return d
})

function toCanvas(e) {
  const r = canvasEl.value.getBoundingClientRect()
  return { x: (e.clientX - r.left - store.flowTf.tx) / store.flowTf.scale, y: (e.clientY - r.top - store.flowTf.ty) / store.flowTf.scale }
}

function onCanvasDown(e) { drag.value = { type: 'pan', lastX: e.clientX, lastY: e.clientY } }

function onNodeDragStart(n, e) {
  e.stopPropagation()
  // 点击/拖拽卡片即选中，使该卡片相关的连线浮到卡片上方，方便看清接入的出入口
  if (store.selectedFlowId !== n.id) store.selectFlow(n.id)
  const c = toCanvas(e)
  drag.value = { type: 'node', id: n.id, ox: c.x - n.x, oy: c.y - n.y }
}
function onPortDown(n, dir, portId, e) {
  e.stopPropagation()
  drag.value = { type: 'connect', from: n.id, fromDir: dir, fromPort: portId, lastX: e.clientX, lastY: e.clientY }
  const p = portPos(n, dir, portId)
  tempConn.value = { x: p.x, y: p.y }
  dragTarget.value = null
}
// 从小组卡片端口拖线：映射到成员节点同名端口发起连线（渲染时锚定到小组卡片边界）
function onGroupPortDown(g, dir, port, e) {
  const m = (g.members || []).map((id) => store.scheme.nodes.find((n) => n.id === id)).filter(Boolean)[0]
  if (!m || !m.ports || !m.ports[dir]) return
  const p = m.ports[dir].find((x) => x.material === port.material) || m.ports[dir][0]
  if (p) onPortDown(m, dir, p.id, e)
}
function onPortDbl(n, dir, portId, e) {
  e.stopPropagation()
  const c = toCanvas(e)
  // portDir 记录端口所在侧（双击的侧），方向切换只影响后续添加的端口，改/删仍作用于当前端口
  editingPort.value = { nodeId: n.id, dir, portDir: dir, portId, material: portMaterial(n, dir, portId), sx: c.x * store.flowTf.scale + store.flowTf.tx + 12, sy: c.y * store.flowTf.scale + store.flowTf.ty + 12 }
}
// 卡片上的「＋」入口：无输入端口时默认添加输入侧，否则默认输出侧；portId 为空表示仅添加模式
function onAddPort(n, e) {
  e.stopPropagation()
  const c = toCanvas(e)
  const dir = n.ports.in.length === 0 ? 'in' : 'out'
  editingPort.value = { nodeId: n.id, dir, portDir: null, portId: null, material: defaultPortMaterial(n, dir), sx: c.x * store.flowTf.scale + store.flowTf.tx + 12, sy: c.y * store.flowTf.scale + store.flowTf.ty + 12 }
}
function setEditDir(dir) {
  if (editingPort.value) editingPort.value.dir = dir
}
function defaultPortMaterial(n, dir) {
  const t = PROCESS_MAP[n.type]
  if (dir === 'out' && t && t.mainOut) return t.mainOut
  if (dir === 'in' && t && t.mainIn) return t.mainIn
  if (dir === 'in') return 'electricity'   // 工辅/驱动类常见输入介质
  return MATERIALS.length ? MATERIALS[0].id : 'hot_metal'
}
function portMaterial(n, dir, portId) {
  const arr = dir === 'in' ? n.ports.in : n.ports.out
  const p = arr.find((x) => x.id === portId)
  return p ? p.material : ''
}
function applyPortMaterial() {
  // 仅添加模式（卡片＋入口，portId 为空）不改现有端口，物料用于新端口
  if (!editingPort.value || !editingPort.value.portId) return
  store.updatePortMaterial(editingPort.value.nodeId, editingPort.value.portDir, editingPort.value.portId, editingPort.value.material)
}
function addPortHere() {
  if (!editingPort.value) return
  store.addPort(editingPort.value.nodeId, editingPort.value.dir, editingPort.value.material || 'hot_metal')
}
function removePortHere() {
  if (!editingPort.value || !editingPort.value.portId) return
  store.removePort(editingPort.value.nodeId, editingPort.value.portDir, editingPort.value.portId)
  editingPort.value = null
}
const popStyle = computed(() => editingPort.value ? { left: editingPort.value.sx + 'px', top: editingPort.value.sy + 'px' } : {})

function hitPort(c) {
  for (const n of visibleNodes.value) {
    const dirs = n.kind === 'material' ? ['out'] : ['in', 'out']
    for (const dir of dirs) {
      const arr = dir === 'in' ? n.ports.in : n.ports.out
      for (const p of arr) {
        const pos = portPos(n, dir, p.id)
        if (Math.hypot(pos.x - c.x, pos.y - c.y) < 12) return { nodeId: n.id, dir, portId: p.id, node: n }
      }
    }
  }
  // 顶层折叠的小组卡片整体作为连线目标：释放点落在卡片内即可连线
  // （落到成员节点的对应端口上，连线端点渲染时统一锚定到小组卡片边界）
  if (!store.scheme.activeGroupId) {
    for (const g of store.scheme.groups) {
      const b = groupBox(g)
      if (c.x < b.x || c.x > b.x + b.w || c.y < b.y || c.y > b.y + b.h) continue
      const m = (g.members || []).map((id) => store.scheme.nodes.find((n) => n.id === id)).filter(Boolean)
      if (!m.length) continue
      const dir = c.x < b.x + b.w / 2 ? 'in' : 'out'
      const arr = (m[0].ports && m[0].ports[dir]) || []
      if (!arr.length) continue
      return { nodeId: m[0].id, dir, portId: arr[0].id, node: m[0], viaGroup: true }
    }
  }
  return null
}

// 当前拖拽（连线）源端口的物料
function dragOutMaterial() {
  const d = drag.value
  if (!d || d.type !== 'connect') return null
  const n = store.scheme.nodes.find((x) => x.id === d.from)
  if (!n) return null
  const arr = d.fromDir === 'out' ? n.ports.out : n.ports.in
  const p = arr.find((x) => x.id === d.fromPort)
  return p ? p.material : null
}
// 判定某端口若作为「目标」是否合法：方向正确 + 非自连 + 物料类型匹配（同族即匹配）
function evalDragTarget(hit) {
  const d = drag.value
  if (!hit || !d || d.type !== 'connect') return null
  const needDir = d.fromDir === 'out' ? 'in' : 'out'
  if (hit.dir !== needDir) return { ...hit, valid: false }
  if (hit.nodeId === d.from) return { ...hit, valid: false }
  const tn = store.scheme.nodes.find((x) => x.id === hit.nodeId)
  if (!tn) return { ...hit, valid: false }
  const tp = (hit.dir === 'in' ? tn.ports.in : tn.ports.out).find((x) => x.id === hit.portId)
  if (!tp) return { ...hit, valid: false }
  const dm = dragOutMaterial()
  const valid = !!dm && materialFamily(dm) === materialFamily(tp.material)
  return { ...hit, valid }
}
// 端口渲染类：连线拖拽中，所有「方向正确且类型匹配」的目标端口高亮绿，
// 方向正确但类型不匹配的高亮红；其余正常。
function phClass(n, dir, portId) {
  const d = drag.value
  if (!d || d.type !== 'connect') return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  const needDir = d.fromDir === 'out' ? 'in' : 'out'
  if (dir !== needDir) return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  if (n.id === d.from) return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  const dm = dragOutMaterial()
  const arr = dir === 'in' ? n.ports.in : n.ports.out
  const p = arr.find((x) => x.id === portId)
  if (!p) return ['ph', dir === 'in' ? 'port-in' : 'port-out']
  const ok = !!dm && materialFamily(dm) === materialFamily(p.material)
  return ['ph', dir === 'in' ? 'port-in' : 'port-out', ok ? 'ph-ok' : 'ph-bad']
}

function onMove(e) {
  const d = drag.value
  if (!d) return
  if (d.type === 'pan') {
    store.flowTf.tx += e.clientX - d.lastX; store.flowTf.ty += e.clientY - d.lastY
    d.lastX = e.clientX; d.lastY = e.clientY
  } else if (d.type === 'node') {
    const c = toCanvas(e)
    store.moveFlowNode(d.id, Math.round(c.x - d.ox), Math.round(c.y - d.oy))
  } else if (d.type === 'group') {
    // 拖动小组：整体平移全部成员节点（保持组内相对位置）
    store.moveFlowGroup(d.id, (e.clientX - d.lastX) / store.flowTf.scale, (e.clientY - d.lastY) / store.flowTf.scale)
    d.lastX = e.clientX; d.lastY = e.clientY
  } else if (d.type === 'connect') {
    tempConn.value = toCanvas(e)
    dragTarget.value = evalDragTarget(hitPort(tempConn.value))
  }
}
function onUp(e) {
  const d = drag.value
  if (d && d.type === 'connect') {
    const c = toCanvas(e)
    const hit = hitPort(c)
    const tgt = evalDragTarget(hit)   // 已含方向/自连/类型匹配判定
    if (tgt && tgt.valid) {
      // 归一化：out -> in
      const outIsSrc = d.fromDir === 'out'
      const outNode = outIsSrc ? d.from : tgt.nodeId
      const outPortId = outIsSrc ? d.fromPort : tgt.portId
      const inNode = outIsSrc ? tgt.nodeId : d.from
      const inPortId = outIsSrc ? tgt.portId : d.fromPort
      const fn = store.scheme.nodes.find((n) => n.id === outNode)
      const fp = fn.ports.out.find((p) => p.id === outPortId)
      const mat = fp ? fp.material : 'hot_metal'
      const tn = store.scheme.nodes.find((n) => n.id === inNode)
      const fb = tn.x < fn.x
      store.addConnection(outNode, outPortId, inNode, inPortId, mat, fb)
    } else if (hit && hit.nodeId !== d.from) {
      // 命中了端口但方向/类型不匹配 -> 给出明确提示
      const needDir = d.fromDir === 'out' ? 'in' : 'out'
      if (hit.dir !== needDir) {
        store.toast = '连线方向错误：请从「输出」端口拖向另一节点的「输入」端口'
      } else {
        const tn = store.scheme.nodes.find((x) => x.id === hit.nodeId)
        const tp = (hit.dir === 'in' ? tn.ports.in : tn.ports.out).find((x) => x.id === hit.portId)
        const dm = dragOutMaterial()
        store.toast = `物料类型不匹配，不能连线：输出「${matName(dm)}」→ 输入「${matName(tp ? tp.material : '')}」`
      }
    }
    tempConn.value = null
    dragTarget.value = null
  }
  drag.value = null
}
function onWheel(e) {
  const r = canvasEl.value.getBoundingClientRect()
  const mx = e.clientX - r.left, my = e.clientY - r.top
  const factor = e.deltaY < 0 ? 1.1 : 0.9
  // 以光标为锚点缩放（逻辑委托给 store，供顶栏工具条复用）
  store.flowZoom(factor, mx, my)
}
function onDrop(e) {
  const raw = e.dataTransfer.getData('application/flow-node')
  if (!raw) return
  let payload
  try { payload = JSON.parse(raw) } catch { return }
  const c = toCanvas(e)
  store.addFlowNode(payload.kind, payload.type, Math.round(c.x - NW / 2), Math.round(c.y - 20))
}
function onKey(e) {
  const tag = (e.target.tagName || '').toLowerCase()
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return
    // 优先删除选中的小组；组内子编排中则删除选中的成员节点
    if (store.selectedGroupId) { store.removeFlowGroup(store.selectedGroupId); return }
    if (store.selectedFlowId) store.removeFlowNode(store.selectedFlowId)
  }
  if (e.key === 'F2') {
    if (store.selectedGroupId) {
      const g = store.scheme.groups.find((x) => x.id === store.selectedGroupId)
      if (g) startGroupRename(g)
      return
    }
    if (store.selectedFlowId) {
      const n = store.scheme.nodes.find((x) => x.id === store.selectedFlowId)
      if (n) startRename(n)
    }
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
    e.preventDefault()
    if (store.selectedGroupId) {
      const g = store.scheme.groups.find((x) => x.id === store.selectedGroupId)
      if (g) duplicateGroup(g)
      return
    }
    if (store.selectedFlowId) {
      const n = store.scheme.nodes.find((x) => x.id === store.selectedFlowId)
      if (n) duplicateNode(n)
    }
  }
  if (e.key === 'Escape') { editingPort.value = null; drag.value = null; tempConn.value = null; renaming.value = ''; groupRenaming.value = '' }
}

/* 内联重命名：双击名称或右键「重命名」进入编辑，回车/Esc/失焦完成 */
function startRename(n) {
  store.selectFlow(n.id)
  renaming.value = n.id
  nextTick(() => {
    const inp = canvasEl.value && canvasEl.value.querySelector('.nname-in')
    if (inp) { inp.focus(); inp.select() }
  })
}
function endRename() { renaming.value = '' }

/* 复制节点：同类型新建一个偏移节点，并继承参数/配比 */
function duplicateNode(n) {
  const id = store.addFlowNode(n.kind, n.type, n.x + 28, n.y + 28)
  if (!id) return
  const nn = store.scheme.nodes.find((x) => x.id === id)
  if (nn && n.params) nn.params = { ...n.params }
  if (nn && n.recipe) nn.recipe = JSON.parse(JSON.stringify(n.recipe))
  store.selectFlow(id)
}

/* ---- 工艺设备小组（子编排）交互 ---- */
function onGroupDown(g, e) {
  e.stopPropagation()
  // 点击/拖拽小组卡片即选中，使该小组相关连线浮到卡片上方
  store.selectFlowGroup(g.id)
  drag.value = { type: 'group', id: g.id, lastX: e.clientX, lastY: e.clientY }
}
function startGroupRename(g) {
  store.selectFlowGroup(g.id)
  groupRenaming.value = g.id
  nextTick(() => {
    const inp = canvasEl.value && canvasEl.value.querySelector('.gname-in')
    if (inp) { inp.focus(); inp.select() }
  })
}
function endGroupRename() { groupRenaming.value = '' }
/* 复制小组：连同全部成员节点与组内连线一起复制（复用 store 逻辑） */
function duplicateGroup(g) {
  const newId = store.duplicateFlowGroup(g.id)
  if (newId) store.selectFlowGroup(newId)
}
/* 小组右键菜单：进入子编排 / 选中 / 重命名 / 复制 / 删除 */
function onGroupContext(e, g) {
  e.preventDefault()
  const items = [
    { label: '进入子编排', icon: 'folder-open', action: () => store.enterGroup(g.id) },
    { label: '选中 / 聚焦小组', icon: 'target', action: () => store.selectFlowGroup(g.id) },
    { sep: true },
    { label: '重命名', icon: 'pencil', accel: 'F2', action: () => startGroupRename(g) },
    { label: '复制小组', icon: 'copy', accel: 'Ctrl+D', action: () => duplicateGroup(g) },
    { label: '删除小组', icon: 'trash', accel: 'Del', danger: true, action: () => store.removeFlowGroup(g.id) },
  ]
  openContextMenu(e.clientX, e.clientY, items)
}

/* 右键上下文菜单（对标 Simulink / MATLAB 节点右键）：选中 / 参数扫描 / 重命名 / 复制 / 删除 */
function onNodeContext(e, n) {
  e.preventDefault()
  const items = [
    { label: '选中 / 聚焦节点', icon: 'target', action: () => store.selectFlow(n.id) },
  ]
  if (n.kind === 'process' && n.type) {
    items.push({ label: '参数敏感性扫描', icon: 'search', action: () => openScanDialog(n.type) })
  }
  items.push({ sep: true })
  items.push({ label: '重命名', icon: 'pencil', accel: 'F2', action: () => startRename(n) })
  items.push({ label: '复制节点', icon: 'copy', accel: 'Ctrl+D', action: () => duplicateNode(n) })
  items.push({ label: '删除节点', icon: 'trash', accel: 'Del', danger: true, action: () => store.removeFlowNode(n.id) })
  openContextMenu(e.clientX, e.clientY, items)
}

// 上报画布像素尺寸，供 store 的「适配视图/缩放」以画布中心为锚点计算
function applySize() { if (canvasEl.value) store.setFlowCanvasSize(canvasEl.value.clientWidth, canvasEl.value.clientHeight) }

onMounted(() => {
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  window.addEventListener('keydown', onKey)
  applySize()
  window.addEventListener('resize', applySize)
  // 进入编排：自动布局后做"适应视图"，将全部节点缩放居中显示
  nextTick(() => { applySize(); store.flowZoomFit() })
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', applySize)
})
</script>

<style scoped>
.flow-canvas { position: absolute; inset: 0; overflow: hidden; background:
  radial-gradient(circle at 1px 1px, rgba(0,90,158,.08) 1px, transparent 0) 0 0 / 22px 22px,
  var(--bg); cursor: grab; }
.flow-canvas:active { cursor: grabbing; }
.viewport { }
.edges, .edges-top { position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible; }
/* 顶层连线：与选中卡片相连，浮在卡片上方（z-index:2 高于卡片、低于端口 .ph 的 3，
   线头锚点圆点清晰可见；点击连线仍可删除） */
.edges-top { z-index: 2; }
.edges path, .edges-top path { fill: none; stroke: var(--green); stroke-width: 2; pointer-events: stroke; cursor: pointer; }
/* 气体管道：青色虚线 + 流动动画（更粗更亮） */
.edges path.pipe-gas, .edges-top path.pipe-gas { stroke: var(--gas); stroke-width: 3; stroke-dasharray: 12 8; animation: gasFlow 1s linear infinite; opacity: 0.85; }
.edges path.pipe-gas.fb, .edges-top path.pipe-gas.fb { stroke: var(--yellow); stroke-dasharray: 12 8; animation: gasFlowReverse 1s linear infinite; }
@keyframes gasFlow { to { stroke-dashoffset: -40; } }
@keyframes gasFlowReverse { to { stroke-dashoffset: 40; } }
.edges path.temp { stroke: var(--accent2); stroke-width: 2; stroke-dasharray: 4 4; pointer-events: none; }
.edges path.temp.ok { stroke: var(--green); }
.edges path.temp.bad { stroke: var(--red); }
/* 管道物料标签 — 与工艺端口标签 .plbl 完全统一：9px / muted / panel 背景 */
.edge-label { font-size: 9px; fill: var(--muted); font-family: var(--ui); letter-spacing: .2px; font-weight: 400;
  pointer-events: none; user-select: none; }
.edge-label-gas { fill: var(--gas); }
/* 工艺设备小组卡片：与普通工艺节点一致的卡片样式（成员折叠为一张卡片，标注台数），双击进入子编排 */
.fgroup { position: absolute; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: var(--shadow); z-index: 1; cursor: grab; user-select: none; overflow: hidden; }
.fgroup:active { cursor: grabbing; }
.fgroup:hover { border-color: var(--yellow); }
.fgroup.sel { border-color: var(--accent2); box-shadow: 0 0 0 1px rgba(26,127,212,.5); }
.fgroup .gname { flex: 1; font-size: 12px; white-space: normal; word-break: break-all; line-height: 1.35;
  overflow: hidden; cursor: pointer; }
.fgroup .gname-in { flex: 1; min-width: 0; font-size: 12px; background: var(--bg); color: var(--text);
  border: 1px solid var(--accent); border-radius: 4px; padding: 1px 5px; outline: none; }
.fgroup .gempty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: var(--muted); font-size: 11px; line-height: 1.8; text-align: center; pointer-events: none; }
/* 子编排面包屑：小组内返回/标题提示 */
.group-crumb { position: absolute; top: 12px; left: 12px; z-index: 25; display: flex; align-items: center; gap: 10px;
  background: rgba(255,255,255,.92); border: 1px solid var(--border); border-radius: 8px; padding: 5px 10px; box-shadow: var(--shadow); }
.group-crumb .crumb-back { font-size: 12px; padding: 3px 9px; }
.group-crumb .crumb-name { font-size: 12px; font-weight: 600; color: var(--accent2); }
.group-crumb .crumb-hint { font-size: 10px; color: var(--muted); }
.fnode { position: absolute; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: var(--shadow); user-select: none; }
.fnode.sel { border-color: var(--accent2); box-shadow: 0 0 0 1px rgba(26,127,212,.5); }
.fnode.device { border-style: dashed; }
.fnode.material { border-color: var(--green); }
/* 小组（同设备多台）：黄色描边标记 */
.fnode.grouped { border: 2px solid var(--yellow); border-style: dashed; }
.fnode.grouped:hover { box-shadow: 0 0 0 1px rgba(230,184,0,.55); }
.ncount { font-size: 10px; font-weight: 700; color: #57410a; background: var(--yellow);
  border-radius: 4px; padding: 1px 5px; flex: 0 0 auto; }
.nh { display: flex; align-items: center; gap: 7px; padding: 7px 9px; cursor: move; border-bottom: 1px solid var(--line); }
.nh .nhd { width: 9px; height: 9px; border-radius: 3px; flex: 0 0 auto; }
.nname { flex: 1; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.nname-in { flex: 1; min-width: 0; font-size: 12px; background: var(--bg); color: var(--text); border: 1px solid var(--accent); border-radius: 4px; padding: 1px 5px; outline: none; }
.ndel { color: var(--muted); cursor: pointer; font-size: 12px; padding: 0 2px; }
.ndel:hover { color: var(--red); }
.nbody { position: relative; padding: 6px 0; }
.addport { position: absolute; right: 6px; top: 3px; font-size: 12px; line-height: 1; color: var(--muted);
  cursor: pointer; padding: 2px 4px; z-index: 3; border: 1px solid transparent; border-radius: 4px; }
.addport:hover { color: var(--accent); border-color: var(--border); background: var(--panel-2); }
/* 端口浮在卡片上方：连线的线头锚点（圆点）与物料标签不被卡片盖住，
   一眼看出连线接入了哪个出入口；非端口处连线仍位于卡片下方（现状不变） */
.ph { position: absolute; display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); white-space: nowrap; cursor: crosshair;
  max-width: calc(100% - 16px); overflow: hidden; z-index: 3; }
.ph.port-in { flex-direction: row; }
.ph.port-out { flex-direction: row; }
.pdot { width: 11px; height: 11px; border-radius: 50%; background: var(--panel); border: 2px solid var(--accent2); flex: 0 0 auto;
  box-shadow: 0 0 0 2px var(--panel-2), var(--shadow); }
.port-out .pdot { border-color: var(--green); }
/* 连线拖拽中的目标合法性高亮：匹配绿、不匹配红 */
.ph-ok .pdot { border-color: var(--green); background: var(--green); box-shadow: 0 0 0 3px rgba(63,174,122,.30); }
.ph-bad .pdot { border-color: var(--red); background: var(--red); box-shadow: 0 0 0 3px rgba(199,90,82,.30); }
.plbl { font-size: 9px; background: var(--panel); padding: 0 3px; min-width: 0; overflow: hidden; text-overflow: ellipsis;
  border: 1px solid var(--border); border-radius: 4px; box-shadow: var(--shadow); }
.devbox { display: flex; align-items: center; gap: 8px; padding: 8px 10px; }
.devtag { font-size: 10px; color: var(--muted); }
.nest { position: absolute; right: 8px; bottom: 4px; font-size: 10px; color: var(--muted); font-family: ui-monospace, monospace; }
.port-pop { position: absolute; z-index: 30; background: var(--panel); border: 1px solid var(--accent2); border-radius: 8px;
  padding: 8px; width: 200px; box-shadow: var(--shadow); }
.pp-t { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.pp-dir { display: flex; gap: 4px; margin-bottom: 6px; }
.pp-dir button { flex: 1; padding: 3px 0; font-size: 11px; }
.pp-dir button.on { background: var(--accent); color: #fff; border-color: var(--accent); }
.pp-btns { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.pp-btns button { padding: 4px 8px; font-size: 12px; }
.flow-legend { position: absolute; bottom: 12px; left: 12px; display: flex; gap: 14px; align-items: center; z-index: 20;
  background: rgba(255,255,255,.9); border: 1px solid var(--border); border-radius: 8px; padding: 5px 10px; font-size: 10px; color: var(--muted); box-shadow: var(--shadow); }
.flow-legend .ln { display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--green); vertical-align: middle; margin-right: 4px; }
.flow-legend .ln.gas { border-top: 3px dashed var(--gas); }
.flow-empty { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); max-width: 460px; text-align: center;
  color: var(--muted); font-size: 12px; line-height: 1.7; z-index: 5; }
</style>
