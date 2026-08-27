<template>
  <!-- ============ 数据视图：传感器历史数据表格（顶栏「视图 → 数据视图」） ============ -->
  <div class="data-view">
    <!-- 左侧：传感器 sheet 页（垂直排列，点击切换） -->
    <div class="dv-sheets">
      <div class="dv-src-tip">{{ source === 'local' ? '本地模拟数据' : '云端时序库（TDengine）' }}</div>
      <div class="dv-sheet" :class="{ active: d.id === curId }"
           v-for="d in sheetDevs" :key="d.id"
           :title="`${d.label || d.id} · ${d.unitName || ''}`" @click="curId = d.id">
        <span class="sh-icon" :style="{ background: d.color || '#0072BD' }"></span>
        <span class="sh-body">
          <span class="sh-top">
            <span class="sh-name">{{ d.label || d.id }}</span>
            <span class="sh-live">{{ fmt(liveOf(d)) }}</span>
          </span>
          <span class="sh-unit">{{ d.unitName || d.unitType || '' }}</span>
        </span>
      </div>
      <div class="dv-sheet-add" v-if="source === 'local'" title="添加数据源（规划中）">+</div>
    </div>

    <!-- 右侧：信息条 + 历史数据表格 -->
    <div class="dv-main">
      <!-- 表格上方统计行（关闭/刷新等操作已由顶栏工具栏提供） -->
      <div class="dv-stats">
        <!-- 数据源切换：本地模拟 / 云端时序 -->
        <div class="dv-source" title="数据来源">
          <button class="dv-src" :class="{ on: source === 'local' }" @click="source = 'local'">本地模拟</button>
          <button class="dv-src" :class="{ on: source === 'cloud' }" @click="enterCloud()">云端时序</button>
        </div>
        <span class="dv-cur-name">
          <span class="dv-dot" :style="{ background: curDev.color || '#0072BD' }"></span>
          <b>{{ curDev.label || curDev.id }}</b>
          <span class="dv-sub">{{ curDev.unitName }} · {{ curDev.unitType }}</span>
          <span class="dv-range" v-if="curDev.range">{{ curDev.range }}</span>
        </span>
        <!-- 云端时序：属性 + 时间范围选择 -->
        <template v-if="source === 'cloud' && curDev.id">
          <label class="dv-src-f">
            <span>属性</span>
            <select :value="cloudSelOf(curDev)" @change="onCloudProp($event)">
              <option v-for="p in cloudPropsOf(curDev)" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
          <div class="dv-ranges">
            <button v-for="r in cloudRanges" :key="r.v"
                    :class="{ on: cloudRange === r.v }" @click="setCloudRange(r.v)">{{ r.label }}</button>
          </div>
        </template>
        <span class="dv-live2">实时 <b class="dv-live-v">{{ fmt(curLive) }}</b> {{ curDev.unit }}</span>
        <span>采样点数 <b>{{ rows.length }}</b></span>
        <span>均值 <b>{{ fmt(avg) }}</b></span>
        <span>峰值 <b>{{ fmt(max) }}</b></span>
        <span>谷值 <b>{{ fmt(min) }}</b></span>
        <!-- 视图切换：列表 / 折线图 -->
        <div class="dv-mode-switch">
          <button class="dv-mode" :class="{ on: viewMode === 'list' }" @click="viewMode = 'list'">列表</button>
          <button class="dv-mode" :class="{ on: viewMode === 'chart' }" @click="viewMode = 'chart'">折线图</button>
        </div>
      </div>

      <!-- 中间：历史数据（列表视图） -->
      <div class="dv-table-wrap" v-if="viewMode === 'list'">
        <table class="dv-table">
          <thead>
            <tr>
              <th class="idx">#</th>
              <th>时间</th>
              <th class="num">读数<em v-if="curDev.unit"> ({{ curDev.unit }})</em></th>
              <th class="num">变化量</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="r.t">
              <td class="idx">{{ i + 1 }}</td>
              <td class="mono">{{ fmtTime(r.t) }}</td>
              <td class="num mono">{{ fmt(r.v) }}</td>
              <td class="num mono" :class="deltaCls(delta(r, i))">{{ deltaTxt(delta(r, i)) }}</td>
              <td><span class="badge" :class="statusCls(r.v)">{{ statusText(r.v) }}</span></td>
            </tr>
            <tr v-if="rows.length === 0">
              <td class="empty" colspan="5">
                <span v-if="cloudBusy">云端历史查询中…</span>
                <span v-else-if="cloudErr">{{ cloudErr }}</span>
                <span v-else-if="source === 'cloud' && !sheetDevs.length">暂无云端时序设备：请确认盒子已上报 data/ 主题、云端已部署 TDengine（deploy_cloud.sh --tsdb-only）</span>
                <span v-else-if="source === 'cloud'">该时间范围内无云端数据</span>
                <span v-else>暂无历史数据</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 中间：历史数据（折线图视图） -->
      <div class="dv-chart-wrap" v-else>
        <TrendChart v-if="chartRows.length"
                    :data="chartRows" :color="curDev.color || '#0072BD'"
                    :height="0" :grid="true" :axis="true" />
        <div v-else class="dv-chart-empty">
          <span v-if="cloudBusy">云端历史查询中…</span>
          <span v-else-if="cloudErr">{{ cloudErr }}</span>
          <span v-else-if="source === 'cloud' && !sheetDevs.length">暂无云端时序设备</span>
          <span v-else-if="source === 'cloud'">该时间范围内无云端数据</span>
          <span v-else>暂无历史数据</span>
        </div>
        <div class="dv-chart-foot" v-if="chartRows.length">
          <span>区间 {{ fmtTime(chartRows[0].t) }} → {{ fmtTime(chartRows[chartRows.length - 1].t) }}</span>
          <span>采样 {{ chartRows.length }} 点</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import TrendChart from './TrendChart.vue'

const store = useSimStore()
const curId = ref(null)
const viewMode = ref('list')   // 'list' 列表 / 'chart' 折线图
const source = ref('local')    // 'local' 本地模拟 / 'cloud' 云端时序库（TDengine）

// ==================== 云端时序库（TDengine） ====================
// 盒子 MQTT data/{box}/{device}/{instance}/{property} → 云端 collector 自动写入
// TDengine → agent /api/history 降采样 → 平台转发 → 本视图拉取
const cloudDevs = ref([])      // 云端设备列表（/box/devices/realtime）
const cloudSel = ref({})       // device name -> 当前选中属性
const cloudRange = ref(24)     // 时间范围（小时）
const cloudHist = ref({})      // device name -> [{ t(秒), v }]
const cloudErr = ref('')
const cloudBusy = ref(false)
const cloudRanges = [
  { v: 1, label: '近1小时' },
  { v: 6, label: '近6小时' },
  { v: 24, label: '近24小时' },
  { v: 168, label: '近7天' },
]

// 云端设备必须挂在盒子（node）且有 twins 属性，才能映射 data/{box}/{device}/{instance}/{property}
const cloudDevicesOf = computed(() =>
  cloudDevs.value
    .filter((d) => d.node && d.name && (d.twins || []).length)
    .map((d) => {
      const u = ((d.twins || [])[0] || {}).unit || ''
      return { ...d, id: d.name, unit: u, unitName: u, unitType: '云端时序', color: '#10A37F' }
    })
)
// 属性清单：云端 DeviceModel 的 twins.propertyName（映射 data/{box}/{device}/{instance}/{property}）
const cloudPropsOf = (d) => {
  if (!d) return []
  return [...new Set((d.twins || [])
    .map((t) => t && t.propertyName)
    .filter((x) => x && String(x).trim()))]
}
const cloudSelOf = (d) => (d && d.name ? (cloudSel.value[d.name] || cloudPropsOf(d)[0] || '') : '')
const cloudHistOf = (d) => (d && d.name ? (cloudHist.value[d.name] || []) : [])

// 进入云端时序模式：拉取云端设备列表，并自动加载当前设备历史
async function enterCloud() {
  source.value = 'cloud'
  if (!cloudDevs.value.length) await loadCloudDevices()
  // 设备列表变化会触发 watch(sheetDevs) 自动选中第一个并加载历史
  if (curDev.value && curDev.value.id) await loadCloudHist(curDev.value)
}

async function loadCloudDevices() {
  cloudBusy.value = true
  cloudErr.value = ''
  try {
    const r = await api.boxDevicesRealtime()
    cloudDevs.value = (r && r.devices) || []
    if (!cloudDevs.value.length) cloudErr.value = '云端未返回设备（cloud-agent 未部署或云端不可达）'
  } catch (e) {
    cloudErr.value = (e && e.message) ? e.message : String(e)
  } finally {
    cloudBusy.value = false
  }
}

// 从云端 TDengine 拉取指定设备/属性/时间范围的历史（agent 降采样）
async function loadCloudHist(d) {
  if (!d || !d.name || !d.node) return
  const prop = (cloudSel.value[d.name] || cloudPropsOf(d)[0] || '').trim()
  if (!prop) {
    cloudHist.value[d.name] = []
    return
  }
  const end = Date.now()
  const start = end - cloudRange.value * 3600 * 1000
  cloudBusy.value = true
  cloudErr.value = ''
  try {
    const r = await api.cloudTsdbHistory({
      box: d.node, device: d.name, instance: d.name, property: prop,
      start, end, points: 600,
    })
    if (!r || r.ok === false) {
      cloudHist.value[d.name] = []
      cloudErr.value = (r && r.error) || '云端查询失败'
    } else {
      // agent 返回毫秒时间戳，统一转 epoch 秒与本视图 fmtTime 对齐
      cloudHist.value[d.name] = (r.series || []).map((p) => ({ t: Number(p.t) / 1000, v: p.v }))
      if (!cloudHist.value[d.name].length) cloudErr.value = ''
    }
  } catch (e) {
    cloudHist.value[d.name] = []
    cloudErr.value = (e && e.message) ? e.message : String(e)
  } finally {
    cloudBusy.value = false
  }
}

function onCloudProp(e) {
  if (!curDev.value || !curDev.value.name) return
  cloudSel.value[curDev.value.name] = e.target.value
  loadCloudHist(curDev.value)
}
function setCloudRange(v) {
  cloudRange.value = v
  if (curDev.value && curDev.value.id) loadCloudHist(curDev.value)
}

// 关闭数据视图，返回数字孪生
const close = () => store.toggleDataView()

// 重新拉取设备历史数据（供视图工具栏「刷新数据」按钮调用）
async function refresh() {
  try {
    if (source.value === 'cloud') {
      await loadCloudDevices()
      if (curDev.value && curDev.value.id) await loadCloudHist(curDev.value)
      return
    }
    const hist = await api.getDeviceHistory()
    if (hist && hist.history) store.deviceHistory = hist.history
  } catch (e) { console.warn('刷新监测数据失败：', e) }
}

// 有历史数据的设备（计量/监测传感器）作为 sheet 页签；云端模式用云端设备
const sheetDevs = computed(() => {
  if (source.value === 'cloud') return cloudDevicesOf.value
  return (store.allDevices || []).filter((d) => (store.deviceHistory[d.id] || []).length > 0)
})

const curDev = computed(() => {
  const devs = sheetDevs.value
  if (!devs.length) return {}
  return devs.find((d) => d.id === curId.value) || devs[0]
})

// 当前选中传感器切换时跟随
watch(sheetDevs, (devs) => {
  if (!curId.value || !devs.some((d) => d.id === curId.value)) {
    curId.value = devs.length ? devs[0].id : null
  }
}, { immediate: true })

// 云端模式切换设备时自动拉取该设备的历史
watch(curDev, (d) => {
  if (source.value === 'cloud' && d && d.id) loadCloudHist(d)
})

// 当前传感器历史序列（倒序：最新在上，贴近实时监控）
const rows = computed(() => {
  const dev = curDev.value
  if (!dev || !dev.id) return []
  const h = source.value === 'cloud' ? cloudHistOf(dev) : (store.deviceHistory[dev.id] || [])
  return [...h].reverse()
})

// 折线图序列（正序：时间从左到右；过滤空值避免断点）
const chartRows = computed(() => {
  const dev = curDev.value
  if (!dev || !dev.id) return []
  const h = source.value === 'cloud' ? cloudHistOf(dev) : (store.deviceHistory[dev.id] || [])
  return [...h].filter((r) => r.v != null)
})

const curLive = computed(() => {
  const dev = curDev.value
  if (!dev || dev.id == null) return null
  if (source.value === 'cloud') {
    const prop = cloudSel.value[dev.name] || cloudPropsOf(dev)[0]
    const tw = prop ? (dev.twins || []).find((x) => x.propertyName === prop) : null
    if (tw && tw.reported != null && !tw.invalid) return tw.reported
    const h = cloudHistOf(dev)
    return h.length ? h[h.length - 1].v : null
  }
  return store.deviceLiveOf(dev.id)
})
const liveOf = (d) => {
  if (source.value === 'cloud') {
    const prop = cloudSel.value[d.name] || cloudPropsOf(d)[0]
    const tw = prop ? (d.twins || []).find((x) => x.propertyName === prop) : null
    if (tw && tw.reported != null && !tw.invalid) return tw.reported
    const h = cloudHistOf(d)
    return h.length ? h[h.length - 1].v : null
  }
  return store.deviceLiveOf(d.id) != null ? store.deviceLiveOf(d.id) : d.reading
}

const fmt = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2).replace(/\.?0+$/, ''))

const avg = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  if (!a.length) return null
  return a.reduce((s, r) => s + r.v, 0) / a.length
})
const max = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  return a.length ? Math.max(...a.map((r) => r.v)) : null
})
const min = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  return a.length ? Math.min(...a.map((r) => r.v)) : null
})

// 时间戳（epoch 秒）-> 本地时间字符串
function fmtTime(t) {
  const d = new Date((t || 0) * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// 与上一采样点的差值
const delta = (r, i) => {
  if (i >= rows.value.length - 1) return null
  const prev = rows.value[i + 1]
  if (r.v == null || prev.v == null) return null
  return r.v - prev.v
}
const deltaTxt = (d) => (d == null ? '—' : `${d >= 0 ? '+' : ''}${fmt(d)}`)
const deltaCls = (d) => (d == null ? '' : (d > 0 ? 'up' : (d < 0 ? 'down' : '')))

// 状态：解析量程字符串（如 "100–1000 m³/h"）判断是否超限
const rangeBounds = computed(() => {
  const s = (curDev.value && curDev.value.range) || ''
  const m = s.match(/(-?[\d.]+)\s*[–-]\s*(-?[\d.]+)/)
  if (!m) return null
  return { min: parseFloat(m[1]), max: parseFloat(m[2]) }
})
const statusText = (v) => {
  if (v == null) return '—'
  const rb = rangeBounds.value
  if (!rb) return '正常'
  if (v < rb.min || v > rb.max) return '超限'
  return '正常'
}
const statusCls = (v) => (statusText(v) === '超限' ? 'warn' : 'ok')

onMounted(() => {
  // 初始为本地模拟数据视图，无需额外动作；云端时序数据由「云端时序」按钮进入
})

defineExpose({ close, refresh })
</script>

<style scoped>
.data-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: row;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
}
/* ---- 右侧主区域（统计行 + 表格） ---- */
.dv-main { display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0; }
/* ---- 表格上方统计行（关闭/刷新等操作已由顶栏工具栏提供） ---- */
.dv-stats {
  display: flex; align-items: center; gap: 12px;
  padding: 7px 14px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
  color: var(--muted); font-size: 11px;
  flex-wrap: wrap;
}
.dv-stats b { color: var(--text); font-family: var(--mono); margin-left: 2px; }
.dv-cur-name { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dv-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.dv-cur-name b { font-size: 13px; color: var(--text); }
.dv-sub { color: var(--muted); font-size: 11px; }
.dv-range { color: var(--muted); font-size: 11px; padding: 2px 8px; background: var(--panel-3); border: 1px solid var(--border); border-radius: 10px; }
.dv-live2 { display: flex; align-items: baseline; gap: 4px; margin-left: auto; }
.dv-live-v { font-size: 16px; font-weight: 500; color: var(--accent); font-family: var(--mono); }
/* ---- 数据源切换（本地模拟 / 云端时序） ---- */
.dv-source { display: flex; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: var(--panel); }
.dv-src { padding: 2px 10px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; }
.dv-src + .dv-src { border-left: 1px solid var(--border); }
.dv-src:hover { color: var(--text); }
.dv-src.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
/* ---- 云端时序：属性 / 时间范围 ---- */
.dv-src-f { display: flex; align-items: center; gap: 5px; flex: 0 0 auto; }
.dv-src-f select {
  padding: 1px 6px; font-size: 11px; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
}
.dv-ranges { display: flex; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: var(--panel); }
.dv-ranges button { padding: 2px 8px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; }
.dv-ranges button + button { border-left: 1px solid var(--border); }
.dv-ranges button:hover { color: var(--text); }
.dv-ranges button.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
/* ---- 列表 / 折线图切换 ---- */
.dv-mode-switch { display: flex; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: var(--panel); }
.dv-mode { padding: 2px 10px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; }
.dv-mode + .dv-mode { border-left: 1px solid var(--border); }
.dv-mode:hover { color: var(--text); }
.dv-mode.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
/* ---- 表格 ---- */
.dv-table-wrap { flex: 1 1 auto; overflow: auto; background: var(--panel); }
/* ---- 折线图 ---- */
.dv-chart-wrap { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; padding: 12px 16px 6px; background: var(--panel); }
.dv-chart-wrap :deep(.trend) { flex: 1 1 auto; min-height: 0; }
.dv-chart-empty { flex: 1; display: grid; place-items: center; color: var(--faint); font-size: 12px; }
.dv-chart-foot { display: flex; align-items: center; gap: 16px; padding: 6px 2px 0; color: var(--muted); font-size: 11px; font-family: var(--mono); }
.dv-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dv-table th, .dv-table td {
  padding: 5px 12px; border-bottom: 1px solid var(--line);
  text-align: left; white-space: nowrap;
}
.dv-table th {
  position: sticky; top: 0; z-index: 2;
  background: var(--panel-3); color: var(--muted);
  font-weight: 500; font-size: 11px;
  border-bottom: 1px solid var(--border);
}
.dv-table th em { font-style: normal; color: var(--faint); }
.dv-table .idx { width: 46px; color: var(--faint); text-align: right; }
.dv-table .num { text-align: right; }
.dv-table .mono { font-family: var(--mono); }
.dv-table tbody tr:hover { background: var(--accent-l); }
.dv-table .up { color: var(--red); }
.dv-table .down { color: var(--green); }
.dv-table .empty { text-align: center; color: var(--faint); padding: 40px 0; }
.badge {
  display: inline-block; padding: 1px 8px; border-radius: 9px;
  font-size: 11px; line-height: 16px;
}
.badge.ok { color: var(--green); background: rgba(46,158,99,.12); }
.badge.warn { color: var(--red); background: rgba(209,75,75,.14); }
/* ---- 左侧 Excel 风格 sheet 页（垂直排列） ---- */
.dv-sheets {
  display: flex; flex-direction: column; gap: 2px;
  width: 168px; flex: 0 0 auto;
  padding: 6px 6px;
  background: var(--bar-d);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.dv-src-tip {
  flex: 0 0 auto;
  padding: 4px 10px 6px;
  color: var(--faint); font-size: 10px;
  text-align: center;
  border-bottom: 1px dashed var(--line);
  margin-bottom: 4px;
}
.dv-sheet {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px;
  min-width: 0;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-left: none;
  border-radius: 0 6px 6px 0;
  cursor: pointer;
  color: var(--muted);
  position: relative;
}
.dv-sheet:hover { background: var(--panel); color: var(--text); }
.dv-sheet.active {
  background: var(--panel);
  color: var(--text);
  box-shadow: inset 3px 0 0 var(--accent);
}
.dv-sheet .sh-icon { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.dv-sheet .sh-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.dv-sheet .sh-top { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.dv-sheet .sh-name { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dv-sheet .sh-live { font-family: var(--mono); font-size: 11px; color: var(--faint); flex: 0 0 auto; }
.dv-sheet.active .sh-live { color: var(--accent); }
.dv-sheet .sh-unit {
  color: var(--faint); font-size: 10px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dv-sheet-add {
  display: flex; align-items: center; justify-content: center;
  height: 28px; flex: 0 0 auto;
  color: var(--faint); font-size: 15px; cursor: pointer;
}
.dv-sheet-add:hover { color: var(--accent); }
</style>
