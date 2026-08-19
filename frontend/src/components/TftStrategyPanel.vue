<template>
  <div class="tft-panel">
    <div class="sec tft-head-row">
      <span>{{ isSystem ? '风口热制度 · TFT（理论火焰温度）系统分析' : '风口热制度 · TFT（理论火焰温度）策略提示' }}</span>
      <span class="tft-src">焓平衡真值</span>
    </div>
    <div class="tft-card" v-if="ctx">
      <div class="tft-top">
        <div class="tft-val">
          <b :style="{ color: status.color }">{{ fmt(ctx.tft) }}</b>
          <i>℃</i>
        </div>
        <span class="tft-badge" :style="{ background: status.color }">{{ status.label }}</span>
      </div>
      <div class="tft-range">目标区间 {{ cfg.tftLow }} – {{ cfg.tftHigh }} ℃</div>

      <!-- 温度刻度条：绿色区为合规区间，圆点为当前 TFT -->
      <div class="tft-bar">
        <div class="tft-bar-ok" :style="{ left: bar.okL + '%', width: (bar.okR - bar.okL) + '%' }"></div>
        <div class="tft-bar-fill" :style="{ left: bar.tft + '%', background: status.color }"></div>
      </div>
      <div class="tft-bar-labels">
        <span>{{ fmt(bar.lo) }}</span>
        <span>{{ fmt(cfg.tftLow) }}</span>
        <span>{{ fmt(cfg.tftHigh) }}</span>
        <span>{{ fmt(bar.hi) }}</span>
      </div>

      <p class="tft-desc">{{ status.desc }}</p>

      <!-- 计算过程：TFT 公式代入具体数值（鼓风显热 + Σ燃料净放热）÷ (炉腹煤气总量 × cp) -->
      <div class="tft-calc" v-if="ctx.res">
        <div class="tft-calc-title">TFT 计算过程 · 焓平衡代入</div>
        <div class="tft-calc-row">
          <span>鼓风显热 Q<sub>air</sub> = B × cp<sub>air</sub> × t<sub>g</sub></span>
          <b>{{ fmt(ctx.res.Q_sensible_air) }} MJ/tFe</b>
        </div>
        <div class="tft-calc-row">
          <span>Σ 燃料净放热 Q<sub>fuel</sub>（含水分解）</span>
          <b>{{ fmt(ctx.res.sum_heat) }} MJ/tFe</b>
        </div>
        <div class="tft-calc-row">
          <span>其中 鼓风水分分解吸热 Q<sub>h2o</sub>（湿度 {{ fmt(ctx.res.blast_humidity) }} g/Nm³）×</span>
          <b>−{{ fmt(ctx.res.Q_h2o_decomp) }} MJ/tFe</b>
        </div>
        <div class="tft-calc-row">
          <span>炉腹煤气量 V<sub>gas</sub> = CO + H<sub>2</sub>O + H<sub>2</sub> + N<sub>2</sub> + 惰性</span>
          <b>{{ fmt(ctx.res.V_gas_total) }} Nm³/tFe</b>
        </div>
        <div class="tft-calc-formula">
          <div>TFT = ({{ fmt(ctx.res.Q_sensible_air) }} + {{ fmt(ctx.res.sum_heat) }}) ÷ ({{ fmt(ctx.res.V_gas_total) }} × {{ fmtC(cfg.cp) }})</div>
          <b>= {{ fmt(ctx.tft) }} ℃</b>
        </div>
      </div>

      <!-- 计算采用工况（系统实时参数：工序参数 + 可调设备设定折算；缺省时使用兜底默认值） -->
      <div class="tft-grid">
        <div class="tft-g"><span>热风温度</span><b>{{ fmt(ctx.inputs.tg) }} ℃</b></div>
        <div class="tft-g"><span>铁水产量</span><b>{{ fmt(ctx.inputs.hot_metal) }} t/h</b></div>
        <div class="tft-g"><span>比风量</span><b>{{ fmt(ctx.inputs.B) }} Nm³/tFe</b></div>
        <div class="tft-g"><span>富氧率</span><b>{{ fmt(ctx.inputs.wO) }} %</b></div>
        <div class="tft-g"><span>鼓风湿度</span><b>{{ fmt(ctx.inputs.blast_humidity) }} g/Nm³</b></div>
        <div class="tft-g"><span>干风量</span><b>{{ fmt(ctx.inputs.dry_air) }} Nm³/tFe</b></div>
      </div>

      <!-- 燃料分解（用量 + 单燃料净放热） -->
      <div class="tft-fuels" v-if="ctx.inputs.fuel_list.length">
        <div class="tft-f" v-for="fu in ctx.inputs.fuel_list" :key="fu.name">
          <span class="tft-fn">{{ fu.name }}</span>
          <span class="tft-fr">{{ fmt(fu.rate) }} {{ fu.fuel_type === 'gas' ? 'Nm³/t' : 'kg/t' }}</span>
        </div>
        <div class="tft-f total">
          <span class="tft-fn">Σ 燃料净放热</span>
          <span class="tft-fr">{{ fmt(ctx.res.sum_heat) }} MJ/t</span>
        </div>
      </div>

      <!-- 设备级：当前设备调节影响（基于算法探测的真实影响方向） -->
      <div class="tft-dev" v-if="!isSystem && devImpact && devImpact.length">
        <div class="tft-dev-title">当前设备调节影响</div>
        <div class="tft-imp" v-for="(im, i) in devImpact" :key="i">
          <span class="tft-imp-op">{{ im.dir }}{{ im.label }}（±{{ im.step }}{{ im.unit }}）</span>
          <span class="tft-imp-delta" :style="{ color: im.delta >= 0 ? '#e8a23d' : '#6ab0f3' }">{{ deltaLabel(im.delta) }}</span>
        </div>
      </div>

      <!-- 操作建议：系统级=全部可调设备完整建议；设备级=仅当前设备建议 -->
      <div class="tft-dev-title" style="margin-top: 10px">
        {{ isSystem ? '系统操作建议 · 全部可调设备' : '操作建议 · 当前设备' }}
      </div>
      <div class="tft-adv" v-for="(a, i) in advices" :key="i">
        <span class="tft-adv-dir" :style="{ background: a.dir === '✓' ? 'var(--accent2)' : a.dir === '!' ? '#888' : status.color }">{{ a.dir }}</span>
        <div class="tft-adv-txt">
          <span class="tft-adv-dev" v-if="isSystem && a.label && a.device !== 'all'">{{ a.label }}</span>
          {{ a.text }}
        </div>
        <span class="tft-adv-delta" v-if="a.deltaLabel">{{ a.deltaLabel }}</span>
      </div>

      <div class="tft-note">
        焓平衡真值：TFT = (鼓风显热 + Σ燃料净放热) ÷ (炉腹煤气总量 × cp)。cp = {{ cfg.cp }} MJ/(Nm³·℃)。
        工况参数直接取自系统实际值（铁水产量/风量/风温/富氧/鼓风湿度/焦比/喷煤，随可调设备设定实时折算）；
        判定区间、比风量基准、燃料基础参数为可配置超参数（算法文档 §9.1）。
      </div>
    </div>
    <div class="tft-err" v-else>工况参数无效，无法计算 TFT（请检查生铁产量 / 鼓风量）。</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  DEFAULT_TFT_CONFIG, collectTftContext,
  buildDeviceTftAdvices, buildSystemTftAdvices,
  previewDeviceChange, inferDeviceSetpoints, TFT_DEVICE_PROBES,
} from '../utils/tft'

const props = defineProps({
  // 当前工序参数（系统实时值，来自 store.model.units[u].params）
  params: { type: Object, default: () => ({}) },
  // 展示模式：'device'=设备属性面板（仅当前设备建议）/ 'system'=工序面板系统分析（全部设备完整建议）
  mode: { type: String, default: 'device' },
  // 当前选中的可调设备类型（blower / hot_blast_stove / injector）
  devType: { type: String, default: '' },
  // 当前设备设定值 / 附加可调项（用于预览当前设备调节影响）
  setpoint: { type: [Number, String], default: null },
  extraSetpoints: { type: Object, default: () => ({}) },
  // 可配置超参数（缺省使用算法默认）
  config: { type: Object, default: () => DEFAULT_TFT_CONFIG },
})

const cfg = computed(() => props.config || DEFAULT_TFT_CONFIG)
const isSystem = computed(() => props.mode === 'system')

const ctx = computed(() => {
  try { return collectTftContext(props.params || {}, cfg.value) } catch (e) { return null }
})

const status = computed(() => (ctx.value ? ctx.value.status : null))

// 当前设备实际设定值（若面板能拿到），用于提升建议/影响探测的基准精度
const spOverride = computed(() => {
  const o = {}
  if (props.devType && props.setpoint != null) o[props.devType] = Number(props.setpoint)
  // 附加可调项（如鼓风机鼓风湿度）作为 blower_humidity 探测基准
  if (props.devType === 'blower' && props.extraSetpoints && props.extraSetpoints.humidity != null) {
    o.blower_humidity = Number(props.extraSetpoints.humidity)
  }
  return o
})
const advices = computed(() => {
  if (!ctx.value) return []
  try {
    if (isSystem.value) return buildSystemTftAdvices(props.params || {}, cfg.value)
    return buildDeviceTftAdvices(props.devType, props.params || {}, cfg.value, spOverride.value)
  } catch (e) { return [] }
})

// 温度条几何：绿色合规区 + 当前 TFT 标记；TFT 越界时动态扩展示范围，保证可见
const bar = computed(() => {
  if (!ctx.value) return { lo: 0, hi: 1, okL: 0, okR: 100, tft: 0 }
  let lo = cfg.value.tftLow - 300
  let hi = cfg.value.tftHigh + 300
  const t = ctx.value.tft
  if (t > hi) hi = t * 1.05
  if (t < lo) lo = t * 0.95
  const span = hi - lo
  const pos = (v) => Math.max(0, Math.min(100, ((v - lo) / span) * 100))
  return { lo, hi, okL: pos(cfg.value.tftLow), okR: pos(cfg.value.tftHigh), tft: pos(t) }
})

// 当前设备调节影响：对该设备探测「提高/降低一步」的真实 TFT 变化
const devImpact = computed(() => {
  if (!ctx.value || !props.devType) return []
  const probes = TFT_DEVICE_PROBES.filter((p) => p.type === props.devType)
  if (!probes.length) return []
  const sp = inferDeviceSetpoints(props.params || {}, cfg.value, spOverride.value)
  const out = []
  for (const pr of probes) {
    let baseSet, extra = {}
    if (pr.extraKey) {
      const skey = `blower_${pr.extraKey}` // 如 blower_humidity
      baseSet = sp[skey] != null ? sp[skey] : (pr.def != null ? pr.def : 0)
      extra = { [pr.extraKey]: baseSet }
    }
    else baseSet = pr.type === 'blower' ? sp.blower : (sp[pr.type] != null ? sp[pr.type] : 120)
    for (const [dir, sgn] of [['提高', 1], ['降低', -1]]) {
      const ns = baseSet + sgn * pr.step
      if (ns <= 0) continue
      try {
        const r = previewDeviceChange('blast_furnace', pr.type, ns, extra, props.params || {}, cfg.value)
        out.push({ label: pr.label, dir, step: pr.step, unit: pr.unit || '', delta: r.delta, tft: r.preview })
      } catch (e) { /* 跳过异常探测 */ }
    }
  }
  return out
})

function fmt(n) { return n == null || !isFinite(n) ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }
// 小数值（如 cp=0.0015）保留更多小数位展示
function fmtC(n) { return n == null || !isFinite(n) ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 4 }) }
function deltaLabel(d) { return `TFT ${d >= 0 ? '↑' : '↓'} ${Math.abs(d).toFixed(0)}℃` }
</script>

<style scoped>
.tft-panel { margin-top: 2px; }
.tft-head-row { display: flex; align-items: center; justify-content: space-between; }
.tft-src { font-size: 10px; color: var(--accent2); background: rgba(95,130,148,.10); border: 1px solid rgba(95,130,148,.28); border-radius: 10px; padding: 1px 8px; }
.tft-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-top: 6px; }
.tft-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tft-val b { font-size: 28px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1; }
.tft-val i { font-size: 12px; color: var(--muted); font-style: normal; margin-left: 3px; }
.tft-badge { font-size: 11px; padding: 3px 10px; border-radius: 12px; color: #fff; letter-spacing: .3px; white-space: nowrap; }
.tft-range { font-size: 11px; color: var(--muted); margin-top: 4px; }
.tft-bar { position: relative; height: 8px; background: var(--bg); border-radius: 4px; margin: 10px 0 4px; border: 1px solid var(--line); }
.tft-bar-ok { position: absolute; top: 0; bottom: 0; background: rgba(63,174,106,.18); }
.tft-bar-fill { position: absolute; top: -3px; width: 10px; height: 12px; border-radius: 5px; transform: translateX(-50%); box-shadow: 0 0 4px rgba(0,0,0,.35); }
.tft-bar-labels { display: flex; justify-content: space-between; font-size: 9px; color: var(--muted); font-variant-numeric: tabular-nums; }
.tft-desc { font-size: 11px; color: var(--muted); line-height: 1.55; margin: 8px 0 0; }
.tft-calc { margin-top: 10px; padding: 8px 10px; background: rgba(95,130,148,.06); border: 1px dashed var(--border); border-radius: 6px; }
.tft-calc-title { font-size: 11px; color: var(--text); font-weight: 500; margin-bottom: 4px; }
.tft-calc-row { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; font-size: 10.5px; line-height: 1.7; }
.tft-calc-row span { color: var(--muted); }
.tft-calc-row b { font-weight: 400; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tft-calc-formula { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border); font-size: 11px; }
.tft-calc-formula div { color: var(--text); font-variant-numeric: tabular-nums; }
.tft-calc-formula b { color: var(--accent2); font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tft-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 12px; margin-top: 10px; }
.tft-g { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; }
.tft-g span { color: var(--muted); }
.tft-g b { font-weight: 400; font-variant-numeric: tabular-nums; }
.tft-fuels { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--border); display: flex; flex-direction: column; gap: 3px; }
.tft-f { display: flex; justify-content: space-between; font-size: 11px; }
.tft-f .tft-fn { color: var(--muted); }
.tft-f .tft-fr { font-variant-numeric: tabular-nums; }
.tft-f.total { border-top: 1px dashed var(--border); padding-top: 4px; margin-top: 2px; }
.tft-dev-title { font-size: 11px; color: var(--text); font-weight: 500; }
.tft-imp { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 11px; margin-top: 4px; }
.tft-imp-op { color: var(--muted); }
.tft-imp-delta { font-variant-numeric: tabular-nums; white-space: nowrap; }
.tft-adv { display: flex; align-items: flex-start; gap: 8px; font-size: 11px; line-height: 1.5; margin-top: 6px; }
.tft-adv-dir { flex: none; width: 16px; height: 16px; border-radius: 50%; color: #fff; font-size: 10px; display: inline-flex; align-items: center; justify-content: center; margin-top: 1px; }
.tft-adv-txt { flex: 1; color: var(--text); }
.tft-adv-dev { display: inline-block; font-size: 10px; color: var(--accent2); background: rgba(95,130,148,.10); border: 1px solid rgba(95,130,148,.28); border-radius: 8px; padding: 0 6px; margin-right: 6px; }
.tft-adv-delta { flex: none; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tft-note { font-size: 10px; color: var(--muted); line-height: 1.6; margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--border); }
.tft-err { font-size: 12px; color: #e06c5a; background: rgba(224,108,90,.08); border: 1px solid rgba(224,108,90,.3); border-radius: 8px; padding: 10px 12px; margin-top: 6px; }
</style>
