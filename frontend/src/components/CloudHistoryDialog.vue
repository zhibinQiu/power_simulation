<template>
  <div class="chd-mask" @click.self="close">
    <div class="chd-panel">
      <div class="chd-head">
        <span class="chd-title">{{ t('云端时序历史（TDengine）') }}</span>
        <button class="x-btn lg" @click="close" :title="t('关闭')">✕</button>
      </div>
      <div class="chd-sub">
        {{ t('设备') }} <b>{{ device.name }}</b>
        <template v-if="device.node"> · {{ t('盒子') }} <b>{{ device.node }}</b></template>
        <template v-if="device.model"> · {{ t('模型') }} <b>{{ device.model }}</b></template>
      </div>

      <!-- 查询参数 -->
      <div class="chd-form">
        <label class="chd-f">
          <span>{{ t('属性 property') }}</span>
          <select v-model="selProp" :disabled="!propOptions.length">
            <option v-for="p in propOptions" :key="p" :value="p">{{ p }}</option>
            <option value="" v-if="!propOptions.length" disabled>{{ t('（无 twins 属性，请手动填写）') }}</option>
          </select>
          <input v-model="selProp" v-if="!propOptions.length" :placeholder="t('如 weight')" />
        </label>
        <label class="chd-f">
          <span>instance</span>
          <input v-model="instance" :placeholder="t('默认与设备同名')" :title="t('MQTT 主题 data/{box}/{device}/{instance}/{property} 第 4 段，默认与设备同名')" />
        </label>
        <label class="chd-f">
          <span>{{ t('时间范围') }}</span>
          <div class="chd-ranges">
            <button v-for="r in ranges" :key="r.v" class="chd-range" :class="{ on: range === r.v }" @click="range = r.v">{{ t(r.label) }}</button>
          </div>
        </label>
        <div class="chd-ops">
          <button class="chd-btn primary" :disabled="loading" @click="load">
            {{ t(loading ? '查询中…' : '查询历史') }}
          </button>
          <span v-if="error" class="chd-err">{{ error }}</span>
        </div>
      </div>

      <!-- 结果 -->
      <div v-if="series.length" class="chd-result">
        <div class="chd-meta">{{ metaText }}</div>
        <svg class="chd-svg" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none">
          <line v-for="i in 5" :key="'g' + i" :x1="P" :x2="W - P" :y1="P + (H - 2 * P) * i / 5" :y2="P + (H - 2 * P) * i / 5" class="chd-grid" />
          <polyline :points="pts" fill="none" class="chd-line" />
        </svg>
        <div class="chd-axis">
          <span>{{ fmtTime(series[0].t) }}</span>
          <span>{{ fmtTime(series[series.length - 1].t) }}</span>
        </div>
        <div class="chd-trend">
          <span>{{ t('最新') }} <b>{{ fmtV(series[series.length - 1].v) }}</b></span>
          <span>{{ t('均值') }} <b>{{ fmtV(avg) }}</b></span>
          <span>{{ t('峰值') }} <b>{{ fmtV(peak) }}</b></span>
        </div>
      </div>
      <div v-else-if="!loading && !error" class="chd-empty">
        {{ t('选择时间范围后点击「查询历史」。需云端已部署时序库（deploy_cloud.sh --tsdb-only）且设备有 data/ 读数持续写入。') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client'
import { t } from '../i18n'

const props = defineProps({ device: { type: Object, required: true } })
const emit = defineEmits(['close'])
function close() { emit('close') }

const W = 640
const H = 180
const P = 8

// ---- 四元组推导：data/{box}/{device}/{instance}/{property} ----
const box = computed(() => (props.device.node || '').trim())
const devName = computed(() => (props.device.name || '').trim())
const instance = ref(devName.value)
// 属性列表：twins 的 propertyName 去重；缺省保留手动输入
const propOptions = computed(() => {
  const s = new Set()
  for (const twin of props.device.twins || []) if (twin && twin.propertyName) s.add(String(twin.propertyName))
  return [...s]
})
const selProp = ref('')
onMounted(() => { if (propOptions.value.length) selProp.value = propOptions.value[0] })

// ---- 时间范围 ----
const ranges = [
  { v: 1, label: '近 1 小时' },
  { v: 6, label: '近 6 小时' },
  { v: 24, label: '近 24 小时' },
  { v: 168, label: '近 7 天' },
]
const range = ref(24)

// ---- 查询 ----
const loading = ref(false)
const error = ref('')
const series = ref([])
const meta = ref(null)
async function load() {
  const prop = selProp.value.trim()
  if (!box.value) { error.value = t('无法确定盒子（设备未挂载到节点）'); return }
  if (!devName.value) { error.value = t('设备名无效'); return }
  const end = Date.now()
  const start = end - range.value * 3600 * 1000
  error.value = ''
  loading.value = true
  try {
    const r = await api.cloudTsdbHistory({
      box: box.value, device: devName.value, instance: instance.value.trim() || devName.value,
      property: prop, start, end, points: 800,
    })
    if (!r || !r.ok) { series.value = []; error.value = (r && r.error) || t('查询失败'); meta.value = null; return }
    series.value = r.series || []
    meta.value = r
  } catch (e) {
    series.value = []
    error.value = e && e.message ? e.message : String(e)
    meta.value = null
  } finally { loading.value = false }
}

// ---- 渲染 ----
const metaText = computed(() => {
  if (!meta.value || !series.value.length) return ''
  const n = series.value.length
  const iv = meta.value.interval || '?'
  const pts = meta.value.points !== undefined ? t('{points} 窗口', { points: meta.value.points }) : ''
  return t('{n} 个采样点（窗口 {iv}{pts}）· 范围 {t0} ~ {t1}', {
    n, iv,
    pts: pts ? ' · ' + pts : '',
    t0: fmtTime(series.value[0].t),
    t1: fmtTime(series.value[series.value.length - 1].t),
  })
})
const pts = computed(() => {
  const s = series.value
  if (!s.length) return ''
  const ts = s.map((p) => p.t), vs = s.map((p) => p.v)
  let t0 = Math.min(...ts), t1 = Math.max(...ts)
  if (t1 <= t0) t1 = t0 + 1
  let v0 = Math.min(...vs), v1 = Math.max(...vs)
  if (v1 - v0 < 1e-9) { v0 -= 1; v1 += 1 }
  const X = (t) => P + (t - t0) / (t1 - t0) * (W - 2 * P)
  const Y = (v) => H - P - (v - v0) / (v1 - v0) * (H - 2 * P)
  return s.map((p, i) => (i ? 'L' : 'M') + X(p.t).toFixed(1) + ',' + Y(p.v).toFixed(1)).join(' ')
})
const avg = computed(() => {
  const s = series.value
  if (!s.length) return 0
  let sum = 0
  for (const p of s) sum += p.v
  return sum / s.length
})
const peak = computed(() => {
  let m = 0
  for (const p of series.value) if (p.v > m) m = p.v
  return m
})
function fmtV(v) { return v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 3 }) }
function fmtTime(t) {
  const d = new Date(Number(t))
  const p = (n, l = 2) => String(n).padStart(l, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.chd-mask {
  position: fixed; inset: 0; z-index: 320; background: rgba(0, 0, 0, .5);
  display: flex; align-items: center; justify-content: center;
}
.chd-panel {
  width: min(720px, 92vw); max-height: 86vh; overflow: auto;
  background: var(--panel-1); border: 1px solid var(--border); border-radius: 6px;
  padding: 14px 16px; box-shadow: 0 12px 40px rgba(0, 0, 0, .45);
}
.chd-head { display: flex; align-items: center; justify-content: space-between; }
.chd-title { font-size: 14px; font-weight: 600; color: var(--text); }
.chd-sub { font-size: 11px; color: var(--muted); margin: 6px 0 10px; }
.chd-sub b { color: var(--text); font-weight: 400; }
.chd-form { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.chd-f { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); }
.chd-f > span { width: 88px; flex: none; }
.chd-f select, .chd-f input {
  flex: 1; background: var(--panel-3); border: 1px solid var(--border); color: var(--text);
  border-radius: 3px; padding: 4px 6px; font-size: 12px;
}
.chd-ranges { display: flex; gap: 6px; }
.chd-range {
  font-size: 11px; padding: 3px 10px; border-radius: 3px; cursor: pointer;
  border: 1px solid var(--border); background: var(--panel-3); color: var(--muted);
}
.chd-range.on { border-color: var(--accent-d); color: var(--accent-d); }
.chd-ops { display: flex; align-items: center; gap: 10px; }
.chd-btn {
  font-size: 12px; padding: 5px 14px; border-radius: 3px;
  border: 1px solid var(--border); background: var(--panel-3); color: var(--muted); cursor: pointer;
}
.chd-btn.primary { border-color: var(--accent-d); color: var(--accent-d); }
.chd-btn.primary:hover { background: var(--accent); color: #fff; }
.chd-err { font-size: 11px; color: var(--danger, #e25c5c); }
.chd-result { margin-top: 4px; }
.chd-meta { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
.chd-svg { width: 100%; height: 150px; display: block; background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px; }
.chd-grid { stroke: rgba(128, 128, 128, .18); stroke-width: 1; }
.chd-line { stroke: var(--accent); stroke-width: 1.6; }
.chd-axis { display: flex; justify-content: space-between; font-size: 10px; color: var(--muted); margin-top: 4px; }
.chd-trend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: var(--muted); margin-top: 6px; }
.chd-trend b { color: var(--text); font-variant-numeric: tabular-nums; font-weight: 400; }
.chd-empty { font-size: 11px; color: var(--muted); padding: 14px 0 6px; line-height: 1.6; }
</style>
