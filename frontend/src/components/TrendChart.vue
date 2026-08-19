<template>
  <canvas ref="cv" class="trend" :style="{ height: height + 'px' }"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  data: { type: Array, default: () => [] },   // [{t, v}]
  color: { type: String, default: '#0860A8' },
  height: { type: Number, default: 120 },
  fill: { type: Boolean, default: true },
  grid: { type: Boolean, default: false },
  unit: { type: String, default: '' },
})

const cv = ref(null)
let ro = null

function draw() {
  const el = cv.value
  if (!el) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = el.clientWidth || 300
  const h = props.height
  el.width = w * dpr
  el.height = h * dpr
  const ctx = el.getContext('2d')
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  const pts = props.data || []
  if (!pts.length) {
    ctx.fillStyle = '#6B7F92'
    ctx.font = '11px ui-monospace, monospace'
    ctx.fillText('暂无数据', 8, h / 2)
    return
  }

  let min = Infinity, max = -Infinity
  for (const p of pts) { if (p.v < min) min = p.v; if (p.v > max) max = p.v }
  if (min === max) { min -= 1; max += 1 }
  const pad = (max - min) * 0.12
  min -= pad; max += pad

  const n = pts.length
  const x = (i) => (n === 1 ? w - 2 : (i / (n - 1)) * (w - 4) + 2)
  const y = (v) => h - 6 - ((v - min) / (max - min)) * (h - 14)

  if (props.grid) {
    ctx.strokeStyle = 'rgba(90,100,115,.25)'
    ctx.lineWidth = 1
    for (let g = 0; g <= 3; g++) {
      const gy = 6 + (g / 3) * (h - 14)
      ctx.beginPath(); ctx.moveTo(2, gy); ctx.lineTo(w - 2, gy); ctx.stroke()
    }
  }

  // 面积填充
  if (props.fill) {
    const grad = ctx.createLinearGradient(0, 0, 0, h)
    grad.addColorStop(0, hexA(props.color, 0.32))
    grad.addColorStop(1, hexA(props.color, 0.02))
    ctx.beginPath()
    ctx.moveTo(x(0), y(pts[0].v))
    for (let i = 1; i < n; i++) ctx.lineTo(x(i), y(pts[i].v))
    ctx.lineTo(x(n - 1), h - 6)
    ctx.lineTo(x(0), h - 6)
    ctx.closePath()
    ctx.fillStyle = grad
    ctx.fill()
  }

  // 折线
  ctx.beginPath()
  ctx.moveTo(x(0), y(pts[0].v))
  for (let i = 1; i < n; i++) ctx.lineTo(x(i), y(pts[i].v))
  ctx.strokeStyle = props.color
  ctx.lineWidth = 1.6
  ctx.lineJoin = 'round'
  ctx.stroke()

  // 末端点
  const lx = x(n - 1), ly = y(pts[n - 1].v)
  ctx.beginPath(); ctx.arc(lx, ly, 2.6, 0, Math.PI * 2)
  ctx.fillStyle = props.color; ctx.fill()
  ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 1.4; ctx.stroke()
}

function hexA(hex, a) {
  const c = hex.replace('#', '')
  const r = parseInt(c.substring(0, 2), 16), g = parseInt(c.substring(2, 4), 16), b = parseInt(c.substring(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

onMounted(() => {
  draw()
  if (window.ResizeObserver) {
    ro = new ResizeObserver(() => draw())
    ro.observe(cv.value.parentElement || cv.value)
  }
})
onBeforeUnmount(() => { if (ro) ro.disconnect() })
watch(() => props.data, () => nextTick(draw), { deep: true })
watch(() => props.color, () => draw())
</script>
