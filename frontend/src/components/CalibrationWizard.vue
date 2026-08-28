<template>
  <transition name="pop">
  <div class="cw-mask" @click.self="$emit('close')">
    <div class="cw-card">
      <div class="cw-head">
        <div>
          <div class="cw-title">耦合校准向导</div>
          <div class="cw-sub">{{ procLabel }} · {{ devLabel }} → 驱动参数 <b>{{ primaryTarget }}</b></div>
        </div>
        <button class="cw-x" @click="$emit('close')">✕</button>
      </div>

      <div class="cw-body">
        <!-- 1. 数据录入 -->
        <div class="cw-step">
          <span class="cw-n">1</span>
          <div>
            <div class="cw-h">本厂历史数据（设备设定值 → {{ primaryTarget }}）</div>
            <div class="cw-hint">
              每行一组：<code>设定值({{ devUnit }}) , {{ primaryTarget }}</code>
              （逗号/空格/制表符分隔，首行若为表头将自动跳过）。至少 3 组样本。
            </div>
            <textarea v-model="raw" class="cw-ta" spellcheck="false"
              :placeholder="'例如：\n' + samplePlaceholder"></textarea>
            <div class="cw-tools">
              <label class="cw-file">
                上传 CSV
                <input type="file" accept=".csv,.txt" @change="onFile" hidden />
              </label>
              <button class="cw-btn ghost" @click="loadSample">载入样例</button>
              <span class="cw-cnt" v-if="rows.length">已解析 {{ rows.length }} 组</span>
            </div>
          </div>
        </div>

        <!-- 2. 回归结果 -->
        <div class="cw-step" v-if="fit">
          <span class="cw-n">2</span>
          <div>
            <div class="cw-h">线性回归结果</div>
            <div class="cw-fit">
              <span class="cw-eq">y = <b>{{ fmt(fit.a,4) }}</b> + <b>{{ fmt(fit.b,6) }}</b> · x</span>
              <span class="cw-stat">R²（拟合优度）= <b>{{ fit.r2.toFixed(3) }}</b></span>
              <span class="cw-stat">n = <b>{{ fit.n }}</b></span>
              <span class="cw-stat">± <b>{{ fit.unc.toFixed(1) }}%</b></span>
            </div>
            <div class="cw-preview" v-if="preview">
              <div class="cw-pv">名义点 {{ coupling.nominal }} → 推算 <b>{{ primaryTarget }}</b> = {{ fmt(preview.baseVal) }}
                <i>（占基准 {{ fmt(preview.baseVal) }}%）</i></div>
              <div class="cw-pv">最低 {{ fmt(preview.lo) }} → {{ fmt(preview.atLo) }}
                <i>({{ pct(preview.atLo, preview.baseVal) }})</i></div>
              <div class="cw-pv">最高 {{ fmt(preview.hi) }} → {{ fmt(preview.atHi) }}
                <i>({{ pct(preview.atHi, preview.baseVal) }})</i></div>
              <div class="cw-pv sub" v-if="secondarySpec">次级联动：{{ secondarySpec.key }}
                = 基准 + {{ secondarySpec.ratio }} × ({{ primaryTarget }} − 基准)</div>
            </div>
          </div>
        </div>
        <div class="cw-warn" v-else-if="raw.trim() && rows.length < 3">
          ⚠ 数据不足或无法解析（需 ≥3 组数值）。
        </div>

        <!-- 3. 应用 -->
        <div class="cw-step" v-if="fit">
          <span class="cw-n">3</span>
          <div>
            <div class="cw-h">应用标定</div>
            <div class="cw-hint">
              将用本厂系数覆盖默认「{{ coupling.source === 'data' ? '已校准' : (coupling.source==='mechanism'?'机理':'经验') }}」耦合，
              并持久化到浏览器（刷新/重启后自动加载）。
            </div>
            <div class="cw-actions">
              <button class="cw-btn primary" :disabled="!canApply" @click="apply">✓ 应用并生效</button>
              <button class="cw-btn danger" v-if="isCalibrated" @click="clear">恢复默认耦合</button>
            </div>
            <div class="cw-ok" v-if="appliedNow">✓ 已写入 COUPLING_OVERRIDES，设备推算立即生效。</div>
          </div>
        </div>
      </div>
    </div>
  </div>
  </transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { getCoupling, makeCalibratedDerive, applyCalibration, clearCalibration, DEVICE_MAP, PROCESS_MAP } from '../data/flowLibrary'
import { useSimStore } from '../stores/sim'

const props = defineProps({ processType: String, deviceType: String })
const emit = defineEmits(['close', 'applied'])
const store = useSimStore()

const coupling = computed(() => getCoupling(props.processType, props.deviceType))
const targets = computed(() => (coupling.value ? String(coupling.value.target).split('/').map((s) => s.trim()) : []))
const primaryTarget = computed(() => targets.value[0] || '')
// 多参数耦合的次级联动规格（injector→coke_rate、bof→hot_metal_in）
const secondarySpec = computed(() => {
  const t = targets.value
  if (t.includes('coal_inj') && t.includes('coke_rate')) return { key: 'coke_rate', ratio: -1.1, wrt: 'coal_inj' }
  if (t.includes('scrap') && t.includes('hot_metal_in')) return { key: 'hot_metal_in', ratio: -1, wrt: 'scrap' }
  return null
})
const procLabel = computed(() => { const u = store.model.units.find((x) => x.type === props.processType); return u ? u.name : props.processType })
const devLabel = computed(() => (DEVICE_MAP[props.deviceType] ? DEVICE_MAP[props.deviceType].label : props.deviceType))
const devUnit = computed(() => (DEVICE_MAP[props.deviceType] && DEVICE_MAP[props.deviceType].unit) || '')
const spRange = computed(() => { const s = DEVICE_MAP[props.deviceType] && DEVICE_MAP[props.deviceType].setpoint; return s ? { min: s.min, max: s.max } : { min: 0, max: 1 } })
// 目标参数的名义基准（模板 def），用于示例样本；找不到时回退 100
const targetDef = computed(() => {
  const tpl = PROCESS_MAP[props.processType]
  const p = tpl && tpl.params && tpl.params.find((x) => x.key === primaryTarget.value)
  return p && p.def != null ? p.def : 100
})

const raw = ref('')
const appliedNow = ref(false)
const isCalibrated = computed(() => coupling.value && coupling.value.source === 'data')

function parseRows(text) {
  const out = []
  for (const line of String(text).split(/[\r\n]+/)) {
    const t = line.trim()
    if (!t) continue
    const parts = t.split(/[,;\t ]+/)
    if (parts.length < 2) continue
    const x = parseFloat(parts[0])
    const y = parseFloat(parts[1])
    if (isNaN(x) || isNaN(y)) continue // 跳过表头/注释
    out.push({ x, y })
  }
  return out
}
const rows = computed(() => parseRows(raw.value))

function fitLinear(rs) {
  const n = rs.length
  if (n < 3) return null
  let sx = 0, sy = 0, sxy = 0, sxx = 0
  for (const r of rs) { sx += r.x; sy += r.y; sxy += r.x * r.y; sxx += r.x * r.x }
  const denom = n * sxx - sx * sx
  if (Math.abs(denom) < 1e-9) return null
  const b = (n * sxy - sx * sy) / denom
  const a = (sy - b * sx) / n
  const meanY = sy / n
  let ssTot = 0, ssRes = 0
  for (const r of rs) { const yh = a + b * r.x; ssRes += (r.y - yh) ** 2; ssTot += (r.y - meanY) ** 2 }
  const r2 = ssTot < 1e-9 ? 1 : 1 - ssRes / ssTot
  const resStd = n > 2 ? Math.sqrt(ssRes / (n - 2)) : 0
  const meanYabs = Math.abs(meanY) < 1e-9 ? 1 : meanY
  const unc = (resStd / meanYabs) * 100 * 2 // ±2σ 相对不确定度
  return { a, b, r2, n, resStd, unc }
}
const fit = computed(() => fitLinear(rows.value))
const canApply = computed(() => !!fit.value && rows.value.length >= 3)

const preview = computed(() => {
  if (!fit.value || !coupling.value) return null
  const cal = { target: primaryTarget.value, nominal: coupling.value.nominal, a: fit.value.a, b: fit.value.b, secondary: secondarySpec.value }
  const derive = makeCalibratedDerive(cal)
  const base = 100 // 代表性基准，用于展示相对效应
  const atNom = derive(coupling.value.nominal, { [primaryTarget.value]: base })[primaryTarget.value]
  const atLo = derive(spRange.value.min, { [primaryTarget.value]: base })[primaryTarget.value]
  const atHi = derive(spRange.value.max, { [primaryTarget.value]: base })[primaryTarget.value]
  return { baseVal: atNom, atLo, atHi, lo: spRange.value.min, hi: spRange.value.max }
})

function onFile(e) {
  const file = e.target.files && e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { raw.value = String(reader.result); appliedNow.value = false }
  reader.readAsText(file)
}

const samplePlaceholder = computed(() => {
  if (!coupling.value) return ''
  const nom = coupling.value.nominal
  const base = targetDef.value
  const pts = [0.85, 0.95, 1.0, 1.05]
  return pts.map((f) => `${(nom * f).toFixed(0)}, ${(base * (1 + 0.10 * (f - 1))).toFixed(0)}`).join('\n')
})

function loadSample() {
  if (!coupling.value) return
  const nom = coupling.value.nominal
  const base = targetDef.value
  // 以「±15% 设定 → ±10% 参数」的典型斜率生成带噪声样本，便于端到端试跑
  const pts = [0.85, 0.95, 1.0, 1.05, 1.15]
  const lines = pts.map((f) => {
    const x = nom * f
    const y = base * (1 + 0.10 * (f - 1)) + (Math.random() - 0.5) * 1.5
    return `${x.toFixed(1)}, ${y.toFixed(2)}`
  })
  raw.value = lines.join('\n')
  appliedNow.value = false
}

function apply() {
  if (!fit.value) return
  const cal = {
    target: primaryTarget.value,
    nominal: coupling.value.nominal,
    a: fit.value.a,
    b: fit.value.b,
    secondary: secondarySpec.value,
    basis: `本厂SCADA（数据采集与监视控制系统）回归：y = ${fmt(fit.value.a, 4)} + ${fmt(fit.value.b, 6)}·x（R²（拟合优度）=${fit.value.r2.toFixed(3)}，n=${fit.value.n}）`,
    uncertainty: `±${fit.value.unc.toFixed(1)}%`,
    n: fit.value.n,
    r2: Number(fit.value.r2.toFixed(3)),
  }
  applyCalibration(props.processType, props.deviceType, cal)
  appliedNow.value = true
  emit('applied')
}
function clear() {
  clearCalibration(props.processType, props.deviceType)
  appliedNow.value = false
  emit('applied')
}

function fmt(n, d = 2) { return n == null ? '—' : Number(n).toFixed(d) }
function pct(v, base) {
  if (base == null || base === 0) return '—'
  const d = (v - base) / base * 100
  return (d >= 0 ? '+' : '') + d.toFixed(1) + '%'
}
</script>

<style scoped>
.cw-mask { position: fixed; inset: 0; background: rgba(8,20,35,.55); z-index: 50;
  display: flex; align-items: center; justify-content: center; padding: 20px; }
.cw-card { width: 560px; max-width: 96vw; max-height: 92vh; overflow: auto; background: #fff;
  border-radius: 4px; box-shadow: 0 18px 50px rgba(0,0,0,.28); border: 1px solid #d8dee6; }
.cw-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 16px 18px;
  border-bottom: 1px solid #eef1f5; }
.cw-title { font-size: 14px; font-weight: 700; }
.cw-sub { font-size: 12px; color: #6b7785; margin-top: 3px; }
.cw-sub b { color: #0860A8; }
.cw-x { border: none; background: transparent; font-size: 14px; color: #8a96a3; cursor: pointer; }
.cw-x:hover { color: #222; }
.cw-body { padding: 14px 18px 20px; }
.cw-step { display: flex; gap: 12px; margin-bottom: 16px; }
.cw-n { flex: 0 0 22px; height: 22px; border-radius: 50%; background: #0860A8; color: #fff;
  font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-top: 2px; }
.cw-h { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.cw-hint { font-size: 10px; color: #6b7785; line-height: 1.5; margin-bottom: 6px; }
.cw-hint code { background: #eef3f8; padding: 1px 5px; border-radius: 4px; color: #0860A8; font-size: 10px; }
.cw-ta { width: 100%; height: 92px; resize: vertical; border: 1px solid #cfd8e2; border-radius: 8px;
  padding: 8px 10px; font-size: 12px; font-family: ui-monospace, Menlo, Consolas, monospace; line-height: 1.5; }
.cw-tools { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.cw-file { font-size: 12px; padding: 5px 11px; border: 1px solid #cfd8e2; border-radius: 7px; cursor: pointer; color: #2a3640; }
.cw-file:hover { border-color: #0860A8; color: #0860A8; }
.cw-btn { font-size: 12px; padding: 5px 12px; border-radius: 7px; border: 1px solid #cfd8e2; background: #fff; cursor: pointer; color: #2a3640; }
.cw-btn.ghost:hover { border-color: #0860A8; color: #0860A8; }
.cw-btn.primary { background: #0860A8; border-color: #0860A8; color: #fff; font-weight: 600; }
.cw-btn.primary:disabled { opacity: .45; cursor: not-allowed; }
.cw-btn.danger { color: #b5483a; border-color: #e0b4ad; }
.cw-btn.danger:hover { background: #fbeeec; }
.cw-cnt { font-size: 10px; color: #6b7785; }
.cw-fit { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; background: #f5f8fb;
  border: 1px solid #e3eaf1; border-radius: 8px; padding: 8px 11px; margin-bottom: 8px; }
.cw-eq { font-size: 12px; font-family: ui-monospace, Menlo, Consolas, monospace; }
.cw-eq b { color: #0860A8; }
.cw-stat { font-size: 12px; color: #4a5662; }
.cw-stat b { color: #2a3640; }
.cw-preview { font-size: 12px; line-height: 1.8; color: #2a3640; }
.cw-pv i { color: #6b7785; font-style: normal; font-size: 10px; }
.cw-pv.sub { color: #6b7785; }
.cw-warn { font-size: 12px; color: #b5852a; background: #fbf3e2; border: 1px solid #ecd9a8;
  border-radius: 8px; padding: 8px 11px; }
.cw-actions { display: flex; gap: 10px; margin-top: 6px; }
.cw-ok { font-size: 12px; color: #2f7d4f; margin-top: 8px; }
</style>
