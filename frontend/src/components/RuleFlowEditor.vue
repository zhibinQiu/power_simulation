<!-- ============ 规则控制 · 可编排视图 ============
     与「流程编排 FlowEditor」完全不同的语义：
       流程编排 = 物料流 / 工艺拓扑（节点=工艺·物料·设备，连线=物流）
       规则编排 = 控制逻辑（节点=可调/传感/IF/循环，连线=执行顺序）
     四类模块用四种颜色区分：可调（可设定数值）· 传感（只读观测）· IF 条件（if/elif/else 分支）·
     循环（重复跑下游）。
     AND / OR 不是模块：它们是「IF 分支」内部多行条件之间的连接词 —— 一条分支可以写多条比较
     （如「机柜温度 ≥ 25 并且 < 50」），行首下拉切「并且 / 或者」，AND 优先于 OR 归约。
     左侧模块列表拖入画布即建节点（也可点工具条按钮）；IF 模块默认 if-else，可手动添加 elif，
     每条分支也可单条删除（至少保留一条）。
     每个条件分支的输出端口可继续往下连接可调或传感节点并进行设置（只有可调可设定数值）；
     同一个输出端口可以连接多个下游模块，命中该分支时这些下游并列推进（不再限制「一个端口只能一条出线」）。
     循环模块只有一对出入端口：走到它时把下游链路重复执行 N 轮，轮与轮之间可设间隔秒数。 -->
<template>
  <div class="rfe">
    <!-- ══════════ 工具条 ══════════ -->
    <div class="rfe-bar">
      <button class="rf-b" title="Ctrl+Z" :disabled="!canUndo" @click="undo">{{ t('撤销') }}</button>
      <button class="rf-b" title="Ctrl+Shift+Z / Ctrl+Y" :disabled="!canRedo" @click="redo">{{ t('重做') }}</button>
      <button class="rf-b" title="Ctrl+C" :disabled="!selNode" @click="copySel">{{ t('复制') }}</button>
      <button class="rf-b" title="Ctrl+X" :disabled="!selNode" @click="cutSel">{{ t('剪切') }}</button>
      <button class="rf-b" title="Ctrl+V" :disabled="!clipboard" @click="paste">{{ t('粘贴') }}</button>
      <span class="rf-sp"></span>
      <span class="rf-lg"><i class="lg-d st"></i>{{ t('开始') }}</span>
      <span class="rf-lg"><i class="lg-d adj"></i>{{ t('可调') }}</span>
      <span class="rf-lg"><i class="lg-d sen"></i>{{ t('传感') }}</span>
      <span class="rf-lg"><i class="lg-d ifn"></i>{{ t('条件') }}</span>
      <span class="rf-lg"><i class="lg-d lop"></i>{{ t('循环') }}</span>
      <span class="rf-sp"></span>
      <span class="rf-cnt mono">{{ nodes.length }} {{ t('模块') }} · {{ edges.length }} {{ t('连线') }}</span>
      <span class="rf-cnt mono">{{ t('本轮动作') }} {{ lastActs.length }}</span>
      <span class="rf-path" :class="{ on: flow.ok }">{{ flow.ok ? t('通路已连通') : t('通路未连通') }}</span>
      <button class="rf-b" @click="fitView" :disabled="!nodes.length">{{ t('适应') }}</button>
      <button class="rf-b" @click="clearAll" :disabled="!nodes.length">{{ t('清空') }}</button>
      <button class="rf-b ghost" @click="showLog = !showLog">{{ t('日志') }}{{ log.length ? '(' + log.length + ')' : '' }}</button>
      <span class="rf-zoom mono">{{ Math.round(view.z * 100) }}%</span>
    </div>

    <!-- ══════════ 画布 ══════════ -->
    <div class="rfe-cv" ref="cvEl" :class="{ drop: dragOver }"
         @mousedown="onCvDown" @wheel.prevent="onWheel"
         @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop">
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
            <span v-if="n.kind === 'adj'" class="rf-bind" :class="{ on: !!boundOf(n) }"
                  :title="boundOf(n) ? t('运行命中时会下发写入 {dev} · {prop}', { dev: boundOf(n).device, prop: boundOf(n).prop }) : t('未绑定数据源设备的可写点位：命中后只改变平台内的仿真设定值，现场设备不会动作')">
              {{ boundOf(n) ? '⇄ ' + boundOf(n).device + '.' + boundOf(n).prop : t('仅仿真') }}
            </span>
            <span v-if="!isLinked(n)" class="rf-warn">{{ t('未接入条件分支') }}</span>
          </div>

          <span class="rf-pt out" @mousedown.stop="startLink(n, 'out')"></span>
        </div>

        <!-- ─────── 开始节点（流程入口：只有与它连通的卡片才会执行；「结束」端点已取消） ─────── -->
        <div v-for="n in flowNodes" :key="n.id" class="rf-node flow" :data-nid="n.id"
             :class="[n.kind, { sel: n.id === selNode, act: activeNode.has(n.id) }]"
             :style="nodeStyle(n)" @mousedown.stop="startMove(n, $event)">
          <i class="rf-fic">▶</i>
          <span class="rf-fnm">{{ t('开始') }}</span>
          <button class="rf-x" :title="t('删除模块')" @mousedown.stop @click.stop="delNode(n)">✕</button>
          <span class="rf-pt out" @mousedown.stop="startLink(n, 'out')"></span>
        </div>

        <!-- ─────── IF 条件节点 ─────── -->
        <div v-for="n in ifNodes" :key="n.id" class="rf-node ifn" :data-nid="n.id"
             :class="{ sel: n.id === selNode, act: activeNode.has(n.id) }" :style="nodeStyle(n)" @mousedown.stop="selNode = n.id">
          <span class="rf-pt in"></span>

          <div class="rf-hd" @mousedown.stop="startMove(n, $event)">
            <i class="rf-ic">⑃</i>
            <span class="rf-nm">{{ t('条件判断') }}</span>
            <em class="rf-ut mono">if / elif / else</em>
            <button class="rf-x" :title="t('删除模块')" @mousedown.stop @click.stop="delNode(n)">✕</button>
          </div>

          <div v-for="b in n.branches" :key="b.id" class="rf-br" :style="{ height: branchH(b) + 'px' }"
               :class="[b.type, { act: activeBranch === n.id + ':' + b.id }]">
            <div class="rf-br1">
              <span class="rf-bt">{{ b.type === 'if' ? t('如果') : b.type === 'elif' ? t('否则如果') : t('否则') }}</span>
              <template v-if="b.type !== 'else'">
                <select class="rf-sel src" v-model="condsOf(b)[0].src" @mousedown.stop @focus="histBegin" @change="histCommit">
                  <option value="">{{ t('跟随输入') }}</option>
                  <option v-for="d in devNodes" :key="d.id" :value="d.id">{{ d.label }}</option>
                </select>
                <select class="rf-sel op" v-model="condsOf(b)[0].op" @mousedown.stop @focus="histBegin" @change="histCommit">
                  <option v-for="o in OPS" :key="o.v" :value="o.v">{{ o.l }}</option>
                </select>
                <input class="rf-num sm" type="number" v-model.number="condsOf(b)[0].val" @mousedown.stop @focus="histBegin" @change="histCommit" />
              </template>
              <span v-else class="rf-el">{{ t('以上都不满足') }}</span>
              <button class="rf-bx" :disabled="b.type === 'else'" @mousedown.stop @click.stop="delBranch(n, b)"
                      :title="b.type === 'else' ? t('else 分支不可删除') : t('删除该分支')">✕</button>
            </div>
            <!-- 同分支内的追加条件：行间的下拉决定它与上一条是「并且」还是「或者」 -->
            <div v-for="c in condsOf(b).slice(1)" :key="c.id" class="rf-gc">
              <select class="rf-jn" v-model="c.join" @mousedown.stop @focus="histBegin" @change="histCommit">
                <option value="and">{{ t('并且') }}</option>
                <option value="or">{{ t('或者') }}</option>
              </select>
              <select class="rf-sel src" v-model="c.src" @mousedown.stop @focus="histBegin" @change="histCommit">
                <option value="">{{ t('跟随输入') }}</option>
                <option v-for="d in devNodes" :key="d.id" :value="d.id">{{ d.label }}</option>
              </select>
              <select class="rf-sel op" v-model="c.op" @mousedown.stop @focus="histBegin" @change="histCommit">
                <option v-for="o in OPS" :key="o.v" :value="o.v">{{ o.l }}</option>
              </select>
              <input class="rf-num sm" type="number" v-model.number="c.val" @mousedown.stop @focus="histBegin" @change="histCommit" />
              <button class="rf-bx" @mousedown.stop @click.stop="delCond(b, c)" :title="t('删除该条件')">✕</button>
            </div>
            <div class="rf-br2">
              <span class="rf-tg" :class="{ none: !branchTargets(n, b).length }">{{ branchTgTxt(n, b) }}</span>
              <span class="rf-sv mono" v-if="b.type !== 'else'">{{ branchSrcTxt(n, b) }}</span>
              <button v-if="b.type !== 'else'" class="rf-add rf-addc"
                      @mousedown.stop @click.stop="addCond(b)">+ {{ t('条件') }}</button>
            </div>
            <span class="rf-pt out" @mousedown.stop="startLink(n, b.id)"></span>
          </div>

          <div class="rf-nft">
            <button class="rf-add" @mousedown.stop @click.stop="addBranch(n)">+ {{ t('elif') }}</button>
          </div>
        </div>

        <!-- ─────── 循环节点：走到它时把下游链路重复执行 N 轮 ─────── -->
        <div v-for="n in loopNodes" :key="n.id" class="rf-node loop" :data-nid="n.id"
             :class="{ sel: n.id === selNode, act: activeNode.has(n.id) }"
             :style="nodeStyle(n)" @mousedown.stop="startMove(n, $event)">
          <span class="rf-pt in"></span>

          <div class="rf-hd" @mousedown.stop="startMove(n, $event)">
            <i class="rf-ic">↻</i>
            <span class="rf-nm">{{ n.label || t('循环模块') }}</span>
            <em class="rf-ut mono">repeat</em>
            <button class="rf-x" :title="t('删除模块')" @mousedown.stop @click.stop="delNode(n)">✕</button>
          </div>

          <div class="rf-lpr">
            <em class="rf-lb">{{ t('循环次数') }}</em>
            <input class="rf-num" type="number" min="1" max="999" step="1" v-model.number="n.times"
                   @mousedown.stop @focus="histBegin" @change="commitLoop(n)" />
            <i class="rf-u">{{ t('次') }}</i>
          </div>
          <div class="rf-lpr">
            <em class="rf-lb">{{ t('每轮间隔') }}</em>
            <input class="rf-num" type="number" min="0" max="3600" step="1" v-model.number="n.gap"
                   @mousedown.stop @focus="histBegin" @change="commitLoop(n)" />
            <i class="rf-u">{{ t('秒') }}</i>
          </div>
          <div class="rf-ft">
            <span class="rf-hint">{{ t('重复执行下游链路') }}</span>
            <span v-if="!isLinked(n)" class="rf-warn">{{ t('未接入流程') }}</span>
          </div>

          <span class="rf-pt out" @mousedown.stop="startLink(n, 'out')"></span>
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
        <p class="t1">{{ t('从左侧「模块」列表拖入画布，或点击工具条按钮开始编排') }}</p>
        <p class="t2">{{ t('规则逻辑：开始 → 传感/可调 → 条件判断（一条分支可写多条比较，行间用「并且 / 或者」连接）→ 出口 → 下游可调（写设定值）或传感（观测）；卡片需与「开始」连通才会执行') }}</p>
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
import { flowPath, evalFlowGraph, isDevKind, isFlowKind, branchConds, branchH, upgradeBranches, KIND_START, KIND_END } from '../utils/ruleFlow'

const props = defineProps({
  // { nodes: [], edges: [] } —— 由父组件（模型）持有的响应式对象，本组件就地读写，持久化由父组件负责
  graph: { type: Object, required: true },
  // 运行状态由编排页右上角的「运行」按钮驱动，本组件不再自带运行开关
  running: { type: Boolean, default: false },
  period: { type: Number, default: 2 },
  // 所属模型 id：用它在 store 里取后台运行器每轮的执行结果（高亮 / 日志）
  modelId: { type: String, default: '' },
})

const store = useSimStore()

// ─────────── 几何常量 ───────────
const CV_W = 4200
const CV_H = 3000
// 往左 / 上可拖出的余量。画布里的连线画在 .rfe-svg 上（overflow: visible，负坐标照常绘制），
// 卡片本身也是绝对定位的 div，都不受 SVG 尺寸裁剪 —— 所以负方向只受这里的人为限制。
// 留一个大余量防止甩飞，同时保证往左 / 上拖动不会再撞上一道「隐形边界」。
const NEG = 6000
// 原点余量：把世界原点 (0,0) 向右下推 ORIGIN 像素渲染，于是 -ORIGIN ~ 0 的负坐标仍在画布内可见。
// 模块才能往左 / 往上自由拖动布局（否则坐标只能 ≥ 0 = 死死贴在画布左上角，往上拖完全没反应）。
const ORIGIN = 400
const DEV_W = 208
const DEV_H = 84
// 循环模块：只有一对出入端口（头部 + 次数 + 间隔 + 提示）
const LOOP_W = 196
const LOOP_H = 104   // 头部 30 + 两行参数 + 底部提示
// 开始 / 结束：流程端点（胶囊形，比设备卡片小，只承载一个端口）
const ST_W = 132
const ST_H = 40
const IF_W = 300
const IF_HD = 30       // 头部
const IF_FT = 28       // 底部「+ elif」
// 分支高度统一由 utils/ruleFlow 的 branchH 给出（首行 46 + 每追加一条条件 30），
// 编辑器与自动布局共用同一份口径，避免「端口位置与卡片实际高度」再次漂移。
const OPS = [
  { v: '>', l: '>' }, { v: '>=', l: '≥' }, { v: '<', l: '<' },
  { v: '<=', l: '≤' }, { v: '==', l: '=' }, { v: '!=', l: '≠' },
]

const nodes = computed(() => (props.graph && props.graph.nodes) || [])
const edges = computed(() => (props.graph && props.graph.edges) || [])
const ifNodes = computed(() => nodes.value.filter((n) => n.kind === 'if'))
/** 分支内的条件组：一组条件之间由 join（并且 / 或者）连接，AND / OR 是条件的内部组件而不再是独立模块 */
function condsOf(b) { return branchConds(b) }
// 存量升级（幂等）：旧版把 AND / OR 做成独立逻辑门模块，这里把它们收进条件内部 ——
// gate 节点转成「条件判断」节点（TRUE / FALSE 两出口 → if / else 两分支），旧式单比较分支转成 conds 数组。
// 必须早于首次渲染，否则模板取 condsOf(b)[0] 会拿到 undefined。
upgradeBranches(props.graph)
// 设备模块只含可调 / 传感；开始 / 结束是流程端点，不对应任何设备
const devNodes = computed(() => nodes.value.filter((n) => isDevKind(n.kind)))
const flowNodes = computed(() => nodes.value.filter((n) => isFlowKind(n.kind)))
const loopNodes = computed(() => nodes.value.filter((n) => n.kind === 'loop'))
/** 通路分析：只有落在 live 里的模块才会被执行（见 utils/ruleFlow.js） */
// 注意：不要命名为 path —— Vue 模板编译器会把 setup 里的同名绑定解析成 <path> 组件
const flow = computed(() => flowPath(props.graph))

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
function isMissing(n) { return isDevKind(n.kind) && !findDev(n.devId) }
/** 可调模块的写入去向：已绑定数据源设备的可写点位 → 命中时真实下发；未绑定 → 只改平台内仿真设定值 */
function boundOf(n) { return n && n.kind === 'adj' ? store.boundWriteOf(n.devId) : null }

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
  const mx = e.clientX - r.left - el.clientLeft - ORIGIN
  const my = e.clientY - r.top - el.clientTop - ORIGIN
  const nz = Math.min(1.8, Math.max(0.35, view.z * (e.deltaY < 0 ? 1.1 : 1 / 1.1)))
  view.x = mx - ((mx - view.x) * nz) / view.z
  view.y = my - ((my - view.y) * nz) / view.z
  view.z = nz
}
function toWorld(cx, cy) {
  const el = cvEl.value
  // clientLeft / clientTop = 画布左边框 / 上边框宽度：内容层 .rfe-vp 以「内边距盒」为原点，
  // 光标换算必须剔除边框，否则落点会整体偏出一个边框宽度（拖拽放模块时肉眼可见的错位）。
  if (!el) return { x: (cx - view.x - ORIGIN) / view.z, y: (cy - view.y - ORIGIN) / view.z }
  const r = el.getBoundingClientRect()
  return {
    x: (cx - r.left - el.clientLeft - view.x - ORIGIN) / view.z,
    y: (cy - r.top - el.clientTop - view.y - ORIGIN) / view.z,
  }
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
 *  下界 -NEG（往左 / 上可自由拖出很长一段，见 NEG 注释），上界 画布尺寸 - 卡片尺寸。
 *  返回 false 表示已被夹在边界上、卡片无法再跟着光标走（此时自动平移也要停，否则只是白滚画布）。 */
function moveNodeTo(cx, cy) {
  if (!drag || drag.kind !== 'node') return false
  const n = nodes.value.find((x) => x.id === drag.id)
  if (!n) return false
  const wx = drag.ox + (cx - drag.sx) / view.z
  const wy = drag.oy + (cy - drag.sy) / view.z
  n.x = clampX(wx, nodeW(n))
  n.y = clampY(wy, nodeH(n))
  return n.x === wx && n.y === wy
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
  const vx = view.x, vy = view.y, ox = drag.ox, oy = drag.oy
  view.x += dx
  view.y += dy
  // 视图平移后光标对应的世界坐标变了：补偿拖拽起点，让卡片始终黏在光标下而不是跟着画布跑
  drag.ox -= dx / view.z
  drag.oy -= dy / view.z
  const ok = moveNodeTo(lastPt.x, lastPt.y)
  if (!ok) {
    // 卡片已顶到边界：撤销这一帧的平移，否则画布照滚而卡片不动，看起来像「往回跑」
    view.x = vx; view.y = vy; drag.ox = ox; drag.oy = oy
    return
  }
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
  const tgt = nodes.value.find((x) => x.id === toId)
  // 开始模块是流程入口，没有入口端口；结束模块之后不再往下走
  if (!tgt || tgt.kind === KIND_START || from.kind === KIND_END) return
  // 同一个输出端口可以连多个下游：命中该分支（或走到该模块）时，所有下游并列推进。
  // 只有「完全相同的连线」才忽略，不再清掉该端口已有的其它出线。
  if (edges.value.some((e) => e.from === from.id && e.port === port && e.to === toId)) return
  histBegin()
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
/** 落点定位：卡片**中心**对准落点（拖拽时即鼠标位置，点击添加时为视图中心）。
 *  夹取范围必须与 moveNodeTo 完全一致（下界 -NEG、上界 画布尺寸 - 卡片尺寸）——
 *  曾用 Math.max(12, …) 把落点硬夹在左上角，而画布本来就支持负坐标（ORIGIN / NEG 就是为了往左、往上布局），
 *  一旦平移或缩放过画布，落点世界坐标变负就会被吸到 (12,12)，表现为「模块没落在我松手的位置」。
 *  只有该位置已被另一张卡片占住时才做一次微小错开，避免新卡片被完全盖住。 */
function dropPoint(at, w, h) {
  const c = at || centerWorld()
  let x = clampX(c.x - w / 2, w)
  let y = clampY(c.y - h / 2, h)
  const clash = nodes.value.some((n) => Math.abs(n.x - x) < 12 && Math.abs(n.y - y) < 12)
  if (clash) { x = clampX(x + 24, w); y = clampY(y + 20, h) }
  return { x, y }
}
/** 条件 id（分支内多条条件各有自己的 id，供 v-for 的 key 与增删定位） */
function cid() { return 'c' + Date.now().toString(36) + (seq++) }
function addIf(at) {
  histBegin()
  const n = {
    id: nid('if'),
    kind: 'if',
    x: 0,
    y: 0,
    branches: [
      { id: 'b1', type: 'if', conds: [{ id: cid(), src: '', op: '>', val: 0, join: 'and' }] },
      { id: 'b2', type: 'else' },
    ],
  }
  const p = dropPoint(at, IF_W, nodeH(n))
  n.x = p.x
  n.y = p.y
  nodes.value.push(n)
  histCommit()
}
/**
 * 给分支追加一条条件：AND / OR 是条件的内部组件（行间的连接词），不再是独立模块。
 * 新条件的判定来源默认沿用首条（最常见的写法就是同一读数落在某个区间：x ≥ 25 并且 x < 50），
 * 追加后再把行首下拉切成「或者」即可表达「任一成立」。
 */
function addCond(b) {
  if (!b || !Array.isArray(b.conds)) return
  histBegin()
  b.conds.push({ id: cid(), src: b.conds[0] ? b.conds[0].src : '', op: '>', val: 0, join: 'and' })
  histCommit()
}
/** 删除分支里的一条条件：至少保留一条 */
function delCond(b, c) {
  if (!b || !Array.isArray(b.conds) || b.conds.length <= 1) return
  histBegin()
  const i = b.conds.indexOf(c)
  if (i >= 0) b.conds.splice(i, 1)
  histCommit()
}
/** 循环模块：走到它时把下游链路重复执行 N 轮（每轮之间可设间隔秒数） */
function addLoop(at) {
  histBegin()
  const p = dropPoint(at, LOOP_W, LOOP_H)
  nodes.value.push({
    id: nid('loop'),
    kind: 'loop',
    label: t('循环模块'),
    times: 3,
    gap: 0,
    x: p.x,
    y: p.y,
  })
  histCommit()
}
/** 循环参数钳取：次数 1~999 整数，间隔 0~3600 秒 */
function loopTimes(n) {
  const v = Math.round(Number(n && n.times))
  return Number.isFinite(v) ? Math.min(999, Math.max(1, v)) : 1
}
function loopGap(n) {
  const v = Number(n && n.gap)
  return Number.isFinite(v) ? Math.min(3600, Math.max(0, v)) : 0
}
/** 循环参数编辑：先钳回合法区间再入历史 */
function commitLoop(n) {
  n.times = loopTimes(n)
  n.gap = loopGap(n)
  histCommit()
}
/** 流程端点（开始 / 结束）：整条流程的入口与出口，只有连通二者的那条路才会执行 */
function addFlow(kind, at) {
  histBegin()
  const p = dropPoint(at, ST_W, ST_H)
  nodes.value.push({
    id: nid(kind),
    kind,
    x: p.x,
    y: p.y,
  })
  histCommit()
}
function addDevById(kind, d, at) {
  histBegin()
  const p = dropPoint(at, DEV_W, DEV_H)
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
    x: p.x,
    y: p.y,
  })
  histCommit()
}
function addBranch(n) {
  histBegin()
  // elif 插在 else 之前
  const ei = n.branches.findIndex((b) => b.type === 'else')
  const item = { id: 'b' + Date.now().toString(36) + (seq++), type: 'elif', conds: [{ id: cid(), src: '', op: '>', val: 0, join: 'and' }] }
  if (ei >= 0) n.branches.splice(ei, 0, item)
  else n.branches.push(item)
  histCommit()
}
/** 删除一条分支：else 是兜底出口，永不删除；删掉 if / elif 后重排分支语义（仍保证有一条 else） */
function delBranch(n, b) {
  if (!n || !b || !Array.isArray(n.branches)) return
  if (b.type === 'else') return
  histBegin()
  const i = n.branches.indexOf(b)
  if (i >= 0) n.branches.splice(i, 1)
  for (let k = edges.value.length - 1; k >= 0; k--) {
    if (edges.value[k].from === n.id && edges.value[k].port === b.id) edges.value.splice(k, 1)
  }
  normBranches(n)
  histCommit()
}
/**
 * 分支语义重排：首条为 if、中间为 elif、else 固定一条且在末位（兜底出口，不可删除）；
 * 缺失 else 时自动补一条（兼容只写了 if 的旧编排），多余 / 失效端口的连线一并清理。
 */
function normBranches(n) {
  const bs = Array.isArray(n.branches) ? n.branches : []
  const head = bs.filter((x) => x && x.type !== 'else')
  head.forEach((x, i) => { x.type = i === 0 ? 'if' : 'elif' })
  let tail = bs.filter((x) => x && x.type === 'else').slice(0, 1)
  if (!tail.length) tail = [{ id: 'b' + Date.now().toString(36) + (seq++), type: 'else' }]
  n.branches = head.concat(tail)
  const ids = {}
  for (const x of n.branches) ids[x.id] = 1
  for (let k = edges.value.length - 1; k >= 0; k--) {
    const e = edges.value[k]
    if (e.from === n.id && !ids[e.port]) edges.value.splice(k, 1)
  }
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
  // 清掉其它模块里指向它的判定来源（IF 各分支的每条条件）
  for (const m of nodes.value) {
    if (m.kind !== 'if') continue
    for (const b of m.branches || []) for (const c of condsOf(b)) if (c.src === n.id) c.src = ''
  }
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
  rfState.pendLoops = []   // 模块都没了，挂起的后续轮次一并作废
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
}
function redo() {
  histCommit()
  if (!redoStack.value.length) return
  undoStack.value.push(JSON.parse(snapState()))
  applyState(redoStack.value.pop())
  selNode.value = ''
  selEdge.value = ''
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
  c.x = clampX((c.x || 40) + 28, nodeW(c))
  c.y = clampY((c.y || 40) + 28, nodeH(c))
  if (c.kind === 'if' && Array.isArray(c.branches)) {
    for (const b of c.branches) {
      b.id = 'b' + Date.now().toString(36) + '_' + (seq++)
      for (const q of condsOf(b)) {
        q.id = 'c' + Date.now().toString(36) + '_' + (seq++)
        q.src = ''   // 判定来源指向旧节点，粘贴后需重新指定
      }
    }
  }
  nodes.value.push(c)
  selNode.value = c.id
  selEdge.value = ''
  histCommit()
}

// ─────────── 拖放（左侧模块列表 → 画布） ───────────
// 左栏把模块（开始 / 结束 / IF / 循环 / 可调 / 传感）以 JSON 写进 dataTransfer，
// 落到画布时按落点世界坐标建模块；点击左栏项时由父组件调 addModule 加到视图中心。
const dragOver = ref(false)
function onDrop(e) {
  dragOver.value = false
  const raw = e && e.dataTransfer ? e.dataTransfer.getData('text/plain') : ''
  if (!raw) return
  let p = null
  try { p = JSON.parse(raw) } catch (err) { return }
  if (!p || !p.k) return
  addModule(p, toWorld(e.clientX, e.clientY))
}
/** 按载荷建模块：{ k, op?, devId? }；at 为世界坐标（缺省落到视图中心） */
function addModule(p, at) {
  if (!p || !p.k) return
  if (p.k === KIND_START || p.k === KIND_END) { addFlow(p.k, at); return }
  if (p.k === 'if') { addIf(at); return }
  if (p.k === 'loop') { addLoop(at); return }
  if (p.k === 'adj' || p.k === 'sen') {
    const list = p.k === 'adj' ? adjList.value : senList.value
    const d = list.find((x) => x.id === p.devId) || list[0]
    if (d) addDevById(p.k, d, at)
  }
}

// ─────────── 几何：端口与连线 ───────────
function nodeW(n) {
  if (n.kind === 'if') return IF_W
  if (n.kind === 'loop') return LOOP_W
  return isFlowKind(n.kind) ? ST_W : DEV_W
}
function nodeH(n) {
  // 每条分支的高度随它的条件条数变化（首行 + 追加条件行）
  if (n.kind === 'if') return IF_HD + (n.branches || []).reduce((s, b) => s + branchH(b), 0) + IF_FT
  if (n.kind === 'loop') return LOOP_H
  return isFlowKind(n.kind) ? ST_H : DEV_H
}
/** 坐标夹取（拖拽移动与拖放落点共用同一口径）：
 *  下界 -NEG（往左 / 上可自由拖出很长一段，见 NEG 注释），上界 画布尺寸 - 卡片尺寸。 */
function clampX(v, w) { return Math.round(Math.min(CV_W - w, Math.max(-NEG, v))) }
function clampY(v, h) { return Math.round(Math.min(CV_H - h, Math.max(-NEG, v))) }
function nodeStyle(n) {
  return { left: n.x + 'px', top: n.y + 'px', width: nodeW(n) + 'px', height: nodeH(n) + 'px' }
}
function inPort(n) { return { x: n.x, y: n.y + nodeH(n) / 2 } }
function outPort(n, port) {
  if (n.kind === 'if') {
    // 分支按其在节点内的实际高度依次排下来（每条分支可能含多行条件）
    let y = n.y + IF_HD
    const bs = n.branches || []
    let i = bs.findIndex((b) => b.id === port)
    if (i < 0) i = 0
    for (let k = 0; k < i; k++) y += branchH(bs[k])
    return { x: n.x + IF_W, y: y + branchH(bs[i] || {}) / 2 }
  }
  if (n.kind === KIND_START) return { x: n.x + ST_W, y: n.y + ST_H / 2 }
  if (n.kind === 'loop') return { x: n.x + LOOP_W, y: n.y + LOOP_H / 2 }
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
/** 模块显示名（校验提示 / 下游摘要用）：设备用标签，逻辑类用种类名 */
function nodeName(n) {
  if (!n) return t('模块')
  if (n.label) return n.label
  if (n.kind === 'if') return t('条件判断')
  if (n.kind === 'loop') return t('循环模块')
  if (n.kind === KIND_START) return t('开始')
  if (n.kind === KIND_END) return t('结束')
  return t('模块')
}
function isLinked(n) {
  if (n.kind === 'if') return true
  if (n.kind === KIND_START) return edges.value.some((e) => e.from === n.id)
  if (n.kind === KIND_END) return edges.value.some((e) => e.to === n.id)
  return edges.value.some((e) => e.to === n.id || e.from === n.id)
}
/** 一条分支的全部下游（同一分支输出可连多个模块，命中时并列推进） */
function branchTargets(n, b) {
  const out = []
  for (const e of edges.value) {
    if (e.from !== n.id || e.port !== b.id) continue
    const t = nodes.value.find((x) => x.id === e.to)
    if (t) out.push(t)
  }
  return out
}
/** 分支下游摘要：两个以内全列，更多则「前两个 + N」 */
function branchTgTxt(n, b) {
  const ts = branchTargets(n, b)
  if (!ts.length) return t('未连接下游')
  const names = ts.map((x) => nodeName(x))
  if (names.length <= 2) return '→ ' + names.join('、')
  return '→ ' + names.slice(0, 2).join('、') + ' +' + (names.length - 2)
}
function branchSrcTxt(n, b) {
  const s = srcNodeOf(n, b)
  if (!s) return t('无判定来源')
  const v = liveOf(s.devId)
  return `${s.label} = ${v == null ? '—' : fmt(v)}`
}
/** 判定来源：条件显式指定 > IF 模块输入连线 > 无（取分支首条条件的来源作代表） */
function srcNodeOf(n, b) {
  const c = condsOf(b)[0]
  if (c && c.src) {
    const x = nodes.value.find((k) => k.id === c.src)
    if (x && x.kind !== 'if') return x
  }
  const e = edges.value.find((x) => x.to === n.id)
  if (!e) return null
  const s = nodes.value.find((x) => x.id === e.from)
  return s && s.kind !== 'if' ? s : null
}
/** 某条条件自己的判定来源：显式指定 > IF 模块输入连线 > 无 */
function condSrcNode(n, c) {
  if (c && c.src) {
    const x = nodes.value.find((k) => k.id === c.src)
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
  const fp = flow.value
  // ① 流程入口：没有「开始」模块，整条流程一次都不会执行（「结束」端点已取消，卡片不必再接出口）
  if (!fp.starts.length) out.push(t('缺少「开始」模块：从左侧「流程」拖入流程入口'))
  for (const id of fp.starts) {
    if (!edges.value.some((e) => e.from === id)) out.push(t('「开始」模块未连接下游模块'))
  }
  // 孤立卡片：与「开始」之间没有通路，运行时不执行（已有「开始」时才逐个点名，否则上面一条提示即可）
  if (fp.starts.length) {
    for (const id of fp.lost) {
      const n = nodes.value.find((x) => x.id === id)
      if (n) out.push(t('模块「{name}」未与「开始」连通，不会被执行', { name: nodeName(n) }))
    }
  }
  // ② 模块自身
  for (const n of nodes.value) {
    if (n.kind === 'if') {
      if (!n.branches.some((b) => b.type === 'else')) {
        out.push(t('IF 模块缺少 else 分支（建议保留兜底走向）'))
      }
      for (const b of n.branches) {
        const bn = b.type === 'if' ? t('如果') : b.type === 'elif' ? t('否则如果') : t('否则')
        if (b.type !== 'else') {
          const cs = condsOf(b)
          cs.forEach((c, i) => {
            const cn = cs.length > 1 ? `${bn}·${t('条件')}${i + 1}` : bn
            if (!condSrcNode(n, c)) out.push(t('IF 模块「{name}」分支未接入判定来源', { name: cn }))
            if (!Number.isFinite(Number(c.val))) out.push(t('IF 模块「{name}」分支阈值未填写', { name: cn }))
          })
        }
        if (!branchTargets(n, b).length) out.push(t('IF 模块「{name}」分支未连接下游模块', { name: bn }))
      }
    } else if (isDevKind(n.kind)) {
      if (isMissing(n)) out.push(t('模块「{name}」对应的设备已不存在', { name: n.label }))
      if (n.kind === 'adj' && !Number.isFinite(Number(n.value))) out.push(t('可调模块「{name}」未设定数值', { name: n.label }))
      if (!isLinked(n)) out.push(t('模块「{name}」未接入任何模块，不会被执行', { name: n.label }))
    } else if (n.kind === 'loop') {
      const nm = n.label || t('循环模块')
      if (!edges.value.some((e) => e.to === n.id)) out.push(t('循环模块「{name}」未接入上游模块', { name: nm }))
      if (!edges.value.some((e) => e.from === n.id)) out.push(t('循环模块「{name}」未连接下游模块', { name: nm }))
    }
    // 接了线但没落在「开始」通路上：已在上面按孤立卡片统一点名，避免重复提示
  }
  return out
})

// ─────────── 执行（运行态由 sim store 的后台运行器驱动；本组件只做手动执行与结果呈现） ───────────
const showLog = ref(false)
const log = ref([])
const lastActs = ref([])
const activeNode = ref(new Set())
const activeEdge = ref(new Set())
const activeBranch = ref('')
// 画布手动「执行一次」时的循环挂起状态（运行态的挂起轮次由后台运行器自己持有）
const rfState = { pendLoops: [] }

function pushLog(txt) {
  log.value.unshift({ ts: Date.now(), txt })
  if (log.value.length > 40) log.value.length = 40
}
/**
 * 把一次执行结果落到画布（高亮 + 日志）：后台运行器与画布手动执行走同一入口。
 */
function applyResult(r, withLog) {
  const acts = (r && r.acts) || []
  lastActs.value = acts
  activeNode.value = (r && r.activeNodes) || new Set()
  activeEdge.value = (r && r.activeEdges) || new Set()
  activeBranch.value = (r && r.branch) || ''
  if (!withLog) return
  if (!acts.length) {
    pushLog(r && r.ok === false ? t('没有与「开始」连通的卡片，本轮不执行') : t('本轮无命中（检查判定来源与阈值）'))
    return
  }
  for (const a of acts) pushLog(a.txt)
}
/**
 * 服务端运行器回传的是结构化动作（{ kind, nodeId, devId, value }），文案在这里按图补全：
 * 既保持中英文都能翻译，也让「画布看到的」与「服务端实际执行的」是同一份结果。
 */
function decorateActs(acts) {
  return (acts || []).map((a) => {
    const n = nodes.value.find((x) => x.id === a.nodeId)
    if (a.kind === 'adj') {
      const b = n ? boundOf(n) : null
      const tail = b ? ` · ${t('下发')} ${b.device}.${b.prop}` : ` · ${t('仅仿真')}`
      return { ...a, txt: `${nodeName(n)} ← ${t('写入')} ${fmt(a.value)}${(n && n.unit) || ''}${tail}` }
    }
    if (a.kind === 'sen') return { ...a, txt: `${nodeName(n)}（${t('仅观测，不写入')}）` }
    if (a.kind === 'loop') return { ...a, txt: `${nodeName(n)} · ${t('第 {i}/{n} 轮', { i: a.round, n: a.total })}` }
    return { ...a, txt: '' }
  })
}
/**
 * 执行一遍（画布「执行一次」用）：执行逻辑统一走 utils/ruleFlow 的 evalFlowGraph，
 * 与后台运行器同源，避免出现「画布跑一遍和策略跑起来结果不一致」。
 * 运行态由 sim store 的运行器按周期驱动，本组件不再自带定时器。
 */
function runOnce(withLog) {
  const r = evalFlowGraph(props.graph, { liveOf, boundOf, state: rfState })
  for (const a of r.acts) {
    // 统一入口：既写本地设定值（驱动仿真 / 碳核算），也把已绑定数据源可写点位的可变设备
    // 经 cmd/{box}/cmd 真实下发。silent：自动执行不弹 toast，store 内按值变化去重避免命令风暴。
    if (a.write) store.setExtSetpoint(a.devId, a.value, { silent: true })
  }
  applyResult(r, !!withLog)
  return r.acts
}

// 后台运行器（sim store）每轮的结果回写到画布：运行态下画布高亮的就是策略真正在跑的那一份结果。
// 画布自身不再持有定时器 —— 否则一切换页面 / 关闭编排页，运行中的策略就停了。
watch(
  () => (props.modelId ? (store.agcLast || {})[props.modelId] : null),
  (r) => {
    if (!r) return
    applyResult({
      ok: r.ok,
      acts: decorateActs(r.acts),
      activeNodes: new Set(r.nodes || []),
      activeEdges: new Set(r.edges || []),
      branch: r.branch || '',
    }, true)
  },
  { immediate: true },
)

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
  return n && isDevKind(n.kind) ? n : null
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
  // 兼容只写了 if / elif 的旧编排：进入时补齐不可删除的 else 兜底分支
  for (const n of nodes.value) if (n && n.kind === 'if') normBranches(n)
  if (nodes.value.length) setTimeout(fitView, 0)
})
onBeforeUnmount(() => {
  stopAutoPan()
  // 画布不再自带定时器：运行态由 sim store 的后台运行器驱动（此处曾误留 stopTimer 调用，导致卸载报错）
  window.removeEventListener('mousemove', onWinMove)
  window.removeEventListener('mouseup', onWinUp)
  window.removeEventListener('keydown', onKey)
})

// addModule：供编排页左栏「点击模块项 → 加到画布中心」直接调用（拖拽则由画布 drop 处理）
defineExpose({ runOnce, fitView, addModule })
</script>

<style scoped>
/* ══════════ 规则画布 · 视觉规范（与群控主页共用同一套令牌） ══════════
   画布内只出现 2 档正文字号（11 正文 / 10 辅助）与唯一的「大数字」读数；
   颜色只有三类：结构色 text·muted·faint，种类色 --k-adj/sen/if/loop，语义色 green/red */

.rfe {
  display: flex; flex-direction: column; min-height: 0;
}
.rfe em, .rfe i { font-style: normal; }

/* ══════════ 工具条 ══════════ */
.rfe-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 6px 8px;
  background: var(--panel-2); border: 1px solid var(--border); border-bottom: 0;
  border-radius: var(--radius) var(--radius) 0 0;
}
.rf-b {
  padding: 3px 9px; font-family: inherit; font-size: var(--fs-b); font-weight: var(--fw-m); line-height: 1;
  color: var(--text); background: var(--panel-3); border: 1px solid transparent; border-radius: 2px;
  cursor: pointer; white-space: nowrap;
}
.rf-b:hover:not(:disabled) { background: color-mix(in srgb, var(--panel-3) 76%, var(--text)); }
.rf-b:disabled { opacity: .45; cursor: not-allowed; }
.rf-b.ghost { background: transparent; border-color: var(--border); }
.rf-b.ghost:hover:not(:disabled) { background: var(--panel); }

.rf-sep { flex: 0 0 auto; width: 1px; height: 14px; background: var(--border); }
.rf-sp { flex: 1 1 auto; }
.rf-lg { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-s); color: var(--muted); white-space: nowrap; }
.lg-d { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.lg-d.adj { background: var(--k-adj); }
.lg-d.sen { background: var(--k-sen); }
.lg-d.ifn { background: var(--k-if); }
.lg-d.lop { background: var(--k-loop); }
.lg-d.st { background: var(--green); }
.lg-d.en { background: var(--red); }
.rf-cnt { font-size: var(--fs-s); color: var(--faint); white-space: nowrap; }
.rf-path {
  padding: 0 6px; border-radius: 8px; white-space: nowrap; font-size: var(--fs-s); line-height: 15px;
  color: var(--red); border: 1px solid color-mix(in srgb, var(--red) 34%, transparent);
  background: color-mix(in srgb, var(--red) 10%, transparent);
}
.rf-path.on {
  color: var(--green); border-color: color-mix(in srgb, var(--green) 34%, transparent);
  background: color-mix(in srgb, var(--green) 10%, transparent);
}
.rf-zoom { font-size: var(--fs-s); color: var(--faint); min-width: 34px; text-align: right; }

/* ══════════ 画布 ══════════ */
.rfe-cv {
  position: relative; flex: 1 1 auto; min-height: 420px; overflow: hidden; border: 1px solid var(--border);
  background: radial-gradient(circle at 1px 1px, var(--border) 1px, transparent 0) 0 0 / 22px 22px, var(--panel);
}
/* 左侧模块拖到画布上方时的落点提示 */
.rfe-cv.drop { border-color: var(--accent-d); box-shadow: inset 0 0 0 1px var(--accent-l); }
.rfe-vp { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
.rfe-svg { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
.rf-e-hit { fill: none; stroke: transparent; stroke-width: 14; pointer-events: stroke; cursor: pointer; }
.rf-e { fill: none; stroke: var(--faint); stroke-width: 1.6; stroke-linecap: round; pointer-events: none; }
.rf-e.on { stroke: var(--accent-d); stroke-width: 2.2; }
.rf-e.act { stroke: var(--green); stroke-width: 2.4; }
.rf-e.tmp { stroke: var(--accent-d); stroke-dasharray: 5 4; }
.rf-eg { cursor: pointer; pointer-events: all; }
.rf-ebg { fill: var(--red); }
.rf-ex { fill: var(--text); font-size: var(--fs-s); text-anchor: middle; }
.rf-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 0 40px; text-align: center; pointer-events: none; }
.rf-empty .t1 { font-size: var(--fs-t); color: var(--muted); }
.rf-empty .t2 { font-size: var(--fs-s); line-height: 1.6; color: var(--faint); max-width: 520px; }

/* ══════════ 模块实时值（贴在卡片正下方） ══════════ */
.rf-insp {
  /* 纯展示：不拦截鼠标，避免压住下方卡片的拖动 / 点击（仅关闭按钮可点） */
  pointer-events: none;
  position: absolute; z-index: 6; width: 208px; box-sizing: border-box;
  display: flex; flex-direction: column; gap: 5px; padding: 8px 10px 9px;
  border: 1px solid var(--border); border-top: 2px solid var(--accent-d); border-radius: var(--radius);
  background: var(--panel); box-shadow: var(--shadow);
}
.ri-hd { display: flex; align-items: center; gap: 5px; }
.ri-d { width: 6px; height: 6px; border-radius: 50%; background: var(--faint); flex: 0 0 auto; }
.ri-d.adj { background: var(--k-adj); }
.ri-d.sen { background: var(--k-sen); }
.ri-hd b { flex: 1 1 auto; min-width: 0; font-size: var(--fs-b); font-weight: var(--fw-t); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-t {
  flex: 0 0 auto; padding: 0 6px; border-radius: 8px; white-space: nowrap;
  font-size: var(--fs-s); line-height: 15px; color: var(--muted); background: var(--bar); border: 1px solid var(--border);
}
.ri-x { flex: 0 0 auto; margin-left: auto; padding: 0 3px; border: 0; background: none; cursor: pointer; pointer-events: auto; font-family: inherit; font-size: var(--fs-b); color: var(--faint); }
.ri-x:hover { color: var(--red); }
.ri-v { display: flex; align-items: baseline; gap: 4px; }
.ri-v b { font-size: 18px; font-weight: var(--fw-t); color: var(--accent-d); line-height: 1.1; font-variant-numeric: tabular-nums; }
.ri-v i { font-size: var(--fs-s); color: var(--faint); }
.ri-sp { width: 100%; height: 40px; }
.ri-sp .sp-l { fill: none; stroke: var(--accent-d); stroke-width: 1.4; vector-effect: non-scaling-stroke; }
.ri-sp .sp-e { fill: var(--faint); font-size: var(--fs-s); text-anchor: middle; }
.ri-r { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; font-size: var(--fs-s); }
.ri-r em { color: var(--faint); }
.ri-r b { font-weight: var(--fw-m); color: var(--text); font-variant-numeric: tabular-nums; }

/* ══════════ 节点通用 ══════════ */
.rf-node {
  position: absolute; box-sizing: border-box; border-radius: var(--radius);
  background: var(--panel); border: 1px solid var(--border);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .10); font-size: var(--fs-b); color: var(--text); user-select: none;
}
.rf-node.sel { border-color: var(--accent-d); box-shadow: 0 0 0 2px var(--accent-l); }
/* 兜底：卡片里的控件一律允许收缩到 0，避免全局 select/input { width: 100% } 撑破卡片 */
.rf-node select, .rf-node input { min-width: 0; }
.rf-node.act { box-shadow: 0 0 0 2px color-mix(in srgb, var(--green) 45%, transparent); }
.rf-node.miss { opacity: .6; border-style: dashed; }
.rf-hd {  background: var(--head-bg);

  display: flex; align-items: center; gap: 5px; height: 30px; padding: 0 4px 0 8px;
   cursor: move; border-radius: var(--radius) var(--radius) 0 0;
}
.rf-ic { flex: 0 0 auto; font-size: var(--fs-b); }
.rf-nm { flex: 1 1 auto; min-width: 0; font-size: var(--fs-b); font-weight: var(--fw-t); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-ut { flex: 0 0 auto; font-size: var(--fs-s); color: var(--faint); }
.rf-x { flex: 0 0 auto; width: 14px; height: 14px; line-height: 12px; padding: 0; font-size: var(--fs-s); color: var(--faint); background: none; border: 0; cursor: pointer; font-family: inherit; }
.rf-x:hover { color: var(--red); }

/* 种类色只用在两处：头部淡底 · 种类图标（卡片左侧不再有竖条） */
.rf-node.adj .rf-hd { background: color-mix(in srgb, var(--k-adj) 12%, transparent); }
.rf-node.adj .rf-ic { color: var(--k-adj); }
.rf-node.adj .rf-pt { border-color: var(--k-adj); }
.rf-node.sen .rf-hd { background: color-mix(in srgb, var(--k-sen) 12%, transparent); }
.rf-node.sen .rf-ic { color: var(--k-sen); }
.rf-node.sen .rf-pt { border-color: var(--k-sen); }
.rf-node.ifn .rf-hd { background: color-mix(in srgb, var(--k-if) 12%, transparent); }
.rf-node.ifn .rf-ic { color: var(--k-if); }
.rf-node.ifn .rf-pt { border-color: var(--k-if); }
.rf-node.loop .rf-hd { background: color-mix(in srgb, var(--k-loop) 12%, transparent); }
.rf-node.loop .rf-ic { color: var(--k-loop); }
.rf-node.loop .rf-pt { border-color: var(--k-loop); }

/* 可调 / 传感主体 */
.rf-bd { display: flex; align-items: center; gap: 5px; padding: 4px 8px 0; }
.rf-lb { flex: 0 0 auto; font-size: var(--fs-s); color: var(--muted); }
.rf-num {
  flex: 1 1 auto; min-width: 0; padding: 2px 4px; font-size: var(--fs-b); font-family: var(--mono);
  font-variant-numeric: tabular-nums; text-align: right; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); outline: none;
}
.rf-num:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); }
.rf-num.sm { width: 60px; flex: 0 0 auto; }
.rf-u { flex: 0 0 auto; font-size: var(--fs-s); color: var(--faint); }
.rf-v { flex: 1 1 auto; font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--accent-d); text-align: right; font-variant-numeric: tabular-nums; }
.rf-ft { display: flex; align-items: center; gap: 6px; padding: 3px 8px 4px; }
.rf-hint { font-size: var(--fs-s); color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-warn { margin-left: auto; font-size: var(--fs-s); color: var(--yellow); white-space: nowrap; }
/* 可调模块的写入去向：绑定了可写点位 = 命中时真实下发（绿）；否则仅改平台内仿真设定值（灰） */
.rf-bind { margin-left: auto; font-size: var(--fs-s); color: var(--faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rf-bind.on { color: var(--green); }

/* 开始 / 结束：胶囊形端点 */
.rf-node.flow { display: flex; align-items: center; gap: 6px; padding: 0 10px; border-radius: 20px; }
.rf-fic { flex: 0 0 auto; font-size: var(--fs-s); }
.rf-fnm { flex: 1 1 auto; min-width: 0; font-size: var(--fs-b); font-weight: var(--fw-t); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rf-node.start { border-color: color-mix(in srgb, var(--green) 50%, transparent); background: color-mix(in srgb, var(--green) 10%, transparent); }
.rf-node.start .rf-fic { color: var(--green); }
.rf-node.start .rf-pt { border-color: var(--green); }
.rf-node.end { border-color: color-mix(in srgb, var(--red) 50%, transparent); background: color-mix(in srgb, var(--red) 10%, transparent); }
.rf-node.end .rf-fic { color: var(--red); }
.rf-node.end .rf-pt { border-color: var(--red); }

/* IF 分支 */
.rf-br {
  position: relative; box-sizing: border-box; height: 46px;
  display: flex; flex-direction: column; justify-content: center; gap: 2px;
  padding: 0 8px 0 10px; border-top: 1px dashed var(--border);
}
.rf-br.act { background: color-mix(in srgb, var(--green) 12%, transparent); }
.rf-br1 { display: flex; align-items: center; gap: 4px; }
.rf-bt {
  flex: 0 0 auto; padding: 0 5px; border-radius: 8px; font-size: var(--fs-s); line-height: 15px;
  color: var(--k-if); border: 1px solid color-mix(in srgb, var(--k-if) 34%, transparent);
  background: color-mix(in srgb, var(--k-if) 12%, transparent);
}
.rf-br.else .rf-bt { color: var(--muted); background: var(--bar); border-color: var(--border); }
.rf-sel {
  min-width: 0; padding: 1px 3px; font-size: var(--fs-s); font-family: inherit; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); outline: none;
}
.rf-sel:focus { border-color: var(--accent-d); }
.rf-sel.src { flex: 1 1 auto; width: 60px; }
.rf-sel.op { flex: 0 0 auto; width: 44px; text-align: center; }
.rf-el { flex: 1 1 auto; font-size: var(--fs-s); color: var(--faint); }
.rf-bx { flex: 0 0 auto; width: 14px; height: 14px; line-height: 12px; padding: 0; font-size: var(--fs-s); color: var(--faint); background: none; border: 0; cursor: pointer; font-family: inherit; }
.rf-bx:hover:not(:disabled) { color: var(--red); }
.rf-bx:disabled { opacity: .4; cursor: not-allowed; }
.rf-br2 { display: flex; align-items: center; gap: 6px; padding: 2px 0 0 2px; }
.rf-tg { font-size: var(--fs-s); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 156px; }
.rf-tg.none { color: var(--faint); }
.rf-sv { margin-left: auto; font-size: var(--fs-s); color: var(--faint); font-variant-numeric: tabular-nums; }
.rf-nft { box-sizing: border-box; height: 28px; display: flex; align-items: center; padding: 0 8px 0 10px; border-top: 1px dashed var(--border); }
.rf-add { padding: 0; font-size: var(--fs-s); color: var(--k-if); background: none; border: 0; cursor: pointer; font-family: inherit; }
.rf-add:hover { text-decoration: underline; }

/* 条件分支内的追加条件行：行首下拉决定它与上一条之间是「并且」还是「或者」 */
.rf-gc {
  box-sizing: border-box; height: 30px; display: flex; align-items: center; gap: 4px;
  padding: 0 8px 0 10px; border-top: 1px dashed var(--border);
}
/* width / min-width 必须显式写：main.css 里有全局 select { width: 100% }，
   不覆盖的话这个下拉会按容器满宽撑开且 flex-shrink:0 不收缩，把条件行挤乱。 */
.rf-jn {
  flex: 0 0 auto; width: 46px; min-width: 0; padding: 0 2px; font-size: var(--fs-s); font-family: inherit; font-weight: var(--fw-t);
  color: var(--k-if); background: var(--panel); border: 1px solid color-mix(in srgb, var(--k-if) 34%, transparent);
  border-radius: var(--radius); outline: none;
}
.rf-jn:focus { border-color: var(--accent-d); }
.rf-addc { margin-left: auto; flex: 0 0 auto; }

/* 循环参数行 */
.rf-lpr { display: flex; align-items: center; gap: 5px; padding: 5px 8px 0; }

/* 端口 */
.rf-pt {
  position: absolute; width: 12px; height: 12px; border-radius: 50%; box-sizing: border-box;
  background: var(--panel); border: 2px solid var(--muted); cursor: crosshair; z-index: 2;
}
.rf-pt:hover { border-color: var(--accent-d); background: var(--accent-l); }
.rf-pt.in { left: -7px; top: 50%; transform: translateY(-50%); }
.rf-pt.out { right: -7px; top: 50%; transform: translateY(-50%); }

/* 校验 / 日志 */
.rfe-iss { padding: 6px 10px 8px; border: 1px solid var(--border); border-top: 0; background: color-mix(in srgb, var(--red) 6%, transparent); }
.iss-h { font-size: var(--fs-s); font-weight: var(--fw-t); color: var(--red); padding-bottom: 3px; }
.iss-r { font-size: var(--fs-s); line-height: 1.6; color: var(--muted); }
.rfe-log { max-height: 132px; overflow-y: auto; padding: 6px 10px; border: 1px solid var(--border); border-top: 0; background: var(--panel); }
.lg-e { font-size: var(--fs-s); color: var(--faint); text-align: center; padding: 4px 0; }
.lg-r { display: flex; gap: 8px; font-size: var(--fs-s); padding: 1px 0; }
.lg-r .dim { flex: 0 0 auto; color: var(--faint); }
.lg-t { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>


