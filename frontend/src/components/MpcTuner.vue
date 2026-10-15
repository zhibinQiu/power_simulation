<!-- ============ 模型预测控制（MPC）· 滚动优化面板 ============
     编排页里「MPC」类型模型的编排与运行体：
       控制回路 = 一台可调设备（操控量 u）+ 一台传感设备（被控量 y），按左栏勾选顺序一一配对；
       过程模型  = 带纯滞后的一阶模型  y[k+1] = a·y[k] + b·u[k−d] + bias
                   （a = e^(−Ts/τ)、b = K(1−a)；bias 每拍用实测值校正，吸收扰动与模型误差）；
       每拍求解  = 预测时域 Np 内只优化一个调节增量 Δu（SSTO，单步到端）：
                   J = Σ (y_free[i] + sᵢ·Δu − r)² + λ′·Δu²  →  Δu* = −Σ sᵢ·eᵢ / (Σ sᵢ² + λ′)
       在线辨识  = 递推最小二乘（遗忘因子 0.98）实时修正 a / b / bias；纯滞后 θ 由用户给定。
     运行中每拍把求出的 u 写入可调设备设定值（已绑定数据源的设备同步下发）。 -->
<template>
  <div class="mpc">
    <!-- ══════════ 编排配置 ══════════ -->
    <div class="mpc-cfg">
      <div class="mpc-blk">
        <div class="mpc-t">{{ t('控制回路') }}<em class="mpc-n mono">{{ loops.length }}</em></div>
        <div v-if="!loops.length" class="mpc-emp">{{ t('请先在左栏勾选可调设备与传感设备（按勾选顺序一一配对形成控制回路）。') }}</div>
        <div v-for="lp in loops" :key="lp.key" class="mpc-lp">
          <div class="lp-hd">
            <b>{{ lp.adjLabel }}</b><i class="ar">←</i><span>{{ lp.senLabel }}</span>
            <span class="lp-sp"></span>
            <span class="kv"><em>y</em><b class="mono">{{ fmt(yOf(lp)) }}</b></span>
            <span class="kv"><em>u</em><b class="mono">{{ fmt(uOf(lp)) }}</b></span>
            <span class="kv"><em>Δu</em><b class="mono">{{ fmt(duOf(lp)) }}</b></span>
          </div>
          <div class="lp-row">
            <em class="lp-lb">{{ t('目标值') }} r</em>
            <input class="mpc-num" type="number" :value="targetOf(lp)" :step="stepOf(lp)" :disabled="running"
                   @change="setTargetOf(lp, $event.target.value)" />
            <i class="mpc-u">{{ senUnit(lp) }}</i>
            <em class="lp-lb" :title="t('稳态增益：操控量变化 1 个单位时被控量的稳态变化量（负值表示反向）')">{{ t('增益') }} K</em>
            <input class="mpc-num" type="number" step="0.1" :value="mdOf(lp).K" :disabled="running || cfg.ident"
                   @change="mdOf(lp).K = Number($event.target.value)" />
            <em class="lp-lb">{{ t('时间常数') }} τ</em>
            <input class="mpc-num" type="number" step="1" min="1" :value="mdOf(lp).tau" :disabled="running || cfg.ident"
                   @change="mdOf(lp).tau = Number($event.target.value)" /><i class="mpc-u">s</i>
            <em class="lp-lb">{{ t('纯滞后') }} θ</em>
            <input class="mpc-num" type="number" step="1" min="0" :value="mdOf(lp).theta" :disabled="running"
                   @change="mdOf(lp).theta = Number($event.target.value)" /><i class="mpc-u">s</i>
          </div>
          <div class="lp-row st">
            <span class="tag" :class="{ on: cfg.ident && (estOf(lp) ? estOf(lp).n : 0) > 3 }">{{ identTxtOf(lp) }}</span>
            <span v-if="estOf(lp)" class="dim mono">K {{ fmt(estOf(lp).K) }} · τ {{ fmt(estOf(lp).tau) }}s · θ {{ fmt(mdOf(lp).theta) }}s</span>
            <span class="dim mono">{{ t('量程') }} {{ fmt(uMin(lp)) }} ~ {{ fmt(uMax(lp)) }}{{ uUnit(lp) }}</span>
          </div>
        </div>
      </div>

      <div class="mpc-blk">
        <div class="mpc-t">{{ t('预测控制参数') }}</div>
        <div class="mpc-grid">
          <label class="mpc-f"><em>{{ t('预测时域') }} Np</em><input class="mpc-num" type="number" min="1" max="60" step="1" v-model.number="cfg.np" :disabled="running" /></label>
          <label class="mpc-f"><em>{{ t('控制周期') }}</em><input class="mpc-num" type="number" min="1" max="600" step="1" v-model.number="cfg.ts" :disabled="running" /><i class="mpc-u">s</i></label>
          <label class="mpc-f"><em>{{ t('增量权重') }} λ</em><input class="mpc-num" type="number" min="0" step="0.01" v-model.number="cfg.lam" :disabled="running" /></label>
          <label class="mpc-f"><em>{{ t('单步限幅') }}</em><input class="mpc-num" type="number" min="0" step="0.1" v-model.number="cfg.duMax" :disabled="running" /></label>
          <label class="mpc-f chk" :title="t('运行中按实测数据递推修正增益 K 与时间常数 τ；关闭则只使用上面填写的模型参数')">
            <input type="checkbox" v-model="cfg.ident" :disabled="running" /><em>{{ t('在线辨识模型') }}</em>
          </label>
        </div>
        <p class="mpc-tip">{{ t('每拍按模型预测未来 Np 步，解出使被控量最贴近目标值、且调节动作最小的 Δu 并下发；λ 越大动作越平缓，单步限幅 0 表示不限。') }}</p>
      </div>
    </div>

    <!-- ══════════ 运行 ══════════ -->
    <div class="mpc-run">
      <div class="mpc-rhd">
        <span class="mpc-st" :class="{ on: running }"><i class="dot"></i>{{ runTxt }}</span>
        <span class="mpc-sp"></span>
        <span class="mono dim">{{ t('拍数') }} {{ ticks }}</span>
      </div>
      <svg class="mpc-cv" viewBox="0 0 320 74" preserveAspectRatio="none">
        <polyline class="cv-r" :points="refPts" />
        <polyline class="cv-y" :points="yPts" />
      </svg>
      <div class="mpc-ft">
        <span class="mono">{{ t('目标') }} <b class="r">{{ fmt(lastR) }}</b></span>
        <span class="mono">{{ t('实测') }} <b>{{ fmt(lastY) }}</b></span>
        <span class="mono dim">{{ t('偏差') }} <b>{{ fmt(lastDev) }}</b></span>
      </div>
      <p class="mpc-tip">{{ t('曲线为第一个回路的实测值与目标值（横轴为控制拍）；运行期间由算法自动写入设定值，请勿手动改动。') }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { DEVICE_MAP } from '../data/flowLibrary'
import { ADJUSTABLE_MAP } from '../data/attachLibrary'
import { t } from '../i18n'

const props = defineProps({
  // 模型自带的 MPC 配置（父组件持久化，本组件就地读写）
  cfg: { type: Object, required: true },
  // 控制回路：父组件按左栏勾选顺序配对得到 [{ key, adjId, senId, adjLabel, senLabel }]
  loops: { type: Array, default: () => [] },
  // 传感设备 id -> 目标值（父组件持久化的设定目标）
  targets: { type: Object, default: () => ({}) },
  running: { type: Boolean, default: false },
})
const emit = defineEmits(['update:running'])

const store = useSimStore()

// ─────────── 设备 ───────────
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
function uMin(lp) { const c = spCfg(lp.adjId); return c ? Number(c.min) : 0 }
function uMax(lp) { const c = spCfg(lp.adjId); return c ? Number(c.max) : 100 }
function uUnit(lp) { const c = spCfg(lp.adjId); return (c && (c.unit || c.label)) || '' }
function senUnit(lp) { const d = devOf(lp.senId); return (d && d.unit) || '' }
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
/** 当前操控量（设定值）：store 覆盖 → 设备实例 → 量程内 0 */
function curU(lp) {
  const v = store.deviceSetpoints ? store.deviceSetpoints[lp.adjId] : null
  if (v != null && Number.isFinite(Number(v))) return Number(v)
  const d = devOf(lp.adjId)
  if (d && d.setpoint != null && Number.isFinite(Number(d.setpoint))) return Number(d.setpoint)
  return clamp(0, uMin(lp), uMax(lp))
}
function targetOf(lp) {
  const v = props.targets ? props.targets[lp.senId] : null
  if (v != null && Number.isFinite(Number(v))) return Number(v)
  const lv = liveOf(lp.senId)
  return lv == null ? 0 : Number((Math.abs(lv) * 1.05).toFixed(4))
}
function setTargetOf(lp, v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return
  props.targets[lp.senId] = n
}
function stepOf(lp) {
  const v = Math.abs(Number(targetOf(lp)) || 1)
  if (v >= 1000) return 10
  if (v >= 100) return 1
  if (v >= 10) return 0.5
  return 0.1
}

// ─────────── 过程模型参数（K / τ / θ） ───────────
function mdOf(lp) {
  if (!props.cfg.md) props.cfg.md = {}
  const k = lp.key
  if (!props.cfg.md[k]) props.cfg.md[k] = { K: 1, tau: 60, theta: 0 }
  return props.cfg.md[k]
}

// ─────────── 运行态（每个回路一份，非响应式） ───────────
const st = new Map()      // loopKey -> { uHist, yPrev, a, b, bias, u, du, y, n, P, th }
const est = reactive({})  // loopKey -> { K, tau, n }（辨识结果，供展示）
const hist = ref([])      // 曲线：第一个回路的 { y, r }
const ticks = ref(0)
let timer = null
let cancel = false

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }
function num(v, def) { const n = Number(v); return Number.isFinite(n) ? n : def }
function dtSec() { return clamp(num(props.cfg.ts, 5), 1, 600) }
function npSteps() { return Math.round(clamp(num(props.cfg.np, 10), 1, 60)) }

function yOf(lp) { const s = st.get(lp.key); return s && s.y != null ? s.y : liveOf(lp.senId) }
function uOf(lp) { const s = st.get(lp.key); return s ? s.u : curU(lp) }
function duOf(lp) { const s = st.get(lp.key); return s ? s.du : null }
function estOf(lp) { return est[lp.key] || null }

/** 历史操控量：idx 越界时取最旧的一条（等效于「此前一直保持该值」） */
function histU(s, idx) {
  const H = s.uHist
  if (!H.length) return s.u || 0
  return H[clamp(idx, 0, H.length - 1)]
}

function initLoop(lp) {
  const u = curU(lp)
  const dt = dtSec()
  const md = mdOf(lp)
  const a0 = clamp(Math.exp(-dt / Math.max(1, num(md.tau, 60))), 0.2, 0.9999)
  st.set(lp.key, {
    uHist: [u], yPrev: null, u, du: 0, y: null, n: 0, lastUd: u,
    a: a0, b: num(md.K, 1) * (1 - a0), bias: 0,
    th: [a0, num(md.K, 1) * (1 - a0), 0], P: [[10, 0, 0], [0, 10, 0], [0, 0, 10]],
  })
  delete est[lp.key]
}

// ─────────── 递推最小二乘（遗忘因子 0.98，三参数 [a, b, c]） ───────────
const FORGET = 0.98
function resetRls(s, a, b) {
  s.th = [a, b, 0]
  s.P = [[10, 0, 0], [0, 10, 0], [0, 0, 10]]
}
function rlsUpdate(s, phi, y, a0, b0) {
  const P = s.P
  const th = s.th
  const Pphi = [0, 0, 0]
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) Pphi[i] += P[i][j] * phi[j]
  let den = FORGET
  for (let i = 0; i < 3; i++) den += phi[i] * Pphi[i]
  if (!Number.isFinite(den) || den < 1e-9) { resetRls(s, a0, b0); return }
  let yhat = 0
  for (let i = 0; i < 3; i++) yhat += th[i] * phi[i]
  const e = y - yhat
  for (let i = 0; i < 3; i++) th[i] += (Pphi[i] / den) * e
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) P[i][j] = (P[i][j] - (Pphi[i] / den) * Pphi[j]) / FORGET
  // 参数守卫：a 必须落在 (0,1) 且数值可用，否则退回先验模型重来
  if (!th.every((v) => Number.isFinite(v)) || Math.abs(th[1]) > 1e6) { resetRls(s, a0, b0); return }
  th[0] = clamp(th[0], 0.2, 0.9999)
  s.a = th[0]
  s.b = th[1]
  s.bias = th[2]
}

function tick() {
  if (cancel) return
  const dt = dtSec()
  const Np = npSteps()
  const lam = Math.max(0, num(props.cfg.lam, 0.02))
  const duLim = Math.max(0, num(props.cfg.duMax, 0))
  let first = null
  for (const lp of props.loops) {
    const s = st.get(lp.key)
    if (!s) continue
    const y = liveOf(lp.senId)
    if (y == null || !Number.isFinite(y)) continue
    s.y = y
    const md = mdOf(lp)
    const d = clamp(Math.round(num(md.theta, 0) / dt), 0, 30)
    const r = targetOf(lp)
    const aManual = clamp(Math.exp(-dt / Math.max(1, num(md.tau, 60))), 0.2, 0.9999)
    const bManual = num(md.K, 1) * (1 - aManual)
    // 上一拍生效的操控量：u[k−1−d]（uHist 末位是上一拍发出的 u[k−1]）
    const uDelayed = histU(s, s.uHist.length - 1 - d)
    if (s.yPrev == null) {           // 首拍只建基准，不动输出
      s.yPrev = y
      s.a = aManual
      s.b = bManual
      continue
    }
    if (props.cfg.ident) {
      // 数据无变化（u 与 y 都没动）时跳过：此时 a/b 在数值上不可辨识，更新只会放大协方差
      if (Math.abs(y - s.yPrev) > 1e-9 || Math.abs(uDelayed - s.lastUd) > 1e-9) {
        rlsUpdate(s, [s.yPrev, uDelayed, 1], y, aManual, bManual)
        s.n++
      }
    } else {
      s.a = aManual
      s.b = bManual
      s.bias = y - (aManual * s.yPrev + bManual * uDelayed)
      s.n++
    }
    s.lastUd = uDelayed

    // ── 预测：自由响应（Δu=0）与灵敏度 sᵢ = b(1−a^(i−d))/(1−a) ──
    const a = s.a
    const b = s.b
    const bias = Number.isFinite(s.bias) ? s.bias : 0
    let yFree = y
    let sCum = 0
    let sumSe = 0
    let sumS2 = 0
    for (let i = 1; i <= Np; i++) {
      const j = i - 1 - d
      yFree = a * yFree + b * (j >= 0 ? s.u : histU(s, s.uHist.length + j)) + bias
      if (i > d) {
        sCum = sCum * a + b
        sumSe += sCum * (yFree - r)
        sumS2 += sCum * sCum
      }
    }
    // 权重按量程归一化：λ′ = λ·(y尺度/u量程)²，使 λ 与工程量纲无关
    const yScale = Math.max(1e-6, Math.abs(r) || Math.abs(y) || 1)
    const uRange = Math.max(1e-6, uMax(lp) - uMin(lp))
    const lamEff = lam * Math.pow(yScale / uRange, 2)
    let du = sumS2 > 1e-12 ? -sumSe / (sumS2 + lamEff) : 0
    if (!Number.isFinite(du)) du = 0
    if (duLim > 0) du = clamp(du, -duLim, duLim)
    const uNew = clamp(s.u + du, uMin(lp), uMax(lp))
    if (Math.abs(uNew - s.u) > 1e-9) store.setExtSetpoint(lp.adjId, uNew, { silent: true })
    s.du = uNew - s.u
    s.u = uNew
    s.uHist.push(uNew)
    if (s.uHist.length > 64) s.uHist.shift()
    s.yPrev = y
    // 展示用的等效一阶参数：K = b/(1−a)、τ = −dt/ln(a)
    const tau = a > 0.2 && a < 1 ? -dt / Math.log(a) : null
    est[lp.key] = { K: b / (1 - a), tau, n: s.n }
    if (!first) first = { y, r }
  }
  if (first) {
    ticks.value++
    const h = hist.value.slice()
    h.push(first)
    if (h.length > 120) h.shift()
    hist.value = h
  }
}

function start() {
  const lps = props.loops || []
  if (!lps.length) {
  store.showToast(t('MPC：请先在左栏勾选可调设备与传感设备（按勾选顺序一一配对形成控制回路）。'), 'warn')
    emit('update:running', false)
    return
  }
  cancel = false
  hist.value = []
  ticks.value = 0
  for (const lp of lps) initLoop(lp)
  tick()
  if (timer) clearInterval(timer)
  timer = setInterval(tick, Math.round(dtSec() * 1000))
}
function stop() {
  cancel = true
  if (timer) { clearInterval(timer); timer = null }
}

const running = computed(() => props.running)
watch(running, (on) => { if (on) start(); else stop() }, { immediate: true })
// 运行途中改控制周期：按新周期重启定时器（不等到下一拍结束）
watch(() => num(props.cfg.ts, 5), () => {
  if (!running.value || cancel) return
  if (timer) clearInterval(timer)
  timer = setInterval(tick, Math.round(dtSec() * 1000))
})
onBeforeUnmount(() => stop())

// ─────────── 展示 ───────────
const runTxt = computed(() => (running.value ? t('MPC 运行中') : t('已停止')))
function identTxtOf(lp) {
  if (!props.cfg.ident) return t('手动模型')
  const e = estOf(lp)
  if (!e || e.n <= 3) return t('辨识中')
  return t('已辨识')
}
const lastY = computed(() => (hist.value.length ? hist.value[hist.value.length - 1].y : null))
const lastR = computed(() => (hist.value.length ? hist.value[hist.value.length - 1].r : null))
const lastDev = computed(() => (lastY.value == null || lastR.value == null ? null : Math.abs(lastY.value - lastR.value)))
const yPts = computed(() => ptsOf((p) => p.y))
const refPts = computed(() => ptsOf((p) => p.r))
function ptsOf(get) {
  const h = hist.value
  if (h.length < 2) return ''
  const vals = []
  for (const p of h) { vals.push(Number(get(p)) || 0); vals.push(Number(p.r) || 0) }
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const sp = (hi - lo) || 1
  return h.map((p, i) => `${((i / (h.length - 1)) * 320).toFixed(1)},${(70 - ((Number(get(p)) || 0) - lo) / sp * 64).toFixed(1)}`).join(' ')
}

function fmt(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 1 : 2 })
}
</script>

<style scoped>
/* ══════════ 模型预测控制（MPC）· 视觉规范（与群控主页共用同一套令牌） ══════════
   区块标题 12/600，正文 11，辅助 10；彩色只给「选中态 · 关键数值 · 运行中的状态」 */

.mpc { display: flex; gap: 10px; align-items: flex-start; flex-wrap: wrap; }
.mpc em, .mpc i { font-style: normal; }
.dim { color: var(--faint); }

.mpc-cfg { flex: 1 1 460px; min-width: 320px; display: flex; flex-direction: column; gap: 10px; }
.mpc-run { flex: 0 0 340px; min-width: 280px; display: flex; flex-direction: column; gap: 8px; }

.mpc-blk {
  display: flex; flex-direction: column; gap: 8px; padding: 10px 12px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: var(--radius);
}
.mpc-t { font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--text); }
.mpc-n { margin-left: 5px; font-size: var(--fs-s); color: var(--faint); }
.mpc-emp { font-size: var(--fs-s); color: var(--faint); }

.mpc-lp { display: flex; flex-direction: column; gap: 6px; padding: 6px 8px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); }
.lp-hd { display: flex; align-items: center; gap: 6px; font-size: var(--fs-b); }
.lp-hd b { font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--text); }
.lp-hd .ar { color: var(--faint); }
.lp-hd > span:not(.lp-sp):not(.kv) { color: var(--muted); }
.lp-sp { flex: 1 1 auto; }
.lp-hd .kv { display: inline-flex; align-items: baseline; gap: 4px; }
.lp-hd .kv em { font-size: var(--fs-s); color: var(--faint); }
.lp-hd .kv b { font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--accent-d); }
.lp-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.lp-row.st { gap: 10px; font-size: var(--fs-s); }
.lp-lb { flex: 0 0 auto; font-size: var(--fs-s); color: var(--muted); white-space: nowrap; }
.mpc-num, .mpc-sel {
  min-width: 0; padding: 3px 6px; font-size: var(--fs-b); color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); outline: none;
}
.mpc-num { width: 68px; text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
.mpc-num:disabled { opacity: .5; }
.mpc-num:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); }
.mpc-u { flex: 0 0 auto; font-size: var(--fs-s); color: var(--faint); }
.tag { padding: 1px 6px; font-size: var(--fs-s); color: var(--muted); background: var(--bar); border-radius: 8px; }
.tag.on { color: var(--on-accent); background: var(--k-adj); }

.mpc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 6px 12px; }
.mpc-f { display: flex; align-items: center; gap: 6px; }
.mpc-f em { flex: 1 1 auto; font-size: var(--fs-s); color: var(--muted); white-space: nowrap; }
.mpc-f .mpc-num { width: 62px; }
.mpc-f.chk em { flex: 0 0 auto; }
.mpc-tip { margin: 0; font-size: var(--fs-s); line-height: 1.6; color: var(--faint); }

.mpc-rhd { display: flex; align-items: center; gap: 6px; }
.mpc-sp { flex: 1 1 auto; }
.mpc-st { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-s); color: var(--faint); }
.mpc-st .dot { flex: 0 0 auto; width: 6px; height: 6px; border-radius: 50%; background: var(--faint); }
.mpc-st.on { color: var(--green); }
.mpc-st.on .dot { background: var(--green); animation: mpc-pulse 1s infinite; }
@keyframes mpc-pulse { 50% { opacity: .35; } }
.mpc-cv { width: 100%; height: 74px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); }
.mpc-cv .cv-y { fill: none; stroke: var(--accent-d); stroke-width: 1.6; vector-effect: non-scaling-stroke; }
.mpc-cv .cv-r { fill: none; stroke: var(--faint); stroke-width: 1.2; stroke-dasharray: 4 3; vector-effect: non-scaling-stroke; }
.mpc-ft { display: flex; align-items: center; gap: 12px; font-size: var(--fs-s); color: var(--muted); }
.mpc-ft b { font-weight: var(--fw-m); color: var(--accent-d); font-variant-numeric: tabular-nums; }
.mpc-ft b.r { color: var(--faint); font-weight: 400; }
</style>
