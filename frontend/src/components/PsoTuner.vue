<!-- ============ 粒子群优化（PSO）· 在线寻优面板 ============
     编排页里「粒子群」类型模型的编排与运行体：
       优化变量 = 参与寻优的可调设备（每一台是一个维度，搜索范围取其量程）
       优化目标 = 一台传感设备 + 目标值（适应度 = |实时读数 − 目标值|）
     运行方式为在线寻优：每代把粒子的位置写入可调设备设定值，等一个采样周期后读传感实时值评估，
     迭代结束后把全局最优位置写回设备。整个过程可随时点「停止」中断。 -->
<template>
  <div class="pso">
    <!-- ══════════ 编排配置 ══════════ -->
    <div class="pso-cfg">
      <div class="pso-blk">
        <div class="pso-t">{{ t('优化变量 · 可调设备') }}<em class="pso-n mono">{{ (cfg.vars || []).length }}</em></div>
        <div v-if="!adjList.length" class="pso-emp">{{ t('当前场景没有可调设备。') }}</div>
        <div v-else class="pso-chips">
          <span v-for="d in adjList" :key="d.id" class="pso-chip adj" :class="{ on: hasVar(d.id) }"
                @click="toggleVar(d.id)">{{ d.label }}</span>
        </div>
        <div v-if="(cfg.vars || []).length" class="pso-dims">
          <div v-for="v in varDims" :key="v.id" class="pso-dim">
            <b>{{ v.label }}</b>
            <span class="mono">{{ fmt(v.lo) }} ~ {{ fmt(v.hi) }}{{ v.unit }}</span>
          </div>
        </div>
      </div>

      <div class="pso-blk">
        <div class="pso-t">{{ t('优化目标 · 传感设备趋近目标值') }}</div>
        <div class="pso-row">
          <em class="pso-lb">{{ t('观测点') }}</em>
          <select v-model="cfg.senId" class="pso-sel grow" :disabled="running">
            <option value="">{{ t('请选择传感设备') }}</option>
            <option v-for="s in senList" :key="s.id" :value="s.id">{{ s.label }}</option>
          </select>
          <em class="pso-lb">{{ t('目标值') }}</em>
          <input class="pso-num" type="number" v-model.number="cfg.target" :disabled="running" />
          <i class="pso-u">{{ targetUnit }}</i>
        </div>
        <div class="pso-row">
          <em class="pso-lb">{{ t('当前读数') }}</em>
          <b class="pso-lv mono">{{ fmt(liveOf(cfg.senId)) }}{{ targetUnit }}</b>
          <em class="pso-lb">{{ t('偏差') }}</em>
          <b class="pso-lv mono">{{ fmt(devNow) }}</b>
        </div>
      </div>

      <div class="pso-blk">
        <div class="pso-t">{{ t('粒子群参数') }}</div>
        <div class="pso-grid">
          <label class="pso-f"><em>{{ t('粒子数') }}</em><input class="pso-num" type="number" v-model.number="cfg.pNum" :disabled="running" /></label>
          <label class="pso-f"><em>{{ t('迭代代数') }}</em><input class="pso-num" type="number" v-model.number="cfg.iters" :disabled="running" /></label>
          <label class="pso-f"><em>{{ t('惯性权重') }}</em><input class="pso-num" type="number" step="0.05" v-model.number="cfg.w" :disabled="running" /></label>
          <label class="pso-f"><em>{{ t('个体因子') }}</em><input class="pso-num" type="number" step="0.1" v-model.number="cfg.c1" :disabled="running" /></label>
          <label class="pso-f"><em>{{ t('群体因子') }}</em><input class="pso-num" type="number" step="0.1" v-model.number="cfg.c2" :disabled="running" /></label>
          <label class="pso-f"><em>{{ t('采样间隔 ms') }}</em><input class="pso-num" type="number" step="100" v-model.number="cfg.waitMs" :disabled="running" /></label>
        </div>
      </div>
    </div>

    <!-- ══════════ 运行进度 ══════════ -->
    <div class="pso-run">
      <div class="pso-rhd">
        <span class="pso-st" :class="{ on: running }"><i class="dot"></i>{{ runTxt }}</span>
        <span class="pso-sp"></span>
        <span class="mono dim">{{ step }} / {{ total }}</span>
      </div>
      <div class="pso-bar"><i :style="{ width: pct + '%' }"></i></div>
      <svg class="pso-cv" viewBox="0 0 320 74" preserveAspectRatio="none">
        <polyline class="cv-g" :points="costPts" />
      </svg>
      <div class="pso-ft">
        <span class="mono">{{ t('最优偏差') }} <b>{{ fmt(bestCost) }}</b></span>
        <span class="mono dim">{{ t('上次运行') }} {{ lastRunTxt }}</span>
      </div>
      <div v-if="bestX.length" class="pso-bx">
        <div class="pso-t sm">{{ t('寻优结果（已写入设定值）') }}</div>
        <div v-for="(b, i) in bestList" :key="b.id" class="pso-dim">
          <b>{{ b.label }}</b><span class="mono">{{ fmt(b.v) }}{{ b.unit }}</span>
        </div>
      </div>
      <p class="pso-tip">{{ t('在线寻优会逐代把候选设定值写入可调设备，运行期间请勿同时手动改设定值；点「停止」可随时中断并保留当前最优。') }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { DEVICE_MAP } from '../data/flowLibrary'
import { ADJUSTABLE_MAP } from '../data/attachLibrary'
import { t } from '../i18n'

const props = defineProps({
  // 模型自带的粒子群配置（父组件持久化，本组件就地读写）
  cfg: { type: Object, required: true },
  running: { type: Boolean, default: false },
})
const emit = defineEmits(['update:running'])

const store = useSimStore()

// ─────────── 设备 ───────────
const all = computed(() => store.allDevices || [])
const adjList = computed(() => all.value.filter((d) => d.adjustable))
const senList = computed(() => all.value.filter((d) => !d.adjustable))
function devOf(id) {
  if (!id) return null
  try { return store.findDevice(id) || null } catch (e) { return null }
}
function spCfg(id) {
  const d = devOf(id)
  if (!d) return null
  const tm = d.type ? DEVICE_MAP[d.type] : null
  if (tm && tm.setpoint) return tm.setpoint
  const at = d.type ? ADJUSTABLE_MAP[d.type] : null
  return (at && at.setpoint) || null
}
function spMin(id) { const c = spCfg(id); return c ? Number(c.min) : 0 }
function spMax(id) { const c = spCfg(id); return c ? Number(c.max) : 100 }
function liveOf(id) {
  if (!id) return null
  try {
    const lv = store.deviceLiveOf(id)
    if (lv != null) return Number(lv)
    const h = store.deviceHistoryOf(id)
    if (h && h.length) return Number(h[h.length - 1].v)
  } catch (e) { /* noop */ }
  const d = devOf(id)
  if (d && d.live != null) return Number(d.live)
  if (d && d.reading != null) return Number(d.reading)
  return null
}
const targetUnit = computed(() => {
  const d = devOf(props.cfg.senId)
  return d && d.unit ? d.unit : ''
})
const devNow = computed(() => {
  const v = liveOf(props.cfg.senId)
  const tg = Number(props.cfg.target)
  if (v == null || !Number.isFinite(tg)) return null
  return Math.abs(v - tg)
})

// ─────────── 优化变量 ───────────
function hasVar(id) { return (props.cfg.vars || []).includes(id) }
function toggleVar(id) {
  if (props.running) return
  const arr = Array.isArray(props.cfg.vars) ? props.cfg.vars.slice() : []
  const i = arr.indexOf(id)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(id)
  props.cfg.vars = arr
}
const varDims = computed(() => (props.cfg.vars || []).map((id) => {
  const d = devOf(id)
  return { id, label: (d && d.label) || id, unit: (d && d.unit) || '', lo: spMin(id), hi: spMax(id) }
}).filter((v) => Number.isFinite(v.lo) && Number.isFinite(v.hi) && v.hi > v.lo))

// ─────────── 运行 ───────────
const running = computed(() => props.running)
const gen = ref(0)
const step = ref(0)
const total = ref(0)
const bestCost = ref(null)
const curve = ref([])
const bestX = ref([])
let cancel = false

const pct = computed(() => (total.value ? Math.min(100, Math.round((step.value / total.value) * 100)) : 0))
const runTxt = computed(() => {
  if (!running.value) return t('已停止')
  return `${t('寻优中')} ${gen.value}/${clampNum(props.cfg.iters, 12, 2, 100)}`
})
const bestList = computed(() => bestX.value.map((v, i) => {
  const dim = varDims.value[i]
  return { id: (dim && dim.id) || String(i), label: (dim && dim.label) || '', unit: (dim && dim.unit) || '', v }
}))
const costPts = computed(() => {
  const c = curve.value
  if (c.length < 2) return ''
  const vals = c.map((p) => p.cost)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const sp = (hi - lo) || 1
  return c.map((p, i) => `${((i / (c.length - 1)) * 320).toFixed(1)},${(70 - ((p.cost - lo) / sp) * 64).toFixed(1)}`).join(' ')
})
const lastRun = ref(0)
const lastRunTxt = computed(() => (lastRun.value ? shortTs(lastRun.value) : '—'))

function clampNum(v, def, lo, hi) {
  const n = Number(v)
  if (!Number.isFinite(n)) return def
  return Math.min(hi, Math.max(lo, Math.round(n)))
}
function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)) }

function applyVars(x, dims) {
  for (let i = 0; i < dims.length; i++) store.setDeviceSetpoint(dims[i].id, Number(x[i]))
}
function costNow() {
  const v = liveOf(props.cfg.senId)
  const tg = Number(props.cfg.target)
  if (v == null || !Number.isFinite(tg)) return null
  return Math.abs(v - tg)
}

async function search() {
  const dims = varDims.value
  const tg = Number(props.cfg.target)
  if (!dims.length || !props.cfg.senId || !Number.isFinite(tg)) {
    store.showToast(t('请先选择优化变量（可调设备）与优化目标（传感设备 + 目标值）。'), 'warn')
    emit('update:running', false)
    return
  }
  cancel = false
  const N = clampNum(props.cfg.pNum, 8, 3, 30)
  const G = clampNum(props.cfg.iters, 12, 2, 100)
  const w = Number(props.cfg.w) || 0.7
  const c1 = Number(props.cfg.c1) || 1.5
  const c2 = Number(props.cfg.c2) || 1.5
  const wait = clamp(Number(props.cfg.waitMs) || 800, 200, 10000)

  curve.value = []
  bestCost.value = null
  bestX.value = []
  gen.value = 0
  step.value = 0
  total.value = N * G

  const ps = []
  for (let i = 0; i < N; i++) {
    const x = dims.map((d) => d.lo + Math.random() * (d.hi - d.lo))
    const v = dims.map((d) => (Math.random() * 2 - 1) * (d.hi - d.lo) * 0.1)
    ps.push({ x, v, bx: x.slice(), bc: Infinity })
  }
  let gx = ps[0].x.slice()
  let gc = Infinity

  for (let g = 1; g <= G; g++) {
    if (cancel) break
    gen.value = g
    for (let i = 0; i < N; i++) {
      if (cancel) break
      applyVars(ps[i].x, dims)
      step.value = (g - 1) * N + i + 1
      await sleep(wait)
      const c = costNow()
      if (c != null && Number.isFinite(c)) {
        if (c < ps[i].bc) { ps[i].bc = c; ps[i].bx = ps[i].x.slice() }
        if (c < gc) { gc = c; gx = ps[i].x.slice(); bestCost.value = gc; bestX.value = gx.slice() }
      }
    }
    if (cancel) break
    curve.value.push({ it: g, cost: gc })
    for (const p of ps) {
      for (let k = 0; k < dims.length; k++) {
        const r1 = Math.random()
        const r2 = Math.random()
        p.v[k] = w * p.v[k] + c1 * r1 * (p.bx[k] - p.x[k]) + c2 * r2 * (gx[k] - p.x[k])
        p.x[k] = clamp(p.x[k] + p.v[k], dims[k].lo, dims[k].hi)
      }
    }
  }

  if (!cancel) {
    applyVars(gx, dims)
    bestCost.value = gc
    bestX.value = gx.slice()
    lastRun.value = Date.now()
    store.showToast(`${t('寻优完成')} · ${t('最优偏差')} ${fmt(gc)}`, 'success')
  }
  emit('update:running', false)
}

watch(() => props.running, (on) => {
  if (on) search()
  else cancel = true
})
onBeforeUnmount(() => { cancel = true })

// ─────────── 格式化 ───────────
function fmt(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 1 : 2 })
}
function p2(n) { return String(n).padStart(2, '0') }
function shortTs(ts) {
  const d = new Date(ts)
  return `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}
</script>

<style scoped>
.pso { display: flex; gap: 10px; align-items: flex-start; flex-wrap: wrap; }
.pso-cfg { flex: 1 1 460px; min-width: 320px; display: flex; flex-direction: column; gap: 8px; }
.pso-run { flex: 0 0 340px; min-width: 280px; display: flex; flex-direction: column; gap: 6px; }

.pso-blk { padding: 7px 9px 9px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px; }
.pso-t { font-size: 11px; font-weight: 600; color: var(--text); padding-bottom: 5px; }
.pso-t.sm { font-size: 10px; color: var(--muted); padding-top: 2px; }
.pso-n { font-style: normal; margin-left: 5px; font-size: 10px; color: var(--faint); }
.pso-emp { font-size: 10px; color: var(--faint); }

.pso-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.pso-chip {
  padding: 1px 8px; font-size: 10.5px; border-radius: 10px; cursor: pointer;
  color: var(--muted); background: var(--panel); border: 1px solid var(--border);
}
.pso-chip.adj.on { color: #fff; background: #D97A21; border-color: transparent; }
.pso-chip:hover { border-color: var(--accent2); }
.pso-dims { display: flex; flex-wrap: wrap; gap: 4px 12px; padding-top: 6px; }
.pso-dim { display: flex; align-items: baseline; gap: 6px; font-size: 10px; color: var(--muted); }
.pso-dim b { font-weight: 600; color: var(--text); font-size: 10.5px; }

.pso-row { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
.pso-lb { font-style: normal; flex: 0 0 auto; font-size: 10.5px; color: var(--muted); }
.pso-sel, .pso-num {
  min-width: 0; padding: 2px 4px; font-size: 11px; font-family: inherit; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none;
}
.pso-sel:focus, .pso-num:focus { border-color: var(--accent2); }
.pso-sel.grow { flex: 1 1 auto; }
.pso-num { width: 76px; text-align: right; font-family: var(--mono); }
.pso-u { font-style: normal; font-size: 10px; color: var(--faint); }
.pso-lv { font-size: 11px; color: var(--accent-d); }

.pso-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 4px 10px; }
.pso-f { display: flex; align-items: center; gap: 5px; }
.pso-f em { font-style: normal; flex: 1 1 auto; font-size: 10.5px; color: var(--muted); }
.pso-f .pso-num { width: 62px; }

.pso-rhd { display: flex; align-items: center; gap: 6px; }
.pso-sp { flex: 1 1 auto; }
.pso-st { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--faint); }
.pso-st .dot { width: 7px; height: 7px; border-radius: 50%; background: #888; }
.pso-st.on { color: var(--green); }
.pso-st.on .dot { background: var(--green); animation: pso-pulse 1s infinite; }
@keyframes pso-pulse { 50% { opacity: .35; } }
.pso-bar { height: 5px; background: var(--bar); border-radius: 3px; overflow: hidden; }
.pso-bar i { display: block; height: 100%; background: var(--accent-d); transition: width .2s; }
.pso-cv { width: 100%; height: 74px; background: var(--panel); border: 1px solid var(--border); border-radius: 3px; }
.pso-cv .cv-g { fill: none; stroke: var(--accent-d); stroke-width: 1.6; vector-effect: non-scaling-stroke; }
.pso-ft { display: flex; align-items: center; gap: 10px; font-size: 10px; color: var(--muted); }
.pso-ft b { color: var(--accent-d); }
.pso-bx { padding-top: 2px; }
.pso-tip { font-size: 9.5px; color: var(--faint); line-height: 1.6; }

.mono { font-family: var(--mono); }
.dim { color: var(--faint); }
</style>
