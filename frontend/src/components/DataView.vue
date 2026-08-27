<template>
  <!-- ============ 数据视图：传感器历史数据表格（顶栏「视图 → 数据视图」） ============ -->
  <div class="data-view">
    <!-- 左侧：传感器 sheet 页（垂直排列，点击切换） -->
    <div class="dv-sheets">
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
      <div class="dv-sheet-add" title="添加数据源（规划中）">+</div>
    </div>

    <!-- 右侧：信息条 + 历史数据表格 -->
    <div class="dv-main">
      <!-- 表格上方统计行（关闭/刷新等操作已由顶栏工具栏提供） -->
      <div class="dv-stats">
        <span class="dv-cur-name">
          <span class="dv-dot" :style="{ background: curDev.color || '#0072BD' }"></span>
          <b>{{ curDev.label || curDev.id }}</b>
          <span class="dv-sub">{{ curDev.unitName }} · {{ curDev.unitType }}</span>
          <span class="dv-range" v-if="curDev.range">{{ curDev.range }}</span>
        </span>
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
              <td class="empty" colspan="5">暂无历史数据</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 中间：历史数据（折线图视图） -->
      <div class="dv-chart-wrap" v-else>
        <TrendChart v-if="chartRows.length"
                    :data="chartRows" :color="curDev.color || '#0072BD'"
                    :height="0" :grid="true" :axis="true" />
        <div v-else class="dv-chart-empty">暂无历史数据</div>
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

// 关闭数据视图，返回数字孪生
const close = () => store.toggleDataView()

// 重新拉取设备历史数据（供视图工具栏「刷新数据」按钮调用）
async function refresh() {
  try {
    const hist = await api.getDeviceHistory()
    if (hist && hist.history) store.deviceHistory = hist.history
  } catch (e) { console.warn('刷新监测数据失败：', e) }
}

// 有历史数据的设备（计量/监测传感器）作为 sheet 页签
const sheetDevs = computed(() =>
  (store.allDevices || []).filter((d) => (store.deviceHistory[d.id] || []).length > 0)
)

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

// 当前传感器历史序列（倒序：最新在上，贴近实时监控）
const rows = computed(() => {
  const dev = curDev.value
  if (!dev || !dev.id) return []
  const h = store.deviceHistory[dev.id] || []
  return [...h].reverse()
})

// 折线图序列（正序：时间从左到右）
const chartRows = computed(() => {
  const dev = curDev.value
  if (!dev || !dev.id) return []
  return [...(store.deviceHistory[dev.id] || [])]
})

const curLive = computed(() => (curDev.value.id != null ? store.deviceLiveOf(curDev.value.id) : null))
const liveOf = (d) => (store.deviceLiveOf(d.id) != null ? store.deviceLiveOf(d.id) : d.reading)

const fmt = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2).replace(/\.?0+$/, ''))

const avg = computed(() => {
  const a = rows.value
  if (!a.length) return null
  return a.reduce((s, r) => s + r.v, 0) / a.length
})
const max = computed(() => (rows.value.length ? Math.max(...rows.value.map((r) => r.v)) : null))
const min = computed(() => (rows.value.length ? Math.min(...rows.value.map((r) => r.v)) : null))

// 时间戳（epoch 秒）-> 本地时间字符串
function fmtTime(t) {
  const d = new Date((t || 0) * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// 与上一采样点的差值
const delta = (r, i) => (i < rows.value.length - 1 ? r.v - rows.value[i + 1].v : null)
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
  display: flex; align-items: center; gap: 16px;
  padding: 7px 14px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
  color: var(--muted); font-size: 11px;
}
.dv-stats b { color: var(--text); font-family: var(--mono); margin-left: 2px; }
.dv-cur-name { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dv-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.dv-cur-name b { font-size: 13px; color: var(--text); }
.dv-sub { color: var(--muted); font-size: 11px; }
.dv-range { color: var(--muted); font-size: 11px; padding: 2px 8px; background: var(--panel-3); border: 1px solid var(--border); border-radius: 10px; }
.dv-live2 { display: flex; align-items: baseline; gap: 4px; margin-left: auto; }
.dv-live-v { font-size: 16px; font-weight: 500; color: var(--accent); font-family: var(--mono); }
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
