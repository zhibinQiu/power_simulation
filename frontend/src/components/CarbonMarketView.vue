<script setup>
// 碳市场实时行情视图：替换中间 3D 数字孪生场景，展示 CEA / CCER 实时行情、走势与预测。
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api } from '../api/client.js'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const quotes = ref(null)
const chart = ref(null)      // 当前展示的图表（cea 蜡烛 / ccer 折线）
const forecast = ref(null)   // 未来 N 日预测序列
const instrument = ref('cea')
const loading = ref(false)
const error = ref('')
const forecastOn = ref(true) // 预测叠加开关
const lastTick = ref(0)      // 用于驱动闪烁动画的 tick
let timer = null

const POLL_MS = 15000
const FORECAST_DAYS = 10

const fmt = (v, digits = 2) => (v == null || Number.isNaN(+v) ? '--' : (+v).toFixed(digits))

// 关闭视图（与 DataView 一致：返回数字孪生场景）
const close = () => store.toggleCarbonMarket()

// ── CEA 行情卡片 ──
const cea = computed(() => quotes.value?.cea || {})
const ceaPrev = computed(() => {
  const pts = quotes.value?.cea_monthly || []
  return pts.length ? pts[pts.length - 1] : null
})
const ceaDaily = computed(() => chart.value?.instrument === 'cea' ? (chart.value?.points || []) : [])

// ── CCER 行情卡片 ──
const ccer = computed(() => quotes.value?.ccer || {})

// 涨跌色使用系统语义色变量（红涨绿跌），深色主题自动适配
const changeColor = (v) => (v == null ? 'var(--muted)' : +v >= 0 ? 'var(--green)' : 'var(--red)')
const changeSign = (v) => (v == null ? '' : +v >= 0 ? '+' : '')

const sourceName = computed(() => chart.value?.source_name || '')
const queriedAt = computed(() => chart.value?.queried_at || quotes.value?.queried_at || '')
const fcDays = computed(() => forecast.value?.ok ? forecast.value.days : 0)

// x 轴日期标签：默认 MM-DD，跨年时显示完整 YYYY-MM-DD
function dateLabel(t, prev) {
  const s = String(t || '').slice(0, 10)
  if (s.length < 10) return s
  return prev && prev.slice(0, 4) !== s.slice(0, 4) ? s : s.slice(5)
}

// ── CEA 蜡烛图（SVG 手绘，历史 + 预测虚线蜡烛 + 置信带） ──
const candleDims = { w: 1000, h: 440 }
function buildCandles(points, fc, w, h) {
  const hist = (points || []).slice(-80)
  const fcs = (fc && fc.ok ? (fc.forecast || []) : []).slice(0, 20)
  const all = [...hist, ...fcs]
  if (!all.length) return null
  const pad = { l: 14, r: 14, t: 22, b: 38 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b
  let min = Infinity, max = -Infinity
  for (const d of all) {
    for (const k of ['low', 'high', 'open', 'close', 'price']) {
      if (d[k] != null) { min = Math.min(min, +d[k]); max = Math.max(max, +d[k]) }
    }
  }
  if (!isFinite(min) || !isFinite(max)) return null
  const span = max - min || 1
  const y = (v) => pad.t + ih - ((+v - min) / span) * ih
  const step = iw / all.length
  const cw = Math.max(2, step * 0.55)
  const bars = all.map((d, i) => {
    const x = pad.l + step * i + step / 2
    const o = d.open ?? d.close, c = d.close ?? d.price, hi = d.high ?? Math.max(o, c), lo = d.low ?? Math.min(o, c)
    const up = c >= o
    return {
      x, up, fc: !!d.forecast,
      wick: `M${x},${y(hi)} L${x},${y(lo)}`,
      body: `M${x - cw / 2},${y(Math.max(o, c))} L${x + cw / 2},${y(Math.max(o, c))} L${x + cw / 2},${y(Math.min(o, c))} L${x - cw / 2},${y(Math.min(o, c))} Z`,
      hi, lo, o, c, t: d.t,
    }
  })
  // 置信带：预测段 high↔price、price↔low 围成的两个半透明多边形
  const fcsX = fcs.map((d, i) => pad.l + step * (hist.length + i) + step / 2)
  const band = fcs.length ? {
    upper: `${fcsX.map((x, i) => `${x},${y(fcs[i].high)}`).join(' ')} ${fcsX.map((x, i) => `${x},${y(fcs[i].price)}`).reverse().join(' ')}`,
    lower: `${fcsX.map((x, i) => `${x},${y(fcs[i].price)}`).join(' ')} ${fcsX.map((x, i) => `${x},${y(fcs[i].low)}`).reverse().join(' ')}`,
  } : null
  // x 轴日期标签（跨年显示完整日期）
  const labels = []
  const stepIdx = Math.max(1, Math.floor(all.length / 9))
  let prev = ''
  for (let i = 0; i < all.length; i += stepIdx) {
    const lb = dateLabel(all[i].t, prev)
    prev = lb.length > 5 ? lb : String(all[i].t).slice(0, 4) + '-' + lb
    labels.push({ x: pad.l + step * i + step / 2, text: lb })
  }
  return { bars, band, labels, yMax: max, yMin: min, gridLines: 5, fcCount: fcs.length }
}

const candle = computed(() => buildCandles(ceaDaily.value, forecastOn.value ? forecast.value : null, candleDims.w, candleDims.h))

// ── CCER 折线图（SVG，历史实线 + 预测虚线 + 置信带） ──
const lineDims = { w: 1000, h: 320 }
function buildLine(points, fc, w, h) {
  const hist = (points || []).slice(-70)
  const fcs = (fc && fc.ok ? (fc.forecast || []) : []).slice(0, 20)
  const all = [...hist, ...fcs]
  if (!hist.length) return null
  const pad = { l: 14, r: 14, t: 20, b: 36 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b
  let min = Infinity, max = -Infinity
  for (const d of all) {
    for (const k of ['price', 'close', 'high', 'low']) {
      if (d[k] != null) { min = Math.min(min, +d[k]); max = Math.max(max, +d[k]) }
    }
  }
  if (!isFinite(min) || !isFinite(max)) return null
  const span = max - min || 1
  const y = (v) => pad.t + ih - ((+v - min) / span) * ih
  const step = iw / Math.max(1, all.length - 1)
  const hPts = []
  const dots = []
  hist.forEach((d, i) => {
    const v = d.price ?? d.close
    if (v == null) return
    const x = pad.l + step * i
    const yy = y(v)
    hPts.push(`${x},${yy}`)
    dots.push({ x, y: yy, v: +v, t: String(d.t) })
  })
  // 预测：从历史末点连虚线
  const last = hPts.length ? hPts[hPts.length - 1] : null
  let fcPts = ''
  let lastPt = null
  fcs.forEach((d, i) => {
    const v = d.price ?? d.close
    if (v == null) return
    const x = pad.l + step * (hist.length + i)
    const yy = y(v)
    fcPts += `${x},${yy} `
    lastPt = { x, y: yy }
  })
  const linePts = last ? `${last} ${fcPts}`.trim() : fcPts.trim()
  const fcsX = fcs.map((d, i) => pad.l + step * (hist.length + i))
  const band = fcs.length ? {
    upper: `${fcsX.map((x, i) => `${x},${y(fcs[i].high)}`).join(' ')} ${fcsX.map((x, i) => `${x},${y(fcs[i].price)}`).reverse().join(' ')}`,
    lower: `${fcsX.map((x, i) => `${x},${y(fcs[i].price)}`).join(' ')} ${fcsX.map((x, i) => `${x},${y(fcs[i].low)}`).reverse().join(' ')}`,
  } : null
  const labels = []
  const stepIdx = Math.max(1, Math.floor(all.length / 9))
  let prev = ''
  for (let i = 0; i < all.length; i += stepIdx) {
    const lb = dateLabel(all[i].t, prev)
    prev = lb.length > 5 ? lb : String(all[i].t).slice(0, 4) + '-' + lb
    labels.push({ x: pad.l + step * i, text: lb })
  }
  return { linePts, dots, band, labels, lastPt, min, max, gridLines: 4 }
}

const ccerPoints = computed(() => chart.value?.instrument === 'ccer' ? (chart.value?.points || []) : [])
const line = computed(() => buildLine(ccerPoints.value, forecastOn.value ? forecast.value : null, lineDims.w, lineDims.h))

// ── 数据加载 ──
async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [q, c, f] = await Promise.all([
      api.carbonMarketQuotes(),
      api.carbonMarketChart(instrument.value, 'daily'),
      api.carbonMarketForecast(instrument.value, FORECAST_DAYS).catch(() => null),
    ])
    quotes.value = q
    chart.value = c
    if (f && f.ok) forecast.value = f
    lastTick.value += 1
  } catch (e) {
    error.value = e?.message || '碳市场数据加载失败'
  } finally {
    loading.value = false
  }
}

async function reloadChart() {
  try {
    const [c, f] = await Promise.all([
      api.carbonMarketChart(instrument.value, 'daily'),
      api.carbonMarketForecast(instrument.value, FORECAST_DAYS).catch(() => null),
    ])
    chart.value = c
    if (f && f.ok) forecast.value = f
  } catch (e) {
    error.value = e?.message || '走势图加载失败'
  }
}

function switchInstrument(v) {
  if (instrument.value === v) return
  instrument.value = v
  reloadChart()
}

function toggleForecast() { forecastOn.value = !forecastOn.value }

function formatTime(s) {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(+d)) return s
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

onMounted(() => {
  loadAll()
  timer = setInterval(loadAll, POLL_MS)
})
onUnmounted(() => clearInterval(timer))
watch(instrument, () => reloadChart())

// 暴露给视图工具栏（RibbonToolbar）：刷新行情 / 切换品种 / 预测开关 / 当前品种与预测状态
defineExpose({ loadAll, switchInstrument, toggleForecast, instrument, forecastOn })
</script>

<template>
  <div class="carbon-market-view" @click.stop>
    <!-- 刷新 / 关闭 / 品种切换 / 预测开关等操作已由顶栏工具栏提供 -->
    <div v-if="error" class="cm-error">{{ error }}</div>

    <!-- 行情卡片 -->
    <div class="cm-cards">
      <div class="cm-card cm-card-cea">
        <div class="cm-card-head">
          <span class="cm-card-name">CEA · 全国碳排放配额</span>
          <span class="cm-card-exch">上海环交所</span>
        </div>
        <div class="cm-card-price">
          <span class="cm-price">{{ fmt(cea.price ?? cea.close) }}</span>
          <span class="cm-unit">元/吨</span>
        </div>
        <div class="cm-card-chg" :style="{ color: changeColor(cea.change_pct) }">
          {{ changeSign(cea.change_pct) }}{{ fmt(cea.change_pct) }}%
          <span v-if="cea.volume != null" class="cm-vol">量 {{ Math.round(cea.volume).toLocaleString() }} 吨</span>
        </div>
        <div class="cm-card-grid">
          <div><span>今开</span><b>{{ fmt(cea.open) }}</b></div>
          <div><span>最高</span><b>{{ fmt(cea.high) }}</b></div>
          <div><span>最低</span><b>{{ fmt(cea.low) }}</b></div>
          <div><span>昨日收</span><b>{{ fmt(ceaPrev?.last_close ?? cea.close) }}</b></div>
        </div>
      </div>

      <div class="cm-card cm-card-ccer">
        <div class="cm-card-head">
          <span class="cm-card-name">CCER · 国家核证自愿减排量</span>
          <span class="cm-card-exch">北京绿交所</span>
        </div>
        <div class="cm-card-price">
          <span class="cm-price">{{ fmt(ccer.price ?? ccer.close) }}</span>
          <span class="cm-unit">元/吨</span>
        </div>
        <div class="cm-card-chg muted">
          全国温室气体自愿减排交易成交均价
          <span v-if="ccer.volume != null" class="cm-vol">量 {{ Math.round(ccer.volume).toLocaleString() }} 吨</span>
        </div>
        <div class="cm-card-grid">
          <div><span>最新价</span><b>{{ fmt(ccer.price ?? ccer.close) }}</b></div>
          <div><span>数据源</span><b class="cm-src">{{ ccer.source ? '官方页面解析' : '--' }}</b></div>
          <div><span>成交量</span><b>{{ ccer.volume != null ? Math.round(ccer.volume).toLocaleString() : '--' }}</b></div>
          <div><span>基准参考</span><b class="cm-src">≈ {{ fmt(cea.price ?? cea.close) }} 元/吨</b></div>
        </div>
      </div>
    </div>

    <!-- 走势图 -->
    <div class="cm-chart-box">
      <div class="cm-chart-head">
        <div class="cm-chart-meta">
          <span class="cm-chart-name">
            {{ chart?.title || '' }}
            <template v-if="forecastOn && fcDays"> + 未来 {{ fcDays }} 日预测</template>
          </span>
        </div>
      </div>

      <div class="cm-legend">
        <span><i class="lg lg-hist" /> 历史数据</span>
        <span v-if="forecastOn && fcDays"><i class="lg lg-fc" /> 预测（{{ forecast?.confidence || '±1.65σ' }}）</span>
      </div>

      <!-- CEA 蜡烛图 -->
      <div class="cm-chart-svg">
        <svg v-if="instrument === 'cea' && candle" :viewBox="`0 0 ${candleDims.w} ${candleDims.h}`" class="cm-svg" preserveAspectRatio="none">
          <template v-for="i in candle.gridLines" :key="'g' + i">
            <line :x1="14" :x2="candleDims.w - 14" :y1="candleDims.h - 38 - i * (candleDims.h - 60) / candle.gridLines" :y2="candleDims.h - 38 - i * (candleDims.h - 60) / candle.gridLines" class="cm-grid" />
            <text x="candleDims.w - 16" :y="candleDims.h - 40 - i * (candleDims.h - 60) / candle.gridLines" class="cm-axis">{{ fmt(candle.yMin + (candle.yMax - candle.yMin) * i / candle.gridLines) }}</text>
          </template>
          <line :x1="14" :x2="candleDims.w - 14" :y1="candleDims.h - 38" :y2="candleDims.h - 38" class="cm-grid" />
          <!-- 预测置信带 -->
          <polygon v-if="candle.band" :points="candle.band.upper" class="cm-band" />
          <polygon v-if="candle.band" :points="candle.band.lower" class="cm-band" />
          <path v-for="(b, i) in candle.bars" :key="'w' + i" :d="b.wick" :class="[b.up ? 'cm-up' : 'cm-down', { 'cm-fc': b.fc }]" stroke-width="1.2" />
          <path v-for="(b, i) in candle.bars" :key="'b' + i" :d="b.body" :class="[b.up ? 'cm-up' : 'cm-down', { 'cm-fc': b.fc }]" />
          <text v-for="(l, i) in candle.labels" :key="'x' + i" :x="l.x" y="candleDims.h - 14" class="cm-axis cm-axis-x" text-anchor="middle">{{ l.text }}</text>
        </svg>
        <div v-else-if="instrument === 'cea'" class="cm-empty">暂无 CEA 日K线数据</div>

        <!-- CCER 折线图 -->
        <svg v-if="instrument === 'ccer' && line" :viewBox="`0 0 ${lineDims.w} ${lineDims.h}`" class="cm-svg" preserveAspectRatio="none">
          <template v-for="i in line.gridLines" :key="'g' + i">
            <line :x1="14" :x2="lineDims.w - 14" :y1="lineDims.h - 36 - i * (lineDims.h - 56) / line.gridLines" :y2="lineDims.h - 36 - i * (lineDims.h - 56) / line.gridLines" class="cm-grid" />
            <text x="lineDims.w - 16" :y="lineDims.h - 38 - i * (lineDims.h - 56) / line.gridLines" class="cm-axis">{{ fmt(line.min + (line.max - line.min) * i / line.gridLines) }}</text>
          </template>
          <!-- 预测置信带 -->
          <polygon v-if="line.band" :points="line.band.upper" class="cm-band" />
          <polygon v-if="line.band" :points="line.band.lower" class="cm-band" />
          <!-- 历史实线 -->
          <polyline v-if="line.linePts" :points="line.linePts" class="cm-line" fill="none" />
          <circle v-for="(d, i) in line.dots" :key="'d' + i" :cx="d.x" :cy="d.y" r="2.2" class="cm-dot">
            <title>{{ d.t }} · {{ fmt(d.v) }} 元/吨</title>
          </circle>
          <text v-for="(l, i) in line.labels" :key="'x' + i" :x="l.x" y="lineDims.h - 12" class="cm-axis cm-axis-x" text-anchor="middle">{{ l.text }}</text>
        </svg>
        <div v-else-if="instrument === 'ccer'" class="cm-empty">暂无 CCER 均价数据</div>
      </div>
    </div>

    <!-- 实时变动提示 -->
    <div class="cm-ticker" :class="{ flash: lastTick % 2 === 1 }">
      <span class="cm-ticker-dot" />
      <span>
        实时行情每 {{ POLL_MS / 1000 }} 秒自动刷新 · 数据源：
        {{ sourceName || '全国碳市场' }}
        <template v-if="queriedAt"> · 更新于 {{ formatTime(queriedAt) }}</template>
        <span v-if="quotes?.simulated" class="cm-badge cm-badge-sim">模拟行情</span>
        <span v-else class="cm-badge">实时数据</span>
        <a v-if="chart?.source_page" :href="chart.source_page" target="_blank" rel="noopener">查看官方页面 ↗</a>
      </span>
    </div>
  </div>
</template>

<style scoped>
/* ===== VS Code / MATLAB 工业风：扁平、克制、统一使用系统 CSS 变量 ===== */
.carbon-market-view {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px 14px;
  overflow: auto;
  color: var(--text);
  background: var(--bg);
  font-family: var(--ui);
}

/* 徽章：模式标签（与 .mode-tag 同体系） */
.cm-badge {
  font-size: 10px; padding: 1px 8px; border-radius: 3px;
  background: var(--accent-l); color: var(--accent-d);
  border: 1px solid var(--accent);
  white-space: nowrap;
}
.cm-badge-sim {
  background: rgba(201, 154, 46, 0.12); color: var(--yellow);
  border-color: rgba(201, 154, 46, 0.4);
}

.cm-error {
  padding: 6px 10px; border-radius: 4px; font-size: 12px; color: var(--red);
  background: rgba(209, 75, 75, 0.08); border: 1px solid rgba(209, 75, 75, 0.3);
}

/* —— 行情卡片：扁平面板 + 顶部 2px 主题色指示条（VS Code tab 顶部指示条同语汇） —— */
.cm-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 10px; }
.cm-card {
  position: relative;
  border-radius: 4px; padding: 12px 14px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.cm-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--accent);
}
.cm-card-ccer::before { background: var(--accent2); }
.cm-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.cm-card-name { font-size: 12px; font-weight: 600; }
.cm-card-exch {
  font-size: 10px; color: var(--muted);
  background: var(--panel-2); border: 1px solid var(--border);
  padding: 1px 8px; border-radius: 3px;
}
.cm-card-price { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.cm-price {
  font-size: 28px; font-weight: 600;
  font-family: var(--mono); font-variant-numeric: tabular-nums;
}
.cm-unit { font-size: 11px; color: var(--muted); }
.cm-card-chg {
  font-size: 12px; font-weight: 500; margin-bottom: 10px;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  font-family: var(--mono); font-variant-numeric: tabular-nums;
}
.cm-card-chg.muted { color: var(--muted); font-weight: 400; font-family: var(--ui); }
.cm-vol { font-size: 10px; color: var(--muted); font-weight: 400; font-family: var(--ui); }
.cm-card-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
  border-top: 1px solid var(--line); padding-top: 10px;
}
.cm-card-grid div { display: flex; flex-direction: column; gap: 2px; }
.cm-card-grid span { font-size: 10px; color: var(--muted); letter-spacing: .3px; }
.cm-card-grid b {
  font-size: 12.5px; font-weight: 500;
  font-family: var(--mono); font-variant-numeric: tabular-nums;
}
.cm-src { font-weight: 500 !important; color: var(--accent); }

/* —— 走势图面板 —— */
.cm-chart-box {
  flex: 1; min-height: 260px;
  border-radius: 4px; padding: 10px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 6px;
  overflow: hidden;
}
.cm-chart-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cm-chart-meta { display: flex; align-items: center; gap: 10px; }
.cm-chart-name { font-size: 11px; color: var(--muted); }

/* 图例 */
.cm-legend { display: flex; gap: 16px; font-size: 10px; color: var(--muted); align-items: center; }
.cm-legend .lg { display: inline-block; width: 14px; height: 3px; vertical-align: middle; margin-right: 4px; border-radius: 2px; }
.lg-hist { background: var(--accent); }
.lg-fc { background: var(--yellow); height: 2px; }

/* SVG 图表：外层容器撑满剩余空间，SVG 绝对定位填满容器，保证底部坐标轴始终在可视区内 */
.cm-chart-svg {
  flex: 1 1 auto;
  position: relative;
  min-height: 0;
  overflow: hidden;
}
.cm-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}
.cm-grid { stroke: var(--line); stroke-width: 1; opacity: .6; }
.cm-axis { font-size: 10px; fill: var(--muted); font-family: var(--mono); }
.cm-axis-x { fill: var(--muted); font-weight: 500; }
.cm-line { stroke: var(--accent); stroke-width: 1.8; }
.cm-dot { fill: var(--accent); }
.cm-up { stroke: var(--green); fill: var(--green); }
.cm-down { stroke: var(--red); fill: var(--red); }
.cm-fc { stroke: var(--yellow) !important; fill: rgba(201, 154, 46, 0.18) !important; stroke-dasharray: 4 3; }
.cm-band { fill: var(--yellow); opacity: .09; pointer-events: none; }
.cm-empty {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  color: var(--muted); font-size: 12px;
}

/* —— 实时刷新提示条 —— */
.cm-ticker {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; color: var(--muted);
  padding: 6px 10px; border-radius: 4px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  transition: background 0.4s;
}
.cm-ticker.flash { background: var(--accent-l); }
.cm-ticker a { color: var(--accent); text-decoration: none; }
.cm-ticker a:hover { text-decoration: underline; }
.cm-ticker-dot {
  width: 7px; height: 7px; border-radius: 50%; flex: none;
  background: var(--green); box-shadow: 0 0 0 0 rgba(46, 158, 99, 0.6);
  animation: cmPulse 2s infinite;
}
@keyframes cmPulse {
  0% { box-shadow: 0 0 0 0 rgba(46, 158, 99, 0.5); }
  70% { box-shadow: 0 0 0 8px rgba(46, 158, 99, 0); }
  100% { box-shadow: 0 0 0 0 rgba(46, 158, 99, 0); }
}
</style>
