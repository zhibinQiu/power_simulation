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
      <!-- 顶部：当前传感器信息条 -->
      <div class="dv-toolbar">
        <div class="dv-cur">
          <span class="dv-dot" :style="{ background: curDev.color || '#0072BD' }"></span>
          <b>{{ curDev.label || curDev.id }}</b>
          <span class="dv-sub">{{ curDev.unitName }} · {{ curDev.unitType }}</span>
          <span class="dv-range" v-if="curDev.range">{{ curDev.range }}</span>
        </div>
        <div class="dv-live">
          <span class="dv-live-lb">实时</span>
          <b class="dv-live-v">{{ fmt(curLive) }}</b>
          <span class="dv-unit">{{ curDev.unit }}</span>
        </div>
        <div class="dv-stats">
          <span>采样点数 <b>{{ rows.length }}</b></span>
          <span>均值 <b>{{ fmt(avg) }}</b></span>
          <span>峰值 <b>{{ fmt(max) }}</b></span>
          <span>谷值 <b>{{ fmt(min) }}</b></span>
        </div>
        <!-- 右上角关闭按钮：退出数据视图，返回数字孪生 -->
        <button class="dv-close" title="关闭数据视图，返回数字孪生" @click="close">✕</button>
      </div>

      <!-- 中间：历史数据表格 -->
      <div class="dv-table-wrap">
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
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const curId = ref(null)

// 关闭数据视图，返回数字孪生
const close = () => store.toggleDataView()

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
</script>

<style scoped>
.data-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: row;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
}
/* ---- 右侧主区域（信息条 + 表格） ---- */
.dv-main { display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0; }
/* ---- 顶部信息条 ---- */
.dv-toolbar {
  display: flex; align-items: center; gap: 18px;
  padding: 8px 14px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
}
.dv-cur { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dv-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.dv-cur b { font-size: 13px; }
.dv-sub { color: var(--muted); font-size: 11px; }
.dv-range { color: var(--muted); font-size: 11px; padding: 2px 8px; background: var(--panel-3); border: 1px solid var(--border); border-radius: 10px; }
.dv-live { display: flex; align-items: baseline; gap: 6px; margin-left: auto; }
.dv-live-lb { color: var(--muted); font-size: 11px; }
.dv-live-v { font-size: 20px; font-weight: 500; color: var(--accent); font-family: var(--mono); }
.dv-unit { color: var(--muted); font-size: 11px; }
.dv-stats { display: flex; gap: 14px; color: var(--muted); font-size: 11px; }
.dv-stats b { color: var(--text); font-family: var(--mono); margin-left: 2px; }
/* ---- 右上角关闭按钮 ---- */
.dv-close {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; margin-left: 4px;
  border: 1px solid var(--border); border-radius: 4px;
  background: transparent; color: var(--muted);
  font-size: 12px; cursor: pointer; flex: 0 0 auto;
}
.dv-close:hover { color: var(--red); border-color: var(--red); background: rgba(209, 75, 75, .1); }
/* ---- 表格 ---- */
.dv-table-wrap { flex: 1 1 auto; overflow: auto; background: var(--panel); }
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
