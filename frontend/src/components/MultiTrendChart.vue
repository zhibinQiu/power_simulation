<template>
  <div class="multi-trend">
    <div v-if="series.length" class="legend">
      <span
        v-for="s in series"
        :key="s.id"
        class="lg-item"
        :style="{ '--c': s.color }"
        :title="s.label + (s.unit ? '（' + s.unit + '）' : '')"
      >
        <i class="dot"></i>{{ s.label }}
        <b>{{ fmt(s.last) }}<em v-if="s.unit">{{ s.unit }}</em></b>
      </span>
    </div>
    <canvas ref="cv" class="cv"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue'
import { t } from '../i18n'

const props = defineProps({
  // 多条序列：[{id, label, color, unit?, pts: [{t, v}]}]
  series: { type: Array, default: () => [] },
  height: { type: Number, default: 220 },   // 0 = 自适应父容器高度
  axis: { type: Boolean, default: true },
  // raw = 原始量纲同图；normalized = 各序列 min-max 归一化到 0~100% 对比相对趋势
  mode: { type: String, default: 'normalized' },
})

const cv = ref(null)
let ro = null

const withLast = computed(() =>
  props.series.map((s) => ({
    ...s,
    pts: (s.pts || []).filter((p) => p.v != null),
    last: (s.pts || []).filter((p) => p.v != null).pop()?.v,
  }))
)

function draw() {
  const el = cv.value
  if (!el) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = el.clientWidth || 320
  const h = props.height > 0 ? props.height : (el.clientHeight || 240)
  el.width = w * dpr
  el.height = h * dpr
  const ctx = el.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  const series = withLast.value.filter((s) => s.pts.length >= 1)
  if (!series.length) {
    ctx.fillStyle = '#6B7F92'
    ctx.font = '11px ui-monospace, monospace'
    ctx.fillText(t('暂无数据'), 8, h / 2)
    return
  }

  const padL = props.axis ? 46 : 4
  const padR = props.axis ? 10 : 4
  const padT = 12
  const padB = props.axis ? 22 : 8
  const wInner = w - padL - padR
  const hInner = h - padT - padB

  // 时间轴：全部序列的最小/最大 t
  let tMin = Infinity, tMax = -Infinity
  for (const s of series) {
    if (s.pts[0].t < tMin) tMin = s.pts[0].t
    if (s.pts[s.pts.length - 1].t > tMax) tMax = s.pts[s.pts.length - 1].t
  }
  if (tMin === tMax) { tMax += 1 }
  const x = (t) => padL + 2 + ((t - tMin) / (tMax - tMin)) * (wInner - 4)

  // 值域：归一化模式固定 0~100；原始模式取全体 min/max
  let min, max
  if (props.mode === 'normalized') {
    min = 0; max = 100
  } else {
    min = Infinity; max = -Infinity
    for (const s of series) {
      for (const p of s.pts) {
        if (p.v < min) min = p.v
        if (p.v > max) max = p.v
      }
    }
    if (min === max) { min -= 1; max += 1 }
    const pad = (max - min) * 0.1
    min -= pad; max += pad
  }
  const y = (v) => padT + hInner - ((v - min) / (max - min)) * (hInner - 2)

  // 网格 + y 轴刻度
  ctx.strokeStyle = 'rgba(90,100,115,.25)'
  ctx.lineWidth = 1
  for (let g = 0; g <= 3; g++) {
    const gv = min + (max - min) * (1 - g / 3)
    const gy = y(gv)
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(w - padR, gy); ctx.stroke()
    if (props.axis) {
      ctx.fillStyle = '#8A97A5'
      ctx.font = '10px ui-monospace, monospace'
      ctx.textAlign = 'right'
      ctx.textBaseline = 'middle'
      const label = props.mode === 'normalized' ? Math.round(gv) + '%' : axisFmt(gv)
      ctx.fillText(label, padL - 6, gy)
    }
  }

  // 逐序列绘制（保持序列顺序，先画的在最下层）
  series.forEach((s) => {
    const n = s.pts.length
    let vmin = Infinity, vmax = -Infinity
    if (props.mode === 'normalized') {
      for (const p of s.pts) {
        if (p.v < vmin) vmin = p.v
        if (p.v > vmax) vmax = p.v
      }
      if (vmin === vmax) { vmin -= 1; vmax += 1 }
    }
    const val = (p) => (props.mode === 'normalized' ? ((p.v - vmin) / (vmax - vmin)) * 100 : p.v)

    // 折线
    ctx.beginPath()
    ctx.moveTo(x(s.pts[0].t), y(val(s.pts[0])))
    for (let i = 1; i < n; i++) ctx.lineTo(x(s.pts[i].t), y(val(s.pts[i])))
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1.7
    ctx.lineJoin = 'round'
    ctx.stroke()
    // 末端点
    const lx = x(s.pts[n - 1].t), ly = y(val(s.pts[n - 1]))
    ctx.beginPath(); ctx.arc(lx, ly, 2.8, 0, Math.PI * 2)
    ctx.fillStyle = s.color; ctx.fill()
    ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 1.4; ctx.stroke()
  })

  // x 轴时间标签
  if (props.axis) {
    const span = tMax - tMin
    const withSec = span < 3600
    ctx.fillStyle = '#8A97A5'
    ctx.font = '10px ui-monospace, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    const slots = [tMin, tMin + (tMax - tMin) / 2, tMax]
    for (const t of slots) {
      const s = timeFmt(t, withSec)
      const tw = ctx.measureText(s).width
      let tx = x(t) - tw / 2
      if (tx < padL) tx = padL
      if (tx + tw > w - padR) tx = w - padR - tw
      ctx.fillText(s, tx, h - 5)
    }
    ctx.strokeStyle = 'rgba(90,100,115,.25)'
    ctx.beginPath(); ctx.moveTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke()
  }
}

function axisFmt(v) {
  const a = Math.abs(v)
  if (a >= 1000) return v.toFixed(0)
  if (a >= 100) return v.toFixed(0)
  if (a >= 10) return v.toFixed(1)
  return v.toFixed(2)
}
function fmt(v) {
  if (v == null || isNaN(v)) return '—'
  return axisFmt(v)
}
function timeFmt(t, withSec) {
  const d = new Date(t * 1000)
  const p = (n) => String(n).padStart(2, '0')
  const hm = `${p(d.getHours())}:${p(d.getMinutes())}`
  return withSec
    ? `${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}:${p(d.getSeconds())}`
    : `${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}`
}

onMounted(() => {
  draw()
  if (window.ResizeObserver) {
    ro = new ResizeObserver(() => draw())
    ro.observe(cv.value.parentElement || cv.value)
  }
})
onBeforeUnmount(() => { if (ro) ro.disconnect() })
watch(() => props.series, () => nextTick(draw), { deep: true })
watch(() => props.mode, () => nextTick(draw))
watch(() => props.height, () => draw())
</script>

<style scoped>
.multi-trend { width: 100%; }
.legend {
  display: flex; flex-wrap: wrap; gap: 4px 14px;
  padding: 4px 2px 8px;
  font-size: 11px; color: #8A97A5;
}
.lg-item { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.lg-item .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--c); display: inline-block; }
.lg-item b { color: #E8EDF2; font-weight: 600; }
.lg-item b em { font-style: normal; color: #8A97A5; font-weight: 400; margin-left: 2px; }
.cv { display: block; width: 100%; }
</style>
