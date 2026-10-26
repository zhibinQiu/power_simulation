<template>
  <canvas ref="cv" class="trend" :class="{ hoverable: hover }" :style="height > 0 ? { height: height + 'px' } : { height: '100%' }"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { t } from '../i18n'

const props = defineProps({
  data: { type: Array, default: () => [] },   // [{t, v}]
  color: { type: String, default: '#0860A8' },
  height: { type: Number, default: 120 },     // 0 = 自适应父容器高度
  fill: { type: Boolean, default: true },
  grid: { type: Boolean, default: false },
  axis: { type: Boolean, default: false },    // 绘制 y 轴刻度 + x 轴时间标签
  unit: { type: String, default: '' },
  hover: { type: Boolean, default: true },    // 鼠标悬停：十字参考线 + 该点 tooltip（时间 + 数值）
})

const cv = ref(null)
let ro = null
let hoverI = -1        // 当前悬停的数据点下标（-1 = 无）
let geom = null        // draw 时记录的布局参数，供 mousemove 反推最近点

function draw() {
  const el = cv.value
  if (!el) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = el.clientWidth || 300
  const h = props.height > 0 ? props.height : (el.clientHeight || 200)
  el.width = w * dpr
  el.height = h * dpr
  const ctx = el.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  const pts = props.data || []
  if (!pts.length) {
    geom = null
    ctx.fillStyle = '#6B7F92'
    ctx.font = '11px ui-monospace, monospace'
    ctx.fillText(t('暂无数据'), 8, h / 2)
    return
  }

  // 坐标轴留白（axis 模式为刻度标签留边）
  const padL = props.axis ? 46 : 2
  const padR = props.axis ? 10 : 2
  const padT = props.axis ? 10 : 6
  const padB = props.axis ? 20 : 6
  const wInner = w - padL - padR
  const hInner = h - padT - padB

  let min = Infinity, max = -Infinity
  for (const p of pts) { if (p.v < min) min = p.v; if (p.v > max) max = p.v }
  if (min === max) { min -= 1; max += 1 }
  const pad = (max - min) * 0.12
  min -= pad; max += pad

  const n = pts.length
  const x = (i) => (n === 1 ? w - 2 : padL + 2 + (i / (n - 1)) * (wInner - 4))
  const y = (v) => padT + hInner - ((v - min) / (max - min)) * (hInner - 2)
  geom = { padL, wInner, n }

  // 预测段起点：数据点带 forecast:true 时，其后为外推预测（画虚线）
  let histLen = n
  for (let i = 0; i < n; i++) { if (pts[i].forecast) { histLen = i; break } }

  // 网格线 + y 轴刻度
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
      ctx.fillText(axisFmt(gv), padL - 6, gy)
      ctx.strokeStyle = 'rgba(90,100,115,.45)'
      ctx.beginPath(); ctx.moveTo(padL - 3, gy); ctx.lineTo(padL, gy); ctx.stroke()
      ctx.strokeStyle = 'rgba(90,100,115,.25)'
    }
  }

  // 面积填充（仅填充历史段）
  if (props.fill && histLen > 0) {
    const grad = ctx.createLinearGradient(0, 0, 0, h)
    grad.addColorStop(0, hexA(props.color, 0.32))
    grad.addColorStop(1, hexA(props.color, 0.02))
    ctx.beginPath()
    ctx.moveTo(x(0), y(pts[0].v))
    for (let i = 1; i < histLen; i++) ctx.lineTo(x(i), y(pts[i].v))
    ctx.lineTo(x(histLen - 1), h - padB)
    ctx.lineTo(x(0), h - padB)
    ctx.closePath()
    ctx.fillStyle = grad
    ctx.fill()
  }

  // 历史段折线（实线）
  if (histLen > 0) {
    ctx.beginPath()
    ctx.moveTo(x(0), y(pts[0].v))
    for (let i = 1; i < histLen; i++) ctx.lineTo(x(i), y(pts[i].v))
    ctx.strokeStyle = props.color
    ctx.lineWidth = 1.6
    ctx.lineJoin = 'round'
    ctx.stroke()
  }

  // 预测段折线（虚线，带轻微透明）
  if (histLen < n) {
    ctx.beginPath()
    ctx.moveTo(x(histLen - 1), y(pts[histLen - 1].v))
    for (let i = histLen; i < n; i++) ctx.lineTo(x(i), y(pts[i].v))
    ctx.setLineDash([4, 3])
    ctx.strokeStyle = hexA(props.color, 0.75)
    ctx.lineWidth = 1.5
    ctx.lineJoin = 'round'
    ctx.stroke()
    ctx.setLineDash([])
  }

  // 末端点（预测末端用空心圆）
  const lx = x(n - 1), ly = y(pts[n - 1].v)
  if (pts[n - 1].forecast) {
    ctx.beginPath(); ctx.arc(lx, ly, 2.6, 0, Math.PI * 2)
    ctx.fillStyle = 'transparent'; ctx.fill()
    ctx.strokeStyle = props.color; ctx.lineWidth = 1.4; ctx.stroke()
  } else {
    ctx.beginPath(); ctx.arc(lx, ly, 2.6, 0, Math.PI * 2)
    ctx.fillStyle = props.color; ctx.fill()
    ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 1.4; ctx.stroke()
  }

  // x 轴时间标签（首 / 中 / 尾，防溢出）
  if (props.axis) {
    const span = pts[n - 1].t - pts[0].t
    const withSec = span < 3600   // 跨度不足 1 小时显示到秒
    ctx.fillStyle = '#8A97A5'
    ctx.font = '10px ui-monospace, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    const idxs = [...new Set([0, Math.floor((n - 1) / 2), n - 1])]
    for (const i of idxs) {
      const s = timeFmt(pts[i].t, withSec)
      const tw = ctx.measureText(s).width
      let tx = x(i) - tw / 2
      if (tx < padL) tx = padL
      if (tx + tw > w - padR) tx = w - padR - tw
      ctx.fillText(s, tx, h - 5)
    }
    // 时间轴基线
    ctx.strokeStyle = 'rgba(90,100,115,.25)'
    ctx.beginPath(); ctx.moveTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke()
  }

  // 悬停：十字参考线 + 该点 tooltip（横坐标 = 时间，纵坐标 = 数值+单位）
  if (props.hover && hoverI >= 0 && hoverI < n) {
    const p = pts[hoverI]
    const hx = x(hoverI), hy = y(p.v)
    ctx.strokeStyle = 'rgba(90,100,115,.5)'
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])
    ctx.beginPath(); ctx.moveTo(hx, padT); ctx.lineTo(hx, h - padB); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(padL, hy); ctx.lineTo(hx, hy); ctx.stroke()
    ctx.setLineDash([])
    ctx.beginPath(); ctx.arc(hx, hy, 3.4, 0, Math.PI * 2)
    ctx.fillStyle = props.color; ctx.fill()
    ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 1.4; ctx.stroke()

    const timeS = timeFmt(p.t, (pts[n - 1].t - pts[0].t) < 3600)
    const valS = axisFmt(p.v) + (props.unit ? ' ' + props.unit : '')
    ctx.font = '10px ui-monospace, monospace'
    const tw = Math.ceil(Math.max(ctx.measureText(timeS).width, ctx.measureText(valS).width)) + 16
    const th = 34
    let bx = hx + 10, by = hy - th - 8
    if (bx + tw > w - padR) bx = hx - tw - 10   // 右侧放不下则翻到点的左侧
    if (bx < padL) bx = padL
    if (by < 2) by = hy + 10                    // 顶部放不下则移到点的下方
    ctx.fillStyle = 'rgba(22,32,44,.88)'
    ctx.beginPath()
    if (ctx.roundRect) ctx.roundRect(bx, by, tw, th, 4); else ctx.rect(bx, by, tw, th)
    ctx.fill()
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
    ctx.fillStyle = '#E8EEF4'
    ctx.fillText(timeS, bx + 8, by + 14)
    ctx.fillStyle = '#9FC3E0'
    ctx.fillText(valS, bx + 8, by + 28)
  }
}

// 鼠标位置 → 最近数据点下标（数据点沿 x 均匀分布，直接按公式反推）
function onMove(e) {
  if (!props.hover || !geom || !cv.value) return
  const rect = cv.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const { padL, wInner, n } = geom
  const i = n === 1 ? 0 : Math.round((mx - padL - 2) / (wInner - 4) * (n - 1))
  const clamped = Math.max(0, Math.min(n - 1, i))
  if (clamped !== hoverI) { hoverI = clamped; draw() }
}
function onLeave() {
  if (hoverI !== -1) { hoverI = -1; draw() }
}

// y 轴刻度：按量级自适应小数位
function axisFmt(v) {
  const a = Math.abs(v)
  if (a >= 1000) return v.toFixed(0)
  if (a >= 100) return v.toFixed(0)
  if (a >= 10) return v.toFixed(1)
  return v.toFixed(2)
}

// x 轴时间标签：MM-DD HH:MM（跨度过小时补到秒）
function timeFmt(t, withSec) {
  const d = new Date(t * 1000)
  const p = (n) => String(n).padStart(2, '0')
  const hm = `${p(d.getHours())}:${p(d.getMinutes())}`
  return withSec
    ? `${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}:${p(d.getSeconds())}`
    : `${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}`
}

function hexA(hex, a) {
  const c = hex.replace('#', '')
  const r = parseInt(c.substring(0, 2), 16), g = parseInt(c.substring(2, 4), 16), b = parseInt(c.substring(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

onMounted(() => {
  draw()
  const el = cv.value
  el.addEventListener('mousemove', onMove)
  el.addEventListener('mouseleave', onLeave)
  if (window.ResizeObserver) {
    ro = new ResizeObserver(() => draw())
    ro.observe(el.parentElement || el)
  }
})
onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  const el = cv.value
  if (el) {
    el.removeEventListener('mousemove', onMove)
    el.removeEventListener('mouseleave', onLeave)
  }
})
watch(() => props.data, () => nextTick(draw), { deep: true })
watch(() => props.color, () => draw())
watch(() => props.height, () => draw())
watch(() => props.axis, () => draw())
</script>

<style scoped>
.trend { display: block; width: 100%; }
.trend.hoverable { cursor: crosshair; }
</style>
