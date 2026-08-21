<template>
  <Teleport to="body">
    <div class="tad-mask" @mousedown.self="onClose">
      <div class="tad-dialog" ref="dialogEl" :style="dialogStyle" :class="{ dragging }">
        <!-- 标题栏（按住可拖动弹窗） -->
        <div class="tad-titlebar" @mousedown.prevent="onTitleDown">
          <span class="tad-icon">◱</span>
          <span class="tad-title">高炉数值仿真分析</span>
          <span class="tad-spacer"></span>
          <button class="tad-restore" :disabled="!restoreDirty" title="恢复打开弹窗时的高炉参数" @click.stop="onRestore">恢复仿真前</button>
          <button class="tad-close" title="关闭 (Esc)" @click="onClose">
            <svg width="14" height="14" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/></svg>
          </button>
        </div>

        <div class="tad-body">
          <!-- 左栏：四轴曲线 + 参数设定 -->
          <div class="tad-left">
            <!-- 四轴曲线 2×2 网格（点击任一图切换当前操作轴，滑块联动） -->
            <div class="tad-grid">
              <div
                v-for="a in charts" :key="a.key"
                class="tad-cell" :class="{ on: a.key === ax.key }"
                @click="axKey = a.key"
              >
                <div class="cell-head">
                  <span class="cell-name">{{ a.label }}</span>
                  <span class="cell-val mono">{{ fmt(a.curVal) }} {{ a.unit }}</span>
                </div>
                <svg :viewBox="viewBox" preserveAspectRatio="none" @mousemove="onMove($event, a)" @mouseleave="tip = null">
                  <rect :x="pad.l" :y="y(cfg.tftHigh)" :width="W - pad.l - pad.r" :height="Math.max(0, y(cfg.tftLow) - y(cfg.tftHigh))" fill="#3fae6a" opacity="0.10" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="y(cfg.tftLow)" :y2="y(cfg.tftLow)" stroke="#89d185" stroke-dasharray="4 3" opacity="0.5" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="y(cfg.tftHigh)" :y2="y(cfg.tftHigh)" stroke="#89d185" stroke-dasharray="4 3" opacity="0.5" />
                  <g v-for="gv in yTicks" :key="'y' + gv">
                    <line :x1="pad.l" :x2="W - pad.r" :y1="y(gv)" :y2="y(gv)" stroke="#333" />
                    <text :x="pad.l - 6" :y="y(gv) + 3" text-anchor="end">{{ gv }}</text>
                  </g>
                  <g v-for="gx in a.ticks" :key="'x' + gx">
                    <line :x1="xOf(a, gx)" :x2="xOf(a, gx)" :y1="H - pad.b" :y2="H - pad.b + 4" stroke="#454545" />
                    <text :x="xOf(a, gx)" :y="H - pad.b + 14" text-anchor="middle">{{ fmt(gx) }}</text>
                  </g>
                  <line :x1="pad.l" :x2="pad.l" :y1="pad.t" :y2="H - pad.b" stroke="#454545" stroke-width="1" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="H - pad.b" :y2="H - pad.b" stroke="#454545" stroke-width="1" />
                  <polyline v-for="(seg, i) in a.segs" :key="i" :points="seg.pts" fill="none" :stroke="colorOf[seg.code]" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
                  <template v-if="a.curTft != null">
                    <line :x1="xOf(a, a.curVal)" :x2="xOf(a, a.curVal)" :y1="pad.t" :y2="H - pad.b" stroke="#6a6a6a" stroke-dasharray="3 3" opacity="0.6" />
                    <circle :cx="xOf(a, a.curVal)" :cy="y(a.curTft)" r="4.5" fill="#1e1e1e" :stroke="cur.status.color" stroke-width="2.4" />
                  </template>
                </svg>
                <div v-if="tip && tip.key === a.key" class="tad-tip" :style="{ left: tip.px + 'px', top: tip.py + 'px' }">
                  <div class="t1">{{ a.label }} = {{ fmt(tip.pt.x) }} {{ a.unit }}</div>
                  <div class="t2">TFT = <b>{{ tip.pt.tft.toFixed(0) }} ℃</b></div>
                  <div class="t2" v-if="tip.pt.co2 != null">CO₂ = <b>{{ tip.pt.co2.toFixed(0) }} kg/tHM</b></div>
                </div>
              </div>
            </div>

            <!-- 参数设定（滑块 → 联动仿真） -->
            <div class="tad-setter">
              <div class="ts-head">
                <span class="ts-lbl">{{ ax.label }}</span>
                <span class="ts-val mono"><b>{{ fmt(curX) }}</b> {{ ax.unit }}</span>
                <span class="ts-badge" :class="applied ? 'ok' : 'dirty'">
                  <i class="bd-dot"></i>{{ applied ? '已应用' : '待应用' }}
                </span>
              </div>
              <input
                class="ts-range"
                type="range"
                :min="ax.min" :max="ax.max" :step="ax.step || 1"
                :value="curX"
                :disabled="!bfUnit"
                @input="onInput"
                @change="onApply"
              />
              <div class="ts-scale">
                <span class="mono">{{ fmt(ax.min) }}</span>
                <span class="mono">{{ fmt(ax.max) }}</span>
              </div>
            </div>

            <!-- 动态解读 -->
            <div class="tad-note" :class="note.kind">
              <span class="note-icon">{{ noteIcon[note.kind] }}</span>
              <span class="note-text">{{ note.text }}</span>
            </div>
          </div>

          <!-- 右栏：当前工况 + 灵敏度总览 + 策略建议 -->
          <div class="tad-right">
            <div class="tad-sec-title">当前工况</div>
            <div class="tad-cond">
              <div class="cond-main">
                <span class="cond-tft mono">{{ cur.tft.toFixed(0) }}</span>
                <span class="cond-unit">℃</span>
                <span class="cond-st" :style="{ color: cur.status.color }">
                  <i class="st-dot" :style="{ background: cur.status.color }"></i>{{ cur.status.label }}
                </span>
              </div>
              <div class="cond-grid">
                <div class="cg-item"><span class="cg-k">焦比（结果量）</span><b class="mono">{{ fmt(baseParams.coke_rate) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">喷煤比</span><b class="mono">{{ fmt(baseParams.coal_inj) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">热风温度</span><b class="mono">{{ fmt(baseParams.hot_blast_temp) }} ℃</b></div>
                <div class="cg-item"><span class="cg-k">富氧率</span><b class="mono">{{ fmt(baseParams.oxygen_enrich) }} %</b></div>
              </div>
              <!-- CO2 排放：随配料比（焦比/喷煤比）联动同步展示 -->
              <div class="cond-co2">
                <div class="co2-main">
                  <span class="co2-k">CO₂ 排放</span>
                  <span class="co2-val mono">{{ fmt(co2.CO2_emit) }}</span>
                  <span class="co2-unit">kg CO₂/tHM</span>
                  <span class="cond-st" :style="{ color: co2.level.color }">
                    <i class="st-dot" :style="{ background: co2.level.color }"></i>{{ co2.level.label }}
                  </span>
                </div>
                <div class="co2-grid">
                  <div class="cg-item"><span class="cg-k">入炉碳 C_in</span><b class="mono">{{ fmt(co2.C_in) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">铁水溶碳 C_HM</span><b class="mono">{{ fmt(co2.C_HM) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">排放碳 C_emit</span><b class="mono">{{ fmt(co2.C_emit) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">风口 / 非风口</span><b class="mono">{{ fmt(co2.CO2_from_raceway) }} / {{ fmt(co2.CO2_from_other) }}</b></div>
                </div>
                <div class="co2-tip">{{ (co2.level && co2.level.desc) || '碳平衡口径：CO₂ = (入炉碳 − 铁水溶碳) × 44.009/12.011；炉尘碳计入排放。' }}</div>
              </div>
              <div class="cond-tip">焦比是结果量：由风温/富氧/喷煤等操作参数经系统耦合推导，不可直接设定；调节旋钮联动仿真后焦比随之更新，CO₂ 排放同步刷新。</div>
            </div>

            <div class="tad-sec-title">灵敏度总览</div>
            <table class="tad-table">
              <thead>
                <tr><th>操作参数</th><th>当前值</th><th>ΔTFT</th><th>ΔCO₂</th><th>趋势</th></tr>
              </thead>
              <tbody>
                <tr v-for="a in axes" :key="a.key" :class="{ on: a.key === ax.key }" @click="axKey = a.key">
                  <td class="c-name">{{ a.label }}</td>
                  <td class="mono">{{ fmt(baseParams[a.key]) }} {{ a.unit }}</td>
                  <td class="mono">{{ (axisStats[a.key] || {}).spreadText || '—' }}</td>
                  <td class="mono">{{ (axisStats[a.key] || {}).co2SpreadText || '—' }}</td>
                  <td>
                    <span class="trend" :class="(axisStats[a.key] || {}).trendCls">
                      <i class="td-dot"></i>{{ (axisStats[a.key] || {}).trend }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="tad-ax-desc">{{ ax.hint }}</div>

            <div class="tad-sec-title">策略建议</div>
            <div class="tad-advice">
              <ul>
                <li v-for="(ad, i) in advices" :key="i" :class="'lv-' + ad.level">
                  <i class="ad-dot"></i>{{ ad.text }}
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'
import { collectTftContext, DEFAULT_TFT_CONFIG } from '../utils/tft'
import { collectSimContext } from '../utils/co2'

const emit = defineEmits(['close'])
const store = useSimStore()

// ---- 可分析轴配置（key 对齐高炉模板参数，附加节能语义）----
// 可操作自变量（操作员可直接设定的旋钮）；焦比是结果量，由这些参数经系统耦合推导，不作为自变量
const AXIS_META = {
  hot_blast_temp: { label: '热风温度', hint: '风温↑ → 鼓风显热免费顶替焦炭放热，联动降低焦比、创造减碳空间' },
  oxygen_enrich: { label: '富氧率', hint: '富氧↑ → 压缩 N2 稀释、供氧↑，为降焦/提煤腾出 TFT' },
  wind_rate: { label: '风量', hint: '供氧与 N2 同步变化近抵消，是产量通道，不减碳' },
  coal_inj: { label: '喷煤比', hint: '喷煤↑替代焦炭（焦比联动↓）减碳，但热解吸热 + 产 H2O 稀释使 TFT↓' },
  // coke_rate: {label:'焦比', hint: '焦比↑导致TFT温度↑，高炉温度稳定，CO2排放↑'},
  blast_humidity: {label:'鼓风湿度', hint: '湿度是炼铁环节努力减小的输入，湿度↑TFT下降，湿度↓TFT上升' }
}

const cfg = DEFAULT_TFT_CONFIG
// 每个小图的逻辑坐标系（CSS 以 aspect-ratio 290/200 保持同比例渲染，文字不变形）
const W = 290
const H = 200
const pad = { l: 38, r: 8, t: 16, b: 22 }
const viewBox = `0 0 ${W} ${H}`
const colorOf = { low: '#f48771', ok: '#89d185', high: '#e2c08d' }
const noteIcon = { ok: '✓', low: '▲', high: '▲', warn: '⚠' }
const tip = ref(null)

const tpl = PROCESS_MAP.blast_furnace
const bfUnit = computed(() => (store.model.units || []).find((u) => u.type === 'blast_furnace'))
const baseParams = computed(() => bfUnit.value?.params || {})

const axes = computed(() => {
  const tplParams = tpl?.params || []
  return tplParams
    .filter((p) => AXIS_META[p.key])
    .map((p) => ({
      key: p.key,
      label: p.label || AXIS_META[p.key].label,
      unit: p.unit || '',
      min: p.min,
      max: p.max,
      step: p.step || 1,
      def: p.def,
      hint: AXIS_META[p.key].hint,
    }))
})

const axKey = ref('hot_blast_temp')
const ax = computed(() => axes.value.find((a) => a.key === axKey.value) || axes.value[0] || { key: '', label: '', unit: '', min: 0, max: 1, step: 1 })

// 模型当前值（无系统值时用模板默认）
const modelVal = computed(() => {
  const v = Number(baseParams.value[ax.value.key])
  return Number.isFinite(v) ? v : (ax.value.def != null ? ax.value.def : ax.value.min)
})

// 滑块设定值：切换轴时同步模型值；拖动时本地预览，松手后写入模型
const localVal = ref(null)
watch(() => [bfUnit.value?.id, axKey.value], () => { localVal.value = modelVal.value }, { immediate: true })

// 当前工况点（跟随滑块设定值，未松手时预览）
const curX = computed(() => {
  const v = localVal.value
  return Number.isFinite(v) ? v : modelVal.value
})

// 是否已应用：滑块设定值与模型值一致
const applied = computed(() => bfUnit.value != null && Math.abs(Number(modelVal.value) - Number(curX.value)) < 1e-9)

function onInput(e) { localVal.value = Number(e.target.value) }
function onApply() {
  if (!bfUnit.value) return
  store.setUnitParam(bfUnit.value.id, ax.value.key, curX.value)
  localVal.value = curX.value
}

// ---- 恢复到仿真前 ----
// 快照：打开弹窗（组件挂载）时的高炉操作参数，作为「仿真前」基准
const snapshot = ref(null)
watch(
  () => bfUnit.value?.id,
  (id) => {
    if (!id || snapshot.value) return
    const snap = {}
    for (const a of axes.value) {
      const v = Number(baseParams.value[a.key])
      snap[a.key] = Number.isFinite(v) ? v : (a.def != null ? a.def : a.min)
    }
    snapshot.value = snap
  },
  { immediate: true }
)

// 是否偏离仿真前（决定「恢复仿真前」按钮可用性）
const restoreDirty = computed(() => {
  const u = bfUnit.value
  if (!u || !snapshot.value) return false
  for (const a of axes.value) {
    const sv = snapshot.value[a.key]
    const cv = Number(baseParams.value[a.key])
    if (!Number.isFinite(cv)) {
      if (Math.abs(sv - (a.def != null ? a.def : a.min)) > 1e-9) return true
      continue
    }
    if (Math.abs(sv - cv) > 1e-9) return true
  }
  // 滑块存在未应用的修改也算偏离
  if (Math.abs(Number(curX.value) - Number(modelVal.value)) > 1e-9) return true
  return false
})

// 恢复：四个操作参数写回快照值，滑块同步
function onRestore() {
  const u = bfUnit.value
  if (!u || !snapshot.value) return
  for (const a of axes.value) {
    const v = snapshot.value[a.key]
    if (v == null) continue
    if (Math.abs(Number(v) - Number(baseParams.value[a.key])) > 1e-9) store.setUnitParam(u.id, a.key, v)
  }
  if (snapshot.value[ax.value.key] != null) localVal.value = snapshot.value[ax.value.key]
}

// 扫描某轴全范围 → TFT / CO2 序列
function scanAxis(a) {
  const pts = []
  const n = Math.max(2, Math.ceil((a.max - a.min) / a.step))
  for (let i = 0; i <= n; i++) {
    const v = a.min + ((a.max - a.min) * i) / n
    try {
      const ctx = collectSimContext({ ...baseParams.value, [a.key]: v })
      pts.push({ x: v, tft: ctx.tft, co2: ctx.co2 ? ctx.co2.CO2_emit : null })
    } catch (e) {
      pts.push({ x: v, tft: null, co2: null })
    }
  }
  return pts
}

// 每轴全范围扫描序列（缓存，模型参数变化时自动重算）
const seriesMap = computed(() => {
  const m = {}
  for (const a of axes.value) m[a.key] = scanAxis(a).filter((p) => p.tft != null)
  return m
})

// 当前工况上下文（跟随滑块设定值预览）：TFT + CO2 排放同步计算
const cur = computed(() => {
  try {
    return collectSimContext({ ...baseParams.value, [ax.value.key]: curX.value })
  } catch (e) {
    return { tft: 0, status: { code: 'err', label: '异常', color: '#8a8a8a' }, co2: { CO2_emit: 0, CO2_t: 0, C_in: 0, C_HM: 0, C_emit: 0, CO2_from_raceway: 0, CO2_from_other: 0, level: { code: 'err', label: '—', color: '#8a8a8a' } } }
  }
})

// CO2 排放上下文（当前工况）
const co2 = computed(() => cur.value.co2 || {})

// 轴当前显示值：当前轴用滑块预览值，其他轴用模型当前值
function curValOf(a) {
  if (a.key === axKey.value) return curX.value
  const v = Number(baseParams.value[a.key])
  return Number.isFinite(v) ? v : (a.def != null ? a.def : a.min)
}

// 轴当前工况 TFT（该轴当前值下其他参数固定时的响应）
function curTftOf(a) {
  try {
    return collectTftContext({ ...baseParams.value, [a.key]: curValOf(a) }).tft
  } catch (e) {
    return null
  }
}

// y 轴固定绝对基准（合规带 2050~2250 居中），坐标永不缩放——
// 改动任一参数后，四图折线在固定坐标系内整体平移直接可见
const Y_BASE = { ymin: 2000, ymax: 2300 }
const yRange = computed(() => Y_BASE)
const y = (v) => pad.t + ((yRange.value.ymax - v) / (yRange.value.ymax - yRange.value.ymin)) * (H - pad.t - pad.b)

const xOf = (a, v) => {
  const xmin = Math.min(a.min, curValOf(a))
  const xmax = Math.max(a.max, curValOf(a))
  return pad.l + ((v - xmin) / (xmax - xmin)) * (W - pad.l - pad.r)
}
const xTicksOf = (a) => {
  const xmin = Math.min(a.min, curValOf(a))
  const xmax = Math.max(a.max, curValOf(a))
  const out = []
  for (let i = 0; i <= 3; i++) out.push(xmin + ((xmax - xmin) * i) / 3)
  return out
}

const yTicks = computed(() => {
  const { ymin, ymax } = yRange.value
  const step = Math.max(50, Math.round((ymax - ymin) / 5 / 50) * 50)
  const out = []
  for (let v = Math.ceil(ymin / step) * step; v <= ymax; v += step) out.push(v)
  return out
})

// 四轴图表数据（2×2 网格）
const charts = computed(() =>
  axes.value.map((a) => {
    const s = seriesMap.value[a.key] || []
    const segs = []
    let run = []
    let lastCode = null
    for (const p of s) {
      const code = p.tft < cfg.tftLow ? 'low' : p.tft > cfg.tftHigh ? 'high' : 'ok'
      if (code !== lastCode && run.length) { segs.push({ code: lastCode, pts: run }); run = [] }
      lastCode = code
      run.push(p)
    }
    if (run.length) segs.push({ code: lastCode, pts: run })
    return {
      ...a,
      curVal: curValOf(a),
      curTft: curTftOf(a),
      ticks: xTicksOf(a),
      segs: segs.map((g) => ({ code: g.code, pts: g.pts.map((p) => `${xOf(a, p.x).toFixed(1)},${y(p.tft).toFixed(1)}`).join(' ') })),
    }
  })
)

// 每轴统计（全表）
const axisStats = computed(() => {
  const out = {}
  for (const a of axes.value) {
    const pts = seriesMap.value[a.key] || []
    if (!pts.length) { out[a.key] = { spreadText: '—', co2SpreadText: '—', trend: '—', trendCls: '' }; continue }
    const mn = Math.min(...pts.map((p) => p.tft))
    const mx = Math.max(...pts.map((p) => p.tft))
    const d = pts[pts.length - 1].tft - pts[0].tft
    let trend = '近水平', trendCls = 'flat'
    if (d > 3) { trend = '升温'; trendCls = 'up' }
    else if (d < -3) { trend = '降温'; trendCls = 'down' }
    // CO2 全范围跨度（配料比等碳相关参数联动时最直观）
    const c2s = pts.map((p) => p.co2).filter((v) => v != null && Number.isFinite(v))
    const c2mn = c2s.length ? Math.min(...c2s) : null
    const c2mx = c2s.length ? Math.max(...c2s) : null
    out[a.key] = {
      spreadText: `${(mx - mn).toFixed(1)} ℃`,
      co2SpreadText: c2s.length ? `${(c2mx - c2mn).toFixed(0)} kg` : '—',
      trend, trendCls,
    }
  }
  return out
})

// 动态解读（教学点）
const note = computed(() => {
  const st = cur.value.status
  const a = ax.value
  const s = seriesMap.value[a.key] || []
  if (!s.length) return { kind: 'warn', text: '扫描失败，请检查高炉工艺参数是否有效。' }
  const spread = Math.max(...s.map((p) => p.tft)) - Math.min(...s.map((p) => p.tft))
  const t0 = s[0].tft
  const t1 = s[s.length - 1].tft
  let text = ''
  const span = (a.max - a.min) || 1
  const slope = (t1 - t0) / span
  if (a.key === 'wind_rate' && spread < 5) {
    text = '曲线近水平：风量↑同时放大供氧与 N2 稀释，两通道抵消，TFT 对风量不敏感——风量用于调节产量，不宜作为温度/减碳调节手段。'
  } else if (a.key === 'hot_blast_temp') {
    text = `曲线${slope > 0 ? '线性上升' : '下降'}（每 +10℃ 约 TFT ${(slope * 10).toFixed(0)}℃）：热风温度直接注入鼓风显热（分子），是最便宜、零碳排放的升温手段，为联动降焦腾出减碳空间。`
  } else if (a.key === 'oxygen_enrich') {
    text = `曲线${slope > 0 ? '上升' : '下降'}（每 +1% 约 TFT ${(slope * 1).toFixed(0)}℃）：富氧同时压缩 N2 分母并提升供氧，是突破降焦/提煤 TFT 瓶颈的兜底手段，注意富氧耗电的间接排放。`
  } else if (a.key === 'coal_inj') {
    text = `曲线${slope < 0 ? '缓降' : '上升'}（每 +10 kg/tFe 约 TFT ${(slope * 10).toFixed(0)}℃）：喷煤替代焦炭可减碳，但热解吸热与产 H2O 稀释压低 TFT，需风温/富氧补偿。`
  }else if(a.key == 'blast_humidity'){
    text = `曲线${slope < 0 ? '线性上升' : '上升'}（每+1g/Nm³） TFT 约下降 ${(6).toFixed(0)}℃）：鼓风湿度上升会带来高炉内部反应H2的比例上升，可以一定程度降低直接还原度，但是收益抵不过水分解的吸热损失，因此要尽量减少。 `
  }else {
    text = `该轴全范围 TFT 变化 ${spread.toFixed(1)}℃。`
  }
  if (st.code === 'low') text += ' 注意：当前 TFT 偏低，应先升温（风温/富氧）恢复热制度，再实施减碳。'
  if (st.code === 'high') text += ' 注意：当前 TFT 偏高，本身即是减碳信号，可优先降焦比。'
  const c2 = cur.value.co2
  if (c2 && Number.isFinite(c2.CO2_emit)) {
    text += ` 当前工况 CO₂ ${c2.CO2_emit.toFixed(0)} kg/tHM（${c2.CO2_t.toFixed(3)} t/tHM，${c2.level.label}）。`
  }
  return { kind: st.code, text }
})

// 策略建议
const advices = computed(() => {
  const st = cur.value.status
  const c2 = cur.value.co2
  const list = []
  // 碳排现状（配料比 → CO2 同步结论）
  if (c2 && Number.isFinite(c2.CO2_emit)) {
    list.push({ level: c2.level.code === 'high' ? 'w' : 'g', text: `当前 CO₂ 排放 ${c2.CO2_emit.toFixed(0)} kg/tHM（${c2.CO2_t.toFixed(3)} t/tHM，${c2.level.label}）：排放随配料比联动——喷煤↑置换焦炭↓可减碳，TFT 回落到下限即该工况的碳排最优解。` })
  }
  if (st.code === 'low') {
    list.push({ level: 'w', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 偏低：先恢复热制度再谈减碳——首选提升热风温度（免费显热），其次提高富氧率（压缩 N2），可少量降低喷煤比（减少热解吸热）。` })
  } else if (st.code === 'high') {
    list.push({ level: 'w', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 偏高：本身即是减碳信号——提高喷煤比（以氢代碳、置换焦炭），必要时降低风温/富氧让 TFT 回落到合规带。` })
  } else {
    list.push({ level: 'g', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 处于合规区间，可安全实施节能减碳。` })
  }
  list.push({ level: 'g', text: '① 风温打满：热风温度提到上限，鼓风显热免费顶替焦炭放热，焦比联动下降、创造减碳空间（成本最低、零碳排放）。' })
  list.push({ level: 'g', text: '② 用 TFT 空间换碳：提高喷煤比（置换焦炭）或提升风温/富氧联动降低焦比，TFT 随之回落，扣到下限即减碳极限。' })
  list.push({ level: 'g', text: '③ 富氧兜底：喷煤受限时，提高富氧率压缩 N2 分母，释放新一轮提煤/降焦空间。' })
  list.push({ level: 'g', text: '④ 监控闭环：全程盯 TFT 状态，达到下限即停手——TFT 下限就是该工况的碳排最优解。' })
  return list
})

// 悬停取点（每图独立）
function onMove(e, a) {
  const r = e.currentTarget.getBoundingClientRect()
  const px = e.clientX - r.left
  const py = e.clientY - r.top
  const sx = (px / r.width) * W
  const xmin = Math.min(a.min, curValOf(a))
  const xmax = Math.max(a.max, curValOf(a))
  const vx = xmin + ((sx - pad.l) / (W - pad.l - pad.r)) * (xmax - xmin)
  let best = null
  let bd = 1e9
  for (const p of (seriesMap.value[a.key] || [])) {
    const d = Math.abs(p.x - vx)
    if (d < bd) { bd = d; best = p }
  }
  if (best) tip.value = { key: a.key, px, py: py - 4, pt: best }
}

function onClose() { emit('close') }

// ---- 弹窗拖拽移动（按住标题栏拖动）----
const dialogEl = ref(null)
const dragging = ref(false)
const dialogPos = ref(null) // { x, y }：null 表示初始居中
let dragStart = null

const dialogStyle = computed(() => {
  if (!dialogPos.value) return {}
  return { left: dialogPos.value.x + 'px', top: dialogPos.value.y + 'px', transform: 'none', margin: '0' }
})

function clampDrag(x, y) {
  const el = dialogEl.value
  if (!el) return { x, y }
  const vw = window.innerWidth
  const vh = window.innerHeight
  const w = el.offsetWidth
  const h = el.offsetHeight
  x = Math.min(Math.max(x, -w + 90), vw - 90)
  y = Math.min(Math.max(y, 0), vh - 44)
  return { x, y }
}

function onTitleDown(e) {
  if (e.button !== 0) return
  if (e.target.closest('button')) return
  const el = dialogEl.value
  if (!el) return
  const start = dialogPos.value || { x: el.offsetLeft, y: el.offsetTop }
  dragStart = { mx: e.clientX, my: e.clientY, x: start.x, y: start.y }
  dragging.value = true
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragUp)
}

function onDragMove(e) {
  if (!dragStart) return
  const pos = clampDrag(dragStart.x + (e.clientX - dragStart.mx), dragStart.y + (e.clientY - dragStart.my))
  dialogPos.value = pos
}

function onDragUp() {
  dragging.value = false
  dragStart = null
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
})

// Esc 关闭
function onKey(e) { if (e.key === 'Escape') onClose() }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function fmt(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  return Math.abs(v) >= 100 ? v.toFixed(0) : (Number.isInteger(v) ? String(v) : v.toFixed(2))
}
</script>

<style scoped>
/* ============ MATLAB / VSCode 深色混合风格 ============
   色板：主蓝 #007acc / 强调 #3794ff / 激活底 #094771
        编辑区 #1e1e1e / 面板 #252526 / 控件底 #2d2d30 / 边框 #3c3c3c */
.tad-mask {
  position: fixed; inset: 0; z-index: 1200;
  background: rgba(0, 0, 0, 0.4);
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
}
.tad-dialog {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  width: 1260px; max-width: calc(100vw - 60px); height: 800px; max-height: calc(100vh - 80px);
  display: flex; flex-direction: column; overflow: hidden;
  background: #1e1e1e; border: 1px solid #454545; border-radius: 4px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  color: #d4d4d4;
}
.tad-dialog.dragging {
  box-shadow: 0 22px 64px rgba(0, 0, 0, 0.7), 0 0 0 1px #007acc;
  cursor: grabbing;
}

/* ---- 标题栏 ---- */
.tad-titlebar {
  display: flex; align-items: center; gap: 9px; flex: none;
  background: #252526; padding: 0 8px 0 13px; height: 34px;
  border-bottom: 1px solid #3c3c3c;
  cursor: move; user-select: none;
}
.tad-titlebar:active { cursor: grabbing; }
.tad-icon { color: #3794ff; font-size: 14px; }
.tad-title { font-size: 12.5px; font-weight: 600; color: #e6e6e6; letter-spacing: 0.3px; }
.st-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.tad-spacer { flex: 1; }
.tad-restore {
  height: 26px; padding: 0 12px; border: 1px solid #3c3c3c; background: transparent;
  color: #b0b0b0; border-radius: 3px; font-size: 11.5px; cursor: pointer;
  display: inline-flex; align-items: center; letter-spacing: 0.3px;
  transition: color 0.12s, border-color 0.12s, background 0.12s;
}
.tad-restore:hover:not(:disabled) { color: #e6e6e6; border-color: #007acc; background: #094771; }
.tad-restore:disabled { opacity: 0.4; cursor: default; }
.tad-close {
  width: 26px; height: 26px; border: none; background: transparent; color: #a0a0a0;
  border-radius: 3px; cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.tad-close:hover { background: #c42b1c; color: #fff; }

/* ---- 主体：左图表区 + 右信息区 ---- */
.tad-body { flex: 1; min-height: 0; display: flex; }
.tad-left {
  flex: 1.6; min-width: 0; display: flex; flex-direction: column; gap: 9px;
  padding: 10px 12px; overflow-y: auto; background: #1e1e1e;
  border-right: 1px solid #333;
}
.tad-right {
  flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 9px;
  padding: 10px 12px; overflow-y: auto; background: #252526;
}

/* ---- 四轴曲线 2×2 网格 ---- */
.tad-grid {
  flex: none; display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.tad-cell {
  position: relative; background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
  padding: 4px 4px 2px; cursor: pointer;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.tad-cell:hover { border-color: #454545; }
.tad-cell.on { border-color: #007acc; box-shadow: inset 0 0 0 1px #007acc; }
.cell-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 6px;
  padding: 0 4px 3px; font-size: 11px;
}
.cell-name { color: #9d9d9d; font-weight: 600; white-space: nowrap; }
.tad-cell.on .cell-name { color: #5aa9ff; }
.cell-val { color: #c8c8c8; font-size: 11px; }
.tad-cell svg { width: 100%; height: auto; aspect-ratio: 290 / 200; display: block; }
.tad-cell svg text { font-size: 9px; fill: #9d9d9d; }

.tad-tip {
  position: absolute; transform: translate(-50%, -100%); pointer-events: none;
  background: #252526; color: #d4d4d4; padding: 5px 9px; border-radius: 3px;
  border: 1px solid #454545; font-size: 11.5px; white-space: nowrap; z-index: 5;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
.tad-tip .t1 { color: #9d9d9d; }
.tad-tip .t2 { margin-top: 2px; }
.tad-tip b { color: #ffd97a; }

/* ---- 参数设定滑块（自定义细轨道，无原生外圈） ---- */
.tad-setter {
  flex: none; background: #252526; border: 1px solid #3c3c3c; border-radius: 3px;
  padding: 8px 11px 6px; display: flex; flex-direction: column; gap: 1px;
}
.ts-head { display: flex; align-items: center; gap: 9px; }
.ts-lbl { font-size: 12px; font-weight: 600; color: #3794ff; }
.ts-val { font-size: 13px; color: #d4d4d4; }
.ts-val b { font-size: 15px; color: #e6e6e6; }
.ts-badge {
  margin-left: auto; display: inline-flex; align-items: center; gap: 5px;
  font-size: 10.5px; padding: 1px 9px; border-radius: 8px; font-weight: 600;
}
.ts-badge .bd-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.ts-badge.ok { background: #1f3a2a; color: #89d185; }
.ts-badge.ok .bd-dot { background: #89d185; }
.ts-badge.dirty { background: #3a3019; color: #e2c08d; }
.ts-badge.dirty .bd-dot { background: #e2c08d; }

/* 细轨道 + 圆点滑块（无外圈） */
.ts-range {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 4px; margin: 7px 0 4px;
  background: #3c3c3c; border: none; border-radius: 2px;
  outline: none; cursor: pointer;
}
.ts-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 13px; height: 13px; border-radius: 50%;
  background: #007acc; border: 2px solid #d4d4d4;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
  cursor: grab; transition: background 0.12s;
}
.ts-range::-webkit-slider-thumb:hover { background: #3794ff; }
.ts-range::-webkit-slider-thumb:active { cursor: grabbing; }
.ts-range::-moz-range-track { height: 4px; background: #3c3c3c; border: none; border-radius: 2px; }
.ts-range::-moz-range-thumb {
  width: 11px; height: 11px; border-radius: 50%;
  background: #007acc; border: 2px solid #d4d4d4;
  cursor: grab;
}
.ts-range:disabled { opacity: 0.4; cursor: default; }
.ts-range:disabled::-webkit-slider-thumb { cursor: default; }

.ts-scale {
  display: flex; justify-content: space-between;
  font-size: 10px; color: #7a7a7a; padding: 0 1px;
}

/* ---- 动态解读（MATLAB 状态条风格） ---- */
.tad-note {
  flex: none; display: flex; gap: 7px; align-items: flex-start;
  font-size: 11.5px; line-height: 1.5; padding: 7px 10px; border-radius: 3px;
  border: 1px solid #3c3c3c;
}
.tad-note .note-icon { font-size: 12px; font-weight: 700; line-height: 1.4; }
.tad-note.ok { background: #12251a; border-color: #1f4d33; color: #9fdfb5; }
.tad-note.ok .note-icon { color: #89d185; }
.tad-note.low, .tad-note.high { background: #3a2417; border-color: #6a3d1a; color: #f0c89a; }
.tad-note.low .note-icon, .tad-note.high .note-icon { color: #e2c08d; }
.tad-note.warn { background: #3a2f12; border-color: #6a571a; color: #e6d29a; }
.tad-note.warn .note-icon { color: #e2c08d; }

/* ---- 当前工况卡 ---- */
.tad-cond {
  flex: none; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 3px;
  padding: 7px 10px; display: flex; flex-direction: column; gap: 6px;
}
.cond-main { display: flex; align-items: baseline; gap: 6px; }
.cond-tft { font-size: 24px; font-weight: 700; color: #e6e6e6; line-height: 1; }
.cond-unit { font-size: 12px; color: #8a8a8a; }
.cond-st {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 600;
}
.cond-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px;
  border-top: 1px solid #2e2e2e; padding-top: 6px;
}
.cg-item { display: flex; justify-content: space-between; gap: 6px; font-size: 11px; }
.cg-k { color: #8a8a8a; white-space: nowrap; }
.cg-item b { color: #c8c8c8; font-weight: 600; }
.cond-tip {
  font-size: 10.5px; line-height: 1.5; color: #7a7a7a;
  background: #252526; border: 1px solid #2e2e2e; border-radius: 2px; padding: 5px 7px;
}

/* ---- CO2 排放卡（随配料比联动） ---- */
.cond-co2 {
  border-top: 1px solid #2e2e2e; padding-top: 6px;
  display: flex; flex-direction: column; gap: 5px;
}
.co2-main { display: flex; align-items: baseline; gap: 6px; }
.co2-k { font-size: 10.5px; color: #8a8a8a; font-weight: 600; letter-spacing: 0.4px; white-space: nowrap; }
.co2-val { font-size: 20px; font-weight: 700; color: #e6e6e6; line-height: 1; }
.co2-unit { font-size: 11px; color: #8a8a8a; white-space: nowrap; }
.co2-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 3px 10px;
}
.co2-tip {
  font-size: 10px; line-height: 1.45; color: #6f8f7a;
  background: #14231a; border: 1px solid #1f4d33; border-radius: 2px; padding: 4px 7px;
}

/* ---- 右栏标题（MATLAB 工具条小标题风格） ---- */
.tad-sec-title {
  flex: none; font-size: 10.5px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;
  color: #9d9d9d; padding-bottom: 5px; border-bottom: 1px solid #3c3c3c;
}

/* ---- 灵敏度表 ---- */
.tad-table { width: 100%; border-collapse: collapse; flex: none; font-size: 11px; }
.tad-table th {
  text-align: left; padding: 4px 8px; color: #8a8a8a; font-weight: 600;
  border-bottom: 1px solid #3c3c3c; white-space: nowrap;
}
.tad-table td { padding: 5px 8px; border-bottom: 1px solid #2e2e2e; color: #c8c8c8; white-space: nowrap; }
.tad-table tbody tr { cursor: pointer; }
.tad-table tbody tr:hover { background: #2a2d2e; }
.tad-table tr.on td { background: #0f2c47; color: #fff; }
.tad-table tr.on .c-name { color: #5aa9ff; }
.tad-table .c-name { font-weight: 600; color: #3794ff; }
.tad-table .trend { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; }
.tad-table .td-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.tad-table .trend.up { color: #f48771; }
.tad-table .trend.up .td-dot { background: #f48771; }
.tad-table .trend.down { color: #4a90d9; }
.tad-table .trend.down .td-dot { background: #4a90d9; }
.tad-table .trend.flat { color: #8a8a8a; }
.tad-table .trend.flat .td-dot { background: #8a8a8a; }

.tad-ax-desc {
  flex: none; font-size: 11px; line-height: 1.5; color: #9d9d9d;
  padding: 6px 9px; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 3px;
}

/* ---- 策略建议 ---- */
.tad-advice { flex: none; }
.tad-advice ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.tad-advice li {
  position: relative; display: flex; gap: 7px; align-items: flex-start;
  padding: 6px 9px; border-radius: 3px; font-size: 11px; line-height: 1.5;
  border: 1px solid #3c3c3c;
}
.tad-advice .ad-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 5px; flex: none; }
.tad-advice .lv-g { background: #12251a; border-color: #1f4d33; color: #9fdfb5; }
.tad-advice .lv-g .ad-dot { background: #89d185; }
.tad-advice .lv-w { background: #3a2417; border-color: #6a3d1a; color: #f0c89a; }
.tad-advice .lv-w .ad-dot { background: #e2c08d; }

.mono { font-family: Consolas, 'SF Mono', Menlo, 'Courier New', monospace; }
</style>
