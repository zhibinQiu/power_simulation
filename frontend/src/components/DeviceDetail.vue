<template>
  <div v-if="info && dev" class="dev-insp">
    <div class="insp-head">
      <div class="dh-row">
        <span class="dh-icon">
          <DeviceGlyph :type="dev.type" :color="dev.adjustable ? 'var(--accent2)' : 'var(--muted)'" :size="17"/>
        </span>
        <div>
          <div class="insp-title">{{ dev.label }}</div>
          <div class="insp-sub">{{ metaLabel }} · {{ dev.adjustable ? '可调设备（策略作用对象）' : '计量设备（只读监测）' }}</div>
        </div>
      </div>
    </div>
    <!-- ===== 1. 实测值 / 设定值 ===== -->
    <CollapseSection title="实测值 / 设定值" tone="blue" :show-more="false">
    <p class="sec-desc" v-if="metaDesc !== '—'">{{ metaDesc }}</p>
    <div class="kv2"><span>所属工序</span><b>{{ info.unitName }}（{{ unitTypeLabel }}）</b></div>
    <!-- 计量项：仅计量设备展示 -->
    <div class="kv2" v-if="!dev.adjustable && dev.measured"><span>计量项</span><b>{{ dev.measured }}</b></div>

    <!-- 计量设备：当前读数 / 计量精度 / 量程 -->
    <div class="chips" v-if="!dev.adjustable">
      <div class="chip2"><span>当前读数</span><b>{{ f(live != null ? live : dev.reading) }}</b><i>{{ dev.unit }}</i></div>
      <div class="chip2"><span>计量精度</span><b>{{ dev.accuracy || '—' }}</b></div>
      <div class="chip2"><span>量程</span><b>{{ dev.range || '—' }}</b></div>
    </div>

    <!-- 可调设备：设定调节（输入框数值即当前设定值/工况值） -->
    <div class="card adj-card" v-if="dev.adjustable && sp">
      <div class="param-row">
        <div class="pr-top"><span>{{ spLabel }}</span><b>{{ f(setpointVal) }} <span class="u">{{ sp.unit || '' }}</span></b></div>
        <input type="number" :min="sp.min" :max="sp.max" :step="sp.step || 1"
               :value="setpointVal" @input="onSetpoint" class="num"
               :title="`当前 ${f(setpointVal)} ${sp.unit || ''}`" />
        <div class="pr-hint">参考范围 {{ f(sp.min) }} – {{ f(sp.max) }} {{ sp.unit || '' }}</div>
      </div>
      <!-- 附加可调项（如鼓风机鼓风湿度） -->
      <div v-for="es in extraSps" :key="es.key" class="param-row extra-row">
        <div class="pr-top"><span>{{ es.label }}</span><b>{{ f(extraVal(es.key)) }} <span class="u">{{ es.unit }}</span></b></div>
        <input type="number" :min="es.min" :max="es.max" :step="es.step || 1"
               :value="extraVal(es.key)" @input="onExtraSetpoint(es.key, $event.target.value)"
               class="num" :title="`当前 ${f(extraVal(es.key))} ${es.unit}`" />
        <div class="pr-hint">参考范围 {{ f(es.min) }} – {{ f(es.max) }} {{ es.unit }}</div>
      </div>
      <div class="note">输入框中的数值即为当前设定值（工况值），仿真计算以此为准；调节后经碳引擎折算为运行电耗 / 间接排放，估算随之更新。</div>
    </div>
    </CollapseSection>

    <!-- ===== 3. 实时监控 ===== -->
    <CollapseSection title="实时监控" tone="teal" :show-more="false">
    <div class="trend-head">
      <span class="live-dot"></span> {{ dev.adjustable ? '设定值轨迹 · 1 Hz' : '实时采样 · 1 Hz' }}
      <span class="sp"></span>
      <span class="mono">{{ history.length }} 点</span>
    </div>
    <TrendChart :data="history" :color="dev.color" :height="150" :grid="true" :unit="dev.unit" />
    <div class="trend-foot">
      <!-- 可调设备不显示「最新」：输入框中的数字即当前设定值，避免与面板重复 -->
      <span v-if="!dev.adjustable">最新 <b :style="{color:dev.color}">{{ f(latest) }} {{ dev.unit }}</b></span>
      <span>均值 <b>{{ f(avg) }} {{ dev.unit }}</b></span>
      <span>峰值 <b>{{ f(peak) }} {{ dev.unit }}</b></span>
    </div>

    <!-- 高炉风口热制度 · TFT 策略提示：实时热状态判定与操作建议（焓平衡真值），随实时监控展示 -->
    <TftStrategyPanel
      v-if="showTftPanel"
      mode="device"
      :params="tftParams"
      :dev-type="dev.type"
      :setpoint="setpointVal"
      :extra-setpoints="extraSetpointsNow"
    />
    <!-- 高炉数值仿真分析入口：全厂高炉 TFT 数值总览与调参推演（原仿真菜单入口迁移至此） -->
    <button v-if="showTftPanel && store.simMode" class="tft-entry-btn" @click="openTftAnalysis">高炉数值仿真分析</button>
    </CollapseSection>

    <!-- ===== 4. 其他内容 ===== -->
    <!-- 附加可调项联动指标（如高炉鼓风含湿）：展示推导公式，透明可审计 -->
    <template v-if="multiIndicators.length">
      <CollapseSection :title="'衍生指标 · ' + (multiIndicators[0] ? multiIndicators[0].label : '')" tone="amber" :show-more="false">
      <div class="couple-box">
        <div v-for="ind in multiIndicators" :key="ind.key" class="multi-ind">
          <div class="couple-top">
            <span class="cb-badge m">机理</span>
            <span class="cb-target">指标：<b>{{ ind.label }}</b></span>
            <span class="cb-val">{{ f(ind.value) }}<i>{{ ind.unit }}</i></span>
          </div>
          <p class="cb-basis"><b>公式：</b>{{ ind.formula }}</p>
          <p class="cb-basis2">当前 风量 {{ f(setpointVal) }} m³/h、{{ ind.label }} {{ f(extraVal(ind.key)) }} {{ ind.unit }}</p>
          <p class="cb-basis2" v-if="ind.basis">{{ ind.basis }}</p>
        </div>
      </div>
      </CollapseSection>
    </template>

    <!-- 减碳影响依据（耦合透明度）：让"为什么调整设备会影响碳排"对用户可见、可审计 -->
    <CollapseSection v-if="coupling" title="减碳影响依据 · 耦合透明度" tone="green" :show-more="false">
    <div class="couple-box">
      <div class="couple-top">
        <span class="cb-badge" :class="sourceClass">{{ sourceLabel }}</span>
        <span class="cb-target">驱动参数：<b>{{ paramLabel(coupling.target) }}</b></span>
        <button class="cb-cal" @click="showWizard = true">用本厂数据校准</button>
      </div>
      <p class="cb-basis"><b>依据：</b>{{ coupling.basis }}</p>
      <div class="cb-rows">
        <div class="cb-row"><span>当前设定</span><b>{{ f(setpointVal) }} <i>{{ sp ? sp.unit : '' }}</i></b></div>
        <div class="cb-row" v-for="(v, k) in derivedNow" :key="k">
          <span>推算 {{ paramLabel(k) }}</span>
          <b>{{ f(v) }} <i v-if="baseParams[k] != null">(基准 {{ f(baseParams[k]) }} → {{ pct(v, baseParams[k]) }})</i></b>
        </div>
        <div class="cb-row"><span>不确定度</span><b>{{ coupling.uncertainty || '—' }}</b></div>
      </div>
      <p class="cb-note data" v-if="coupling.source === 'data'">✓ 已用本厂数据标定（{{ coupling.n }} 个样本，R²（拟合优度）={{ coupling.r2 }}），刷新/重启后自动加载。</p>
    </div>
    </CollapseSection>

    <CollapseSection title="活动数据 → 碳引擎" tone="teal" :show-more="false">
    <div class="feeds">{{ feedsText }}</div>
    <div class="note">碳排放 = 活动数据 × 排放因子；接入 SCADA / EMS 后显示实测值。</div>
    </CollapseSection>

    <CalibrationWizard
      v-if="showWizard && coupling"
      :process-type="info.unitType"
      :device-type="dev.type"
      @close="showWizard = false"
      @applied="showWizard = false"
    />
    <!-- 高炉数值仿真分析弹窗（随入口按钮按需打开，异步分包降低首屏体积） -->
    <TftAnalysisDialog v-if="showTft" @close="showTft = false" />
  </div>
</template>

<script setup>
import { computed, ref, watch, defineAsyncComponent } from 'vue'
import { useSimStore } from '../stores/sim'
import CollapseSection from './CollapseSection.vue'
import TrendChart from './TrendChart.vue'
import DeviceGlyph from './DeviceGlyph.vue'
import TftStrategyPanel from './TftStrategyPanel.vue'
// 校准向导较重且仅在「用本厂数据校准」时按需打开：异步分包，降低首屏体积
const CalibrationWizard = defineAsyncComponent(() => import('./CalibrationWizard.vue'))
// 高炉数值仿真分析弹窗：仅在点击入口时按需加载
const TftAnalysisDialog = defineAsyncComponent(() => import('./TftAnalysisDialog.vue'))
import { getCoupling, deriveProcessOpParams, paramLabel, PROCESS_MAP, DEVICE_MAP } from '../data/flowLibrary'
import { buildRealtimeTftParams } from '../utils/tft'

const store = useSimStore()
const info = computed(() => store.deviceDetail)
const dev = computed(() => (info.value ? info.value.device : null))
const lib = computed(() => (store.deviceLibrary && store.deviceLibrary.library) ? store.deviceLibrary.library : {})
const meta = computed(() => (dev.value ? (lib.value[dev.value.type] || {}) : {}))
const metaLabel = computed(() => meta.value.label || (dev.value ? dev.value.type : ''))
// 说明：优先后端设备库，其次设备自带 desc（可调设备由 _adjDevice 补全），再兜底
const metaDesc = computed(() => meta.value.desc || (dev.value && dev.value.desc) || '—')
// 设定范围/单位：前端 DEVICE_MAP 模板对可调/计量设备均有 setpoint；后端库缺失时仍可用
const sp = computed(() => {
  const t = dev.value && DEVICE_MAP[dev.value.type]
  return (t && t.setpoint) || meta.value.setpoint || null
})
// 喂给碳核算引擎的活动数据说明：优先设备自带，其次由耦合目标推断（可调设备无后端 feeds 字段）
const feedsText = computed(() => {
  if (dev.value && dev.value.feeds) return dev.value.feeds
  if (coupling.value && coupling.value.target) return `驱动 ${paramLabel(coupling.value.target)}（经碳引擎折算运行电耗 / 间接排放）`
  return '—'
})
// 所属工序类型 → 中文标签（避免直接显示英文工序类型键）
const unitTypeLabel = computed(() => (info.value && info.value.unitType
  ? (PROCESS_MAP[info.value.unitType] && PROCESS_MAP[info.value.unitType].label) || info.value.unitType
  : ''))
// 可调设备的设定范围与当前值（来自设备库模板，统一存于 store.deviceSetpoints）
const setpointVal = computed(() => {
  const id = dev.value && dev.value.id
  if (id != null && store.deviceSetpoints[id] != null) return store.deviceSetpoints[id]
  return sp.value ? sp.value.def : 0
})
function onSetpoint(e) { if (dev.value) store.setDeviceSetpoint(dev.value.id, e.target.value) }

// 主设定项中文名（模板 setpoint.label 优先，其次 measures，兜底「设定值」）
const spLabel = computed(() => {
  const t = dev.value && DEVICE_MAP[dev.value.type]
  if (t && t.setpoint && t.setpoint.label) return t.setpoint.label
  if (dev.value && dev.value.measures) return dev.value.measures
  return '设定值'
})
// 附加可调项（如鼓风机鼓风湿度）：模板定义列表
const extraSps = computed(() => {
  const t = dev.value && DEVICE_MAP[dev.value.type]
  return (t && t.extraSetpoints) || []
})
// 附加可调项当前值：优先 store 用户设定，其次模板默认
const extraVal = (key) => {
  const id = dev.value && dev.value.id
  if (id != null && store.deviceExtraSetpoints[id] && store.deviceExtraSetpoints[id][key] != null) {
    return store.deviceExtraSetpoints[id][key]
  }
  const es = extraSps.value.find((x) => x.key === key)
  return es ? es.def : 0
}
function onExtraSetpoint(key, v) { if (dev.value) store.setDeviceExtraSetpoint(dev.value.id, key, v) }

// CEMS 说明性内容移入命令行窗口（避免面板冗余提示）：选中 CEMS 设备时推送一次
watch(info, (v) => {
  if (v && v.device && v.device.type === 'cems') {
    store.toast = 'CEMS（烟气连续排放监测系统）直接测得 CO₂ 排放（点源直接监测法），用于与因子法交叉校验；并非所有烟囱都需安装，主体核算仍以活动数据 × 因子为准。'
  }
}, { immediate: true })

// ---- 耦合透明度 ----
const showWizard = ref(false)
const coupling = computed(() => {
  if (!info.value || !dev.value) return null
  return getCoupling(info.value.unitType, dev.value.type)
})
const baseParams = computed(() => {
  if (!info.value) return {}
  const u = store.model.units.find((x) => x.id === info.value.unitId)
  return u ? (u.params || {}) : {}
})
// TFT 策略提示：仅高炉（blast_furnace）热制度相关可调设备展示（风量/湿度、风温；喷吹系统喷煤量已锁定，不在此列）
const TFT_DEVICES = ['blower', 'hot_blast_stove']
// TFT 实时参数：工序基础参数 + 当前工序全部热制度设备实际设定折算（拖动滑块实时联动 TFT 与建议）
const tftParams = computed(() => {
  if (!info.value) return {}
  const unitId = info.value.unitId
  const sps = {}
  for (const dt of TFT_DEVICES) {
    const did = `${unitId}::${dt}`
    const sp = store.deviceSetpoints[did]
    const es = store.deviceExtraSetpoints[did]
    if (sp != null || (es && Object.keys(es).length)) sps[dt] = { setpoint: sp, extraSetpoints: es || {} }
  }
  return buildRealtimeTftParams('blast_furnace', baseParams.value, sps)
})
const showTftPanel = computed(() => !!info.value && info.value.unitType === 'blast_furnace' && dev.value && TFT_DEVICES.includes(dev.value.type))
// 高炉数值仿真分析：仅仿真模式可用（与 Alt+T 快捷键同一入口逻辑）
const showTft = ref(false)
function openTftAnalysis() {
  if (store.simMode) showTft.value = true
  else store.toast = '高炉数值分析仅限仿真模式使用：请先开启仿真模式'
}
const extraSetpointsNow = computed(() => {
  const o = {}
  if (dev.value && extraSps.value) for (const es of extraSps.value) o[es.key] = extraVal(es.key)
  return o
})
const derivedNow = computed(() => {
  if (!coupling.value || !info.value) return {}
  const ov = deriveProcessOpParams(info.value.unitType, [{ type: dev.value.type, setpoint: setpointVal.value }], baseParams.value)
  return ov || {}
})
// 附加可调项联动指标（如鼓风机鼓风湿度 → 高炉鼓风含湿）：由耦合注册表 multi 配置推导，属性面板展示指标与公式
const multiIndicators = computed(() => {
  const c = coupling.value
  if (!c || !c.multi || !dev.value) return []
  const out = []
  for (const [key, m] of Object.entries(c.multi)) {
    let value = null
    try {
      const ov = m.derive(extraVal(key), setpointVal.value, baseParams.value)
      value = ov && ov[m.target] != null ? ov[m.target] : null
    } catch (e) { value = null }
    out.push({ key, label: paramLabel(m.target), value, formula: m.formula || '', basis: m.basis || '', unit: m.unit || '%' })
  }
  return out
})
const sourceLabel = computed(() => {
  const s = coupling.value && coupling.value.source
  return s === 'mechanism' ? '机理' : s === 'empirical' ? '经验' : s === 'data' ? '数据·已校准' : '未标定'
})
const sourceClass = computed(() => {
  const s = coupling.value && coupling.value.source
  return s === 'mechanism' ? 'm' : s === 'empirical' ? 'e' : s === 'data' ? 'd' : 'u'
})
function pct(v, base) {
  if (base == null || base === 0) return '—'
  const d = (v - base) / base * 100
  return (d >= 0 ? '+' : '') + d.toFixed(1) + '%'
}

const history = computed(() => store.deviceHistoryOf(info.value ? info.value.device.id : ''))
const live = computed(() => (info.value ? store.deviceLiveOf(info.value.device.id) : null))
const latest = computed(() => (history.value.length ? history.value[history.value.length - 1].v : (live.value != null ? live.value : (dev.value ? dev.value.reading : 0))))
const avg = computed(() => {
  const h = history.value; if (!h.length) return live.value != null ? live.value : (dev.value ? dev.value.reading : 0)
  let s = 0; for (const p of h) s += p.v; return s / h.length
})
const peak = computed(() => {
  const h = history.value; if (!h.length) return live.value != null ? live.value : (dev.value ? dev.value.reading : 0)
  let m = 0; for (const p of h) if (p.v > m) m = p.v; return m
})

function f(n) { return n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }
</script>

<style scoped>
/* 模块内部说明：不单独成模块，直接写在对应模块内容区顶部 */
.sec-desc { font-size: 10.5px; line-height: 1.5; color: var(--muted); margin: 0 0 8px 0; padding: 0; }
.dh-row { display: flex; align-items: center; gap: 10px; }
.dh-icon { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: 1px solid var(--border); border-radius: 3px; background: var(--panel-3); }
.insp-head { margin-bottom: 4px; }
.trend-head { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); margin-bottom: 6px; }
.trend-head .sp { flex: 1; }
.live-dot { width: 6px; height: 6px; border-radius: 2px; background: var(--accent); }
.trend-foot { display: flex; gap: 14px; flex-wrap: wrap; font-size: 10px; color: var(--muted); margin-top: 6px; }
.trend-foot b { color: var(--text); font-variant-numeric: tabular-nums; font-weight: 400; }
.feeds { margin-top: 6px; font-size: 11px; line-height: 1.5; color: var(--accent2); background: rgba(95,130,148,.10);
  border: 1px solid rgba(95,130,148,.28); border-radius: 3px; padding: 5px 8px; }
.note .hl { color: var(--accent2); font-weight: 400; }

/* 可调设备设定调节：统一使用全局 .param-row / .pr-top / .num / .pr-hint */
.adj-card { margin-top: 6px; }
.extra-row { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); }

/* 耦合透明度 */
.couple-box { background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px; padding: 6px 9px; margin-top: 6px; }
.couple-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cb-badge { font-size: 10px; font-weight: 400; padding: 2px 7px; border-radius: 3px; color: #fff; letter-spacing: .3px; }
.cb-badge.m { background: #2f7d4f; }      /* 机理：绿（确定物理） */
.cb-badge.e { background: #b5852a; }      /* 经验：琥珀 */
.cb-badge.d { background: #0860A8; }      /* 数据：钢蓝（已标定） */
.cb-badge.u { background: #888; }          /* 未标定 */
.cb-target { font-size: 11px; color: var(--muted); }
.cb-target b { color: var(--text); font-weight: 400; }
.cb-val { margin-left: auto; font-size: 13px; color: var(--accent); font-variant-numeric: tabular-nums; }
.cb-val i { font-size: 10px; color: var(--muted); font-style: normal; margin-left: 2px; }
.multi-ind + .multi-ind { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); }
.cb-basis2 { font-size: 10px; color: var(--muted); line-height: 1.6; margin: 4px 0 0; }
.cb-cal { margin-left: auto; font-size: 10px; padding: 3px 8px; border-radius: 3px; border: 1px solid var(--accent);
  background: transparent; color: var(--accent); cursor: pointer; }
.cb-cal:hover { background: var(--accent); color: #fff; }
.cb-basis { font-size: 11px; line-height: 1.55; color: var(--text); margin: 8px 0 6px; }
.cb-rows { display: flex; flex-direction: column; gap: 5px; }
.cb-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; }
.cb-row > span { color: var(--muted); }
.cb-row > b { font-variant-numeric: tabular-nums; font-weight: 400; }
.cb-row > b i { font-size: 10px; color: var(--muted); font-style: normal; }
.cb-note { font-size: 10px; line-height: 1.6; margin: 8px 0 0; }
.cb-note.data { color: var(--accent2); background: rgba(95,130,148,.10); border: 1px solid rgba(95,130,148,.28);
  border-radius: 3px; padding: 5px 8px; }
/* 高炉数值仿真分析入口按钮（随 TFT 策略面板展示） */
.tft-entry-btn { display: block; width: 100%; margin-top: 8px; padding: 6px 8px; font-size: 11px; text-align: center;
  border-radius: 3px; border: 1px solid var(--accent2); background: transparent; color: var(--accent2); cursor: pointer; }
.tft-entry-btn:hover { background: var(--accent2); color: #fff; }
</style>
