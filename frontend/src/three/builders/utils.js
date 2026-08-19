// 工艺模型共享工具模块：颜色、材质、纹理、标签绘制
import * as THREE from 'three'

/** 赛博朋克工业科技蓝调色板 */
export const PAL = {
  terrain: 0x0b1020,
  platform: 0x1a2035,
  road: 0x162038,
  lane: 0x00d4ff,
  grass: 0x0d1830,
  wall: 0x1e2d4a,
  roof: 0x253550,
  steel: 0x3a5080,
  glass: 0x1a8aa8,
  accent: 0x00b4d8,
  accent2: 0xd040f0,
  neonCyan: 0x00e5ff,
  neonBlue: 0x0088ff,
  neonPurple: 0x8844ff,
  base: 0x1e3050,
  stack: 0x253550,
  stackBand: 0x00b4d8,
}

export const SCALE = 1

/** 标准材质工厂 */
export function mat(color, o = {}) {
  return new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.48, metalness: 0.42 }, o))
}

/** 快速创建 BoxGeometry Mesh */
export function boxMesh(w, h, d, material) {
  return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material)
}

/** Canvas 纹理生成器 */
export function _makeCanvasTex(w, h, draw, repeat = null) {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')
  draw(ctx, w, h)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.anisotropy = 8
  if (repeat) t.repeat.set(repeat[0] || 1, repeat[1] || 1)
  return t
}

/* ========== 纹理生成 ========== */

let _grassTexCache = null
export function grassTex() {
  if (_grassTexCache) return _grassTexCache
  const SZ = 2048
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    ctx.fillStyle = '#5c6e40'; ctx.fillRect(0, 0, w, h)
    const img = ctx.getImageData(0, 0, w, h)
    const d = img.data
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = (y * w + x) * 4
        const rn = Math.random()
        let rv, gv, bv
        if (rn < 0.28) { rv = 58 + Math.random() * 14; gv = 102 + Math.random() * 18; bv = 38 + Math.random() * 10 }
        else if (rn < 0.52) { rv = 74 + Math.random() * 16; gv = 126 + Math.random() * 20; bv = 48 + Math.random() * 12 }
        else if (rn < 0.70) { rv = 96 + Math.random() * 18; gv = 148 + Math.random() * 22; bv = 56 + Math.random() * 14 }
        else if (rn < 0.83) { rv = 120 + Math.random() * 20; gv = 148 + Math.random() * 20; bv = 62 + Math.random() * 16 }
        else if (rn < 0.92) { rv = 155 + Math.random() * 25; gv = 142 + Math.random() * 20; bv = 72 + Math.random() * 18 }
        else { rv = 150 + Math.random() * 30; gv = 132 + Math.random() * 28; bv = 82 + Math.random() * 22 }
        d[idx] = rv; d[idx + 1] = gv; d[idx + 2] = bv; d[idx + 3] = 255
      }
    }
    ctx.putImageData(img, 0, 0)
    for (let i = 0; i < 60000; i++) {
      const cx = Math.floor(Math.random() * w), cy = Math.floor(Math.random() * h)
      const bladeH = 2 + Math.floor(Math.random() * 12)
      const alpha = 0.06 + Math.random() * 0.14
      const r = 100 + Math.random() * 50, g = 130 + Math.random() * 50, bB = 40 + Math.random() * 20
      ctx.strokeStyle = Math.random() < 0.5
        ? `rgba(${Math.floor(r * 0.55)},${Math.floor(g * 0.55)},${Math.floor(bB * 0.55)},${alpha})`
        : `rgba(${r},${g},${bB},${alpha})`
      ctx.lineWidth = 0.6 + Math.random() * 1.0
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + (Math.random() - 0.5) * 2.5, cy - bladeH); ctx.stroke()
    }
    for (let i = 0; i < 900; i++) {
      const fx = Math.random() * w, fy = Math.random() * h
      ctx.fillStyle = Math.random() < 0.5 ? 'rgba(248,248,225,0.15)' : 'rgba(255,245,160,0.15)'
      ctx.beginPath(); ctx.arc(fx, fy, 0.7 + Math.random() * 0.8, 0, Math.PI * 2); ctx.fill()
    }
  }, [24, 24])
  _grassTexCache = t
  return t
}

let _steelTexCache = null
export function steelTex() {
  if (_steelTexCache) return _steelTexCache
  const t = _makeCanvasTex(512, 512, (ctx, w, h) => {
    ctx.fillStyle = '#6b7680'; ctx.fillRect(0, 0, w, h)
    for (let i = 0; i < 14; i++) {
      const x = Math.random() * w, y = Math.random() * h, r = 6 + Math.random() * 22
      const g = ctx.createRadialGradient(x, y, 0, x, y, r)
      g.addColorStop(0, 'rgba(150,90,60,0.25)'); g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 16
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _steelTexCache = t
  return t
}

let _tankShellTexCache = null
export function tankShellTex() {
  if (_tankShellTexCache) return _tankShellTexCache
  const t = _makeCanvasTex(1024, 512, (ctx, w, h) => {
    ctx.fillStyle = '#c9cfd4'; ctx.fillRect(0, 0, w, h)
    for (let y = 0; y < h; y += 40) {
      ctx.fillStyle = 'rgba(60,70,80,0.40)'; ctx.fillRect(0, y, w, 3)
      ctx.fillStyle = 'rgba(255,255,255,0.20)'; ctx.fillRect(0, y + 3, w, 1)
    }
    const gv = ctx.createLinearGradient(0, 0, w, 0)
    gv.addColorStop(0, 'rgba(0,0,0,0.30)'); gv.addColorStop(0.4, 'rgba(0,0,0,0)')
    gv.addColorStop(0.6, 'rgba(0,0,0,0)'); gv.addColorStop(1, 'rgba(0,0,0,0.30)')
    ctx.fillStyle = gv; ctx.fillRect(0, 0, w, h)
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 10
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _tankShellTexCache = t
  return t
}

let _stackPanelTexCache = null
export function stackPanelTex() {
  if (_stackPanelTexCache) return _stackPanelTexCache
  const t = _makeCanvasTex(512, 1024, (ctx, w, h) => {
    const segH = 64
    for (let y = 0; y < h; y += segH) {
      ctx.fillStyle = (y / segH) % 2 === 0 ? '#d8d2c4' : '#a6423a'
      ctx.fillRect(0, y, w, segH)
    }
    const gv = ctx.createLinearGradient(0, 0, w, 0)
    gv.addColorStop(0, 'rgba(0,0,0,0.30)'); gv.addColorStop(0.5, 'rgba(0,0,0,0)')
    gv.addColorStop(1, 'rgba(255,255,255,0.10)')
    ctx.fillStyle = gv; ctx.fillRect(0, 0, w, h)
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 14
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _stackPanelTexCache = t
  return t
}

let _wallPanelTexCache = null
export function wallPanelTex() {
  if (_wallPanelTexCache) return _wallPanelTexCache
  const t = _makeCanvasTex(1024, 512, (ctx, w, h) => {
    ctx.fillStyle = '#aab6c2'; ctx.fillRect(0, 0, w, h)
    const ribs = 14
    for (let i = 0; i < ribs; i++) {
      const x = (i + 0.5) * (w / ribs)
      const half = (w / ribs) * 0.5
      const g = ctx.createLinearGradient(x - half, 0, x + half, 0)
      g.addColorStop(0, 'rgba(255,255,255,0.18)'); g.addColorStop(0.5, 'rgba(255,255,255,0)')
      g.addColorStop(1, 'rgba(0,0,0,0.18)')
      ctx.fillStyle = g; ctx.fillRect(x - half, 0, half * 2, h)
    }
    for (let y = 0; y < h; y += h / 4) {
      ctx.fillStyle = 'rgba(0,0,0,0.20)'; ctx.fillRect(0, y, w, 2)
    }
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 14
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _wallPanelTexCache = t
  return t
}

let _rollerTexCache = null
export function rollerTex() {
  if (_rollerTexCache) return _rollerTexCache
  const t = _makeCanvasTex(128, 128, (ctx, w, h) => {
    ctx.fillStyle = '#8b95a1'; ctx.fillRect(0, 0, w, h)
    ctx.fillStyle = '#586070'
    for (let i = -128; i < 128; i += 28) ctx.fillRect(i, 0, 14, 128)
  }, [1, 3])
  _rollerTexCache = t
  return t
}

export function makeSkyTex(stops) {
  const c = document.createElement('canvas')
  c.width = 16; c.height = 256
  const ctx = c.getContext('2d')
  const grad = ctx.createLinearGradient(0, 0, 0, 256)
  grad.addColorStop(0.0, stops[0]); grad.addColorStop(0.5, stops[1]); grad.addColorStop(1.0, stops[2])
  ctx.fillStyle = grad; ctx.fillRect(0, 0, 16, 256)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/* ========== 标签绘制辅助 ========== */
export const LABEL_W = 300
export const LABEL_H = 132
export const LABEL_SS = 3
export const LABEL_SCALE = 13
export const LABEL_ASPECT = LABEL_H / LABEL_W
export const LABEL_FONT = '"PingFang SC","Microsoft YaHei",-apple-system,sans-serif'

export function fmtMetric(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

export function labelRow(ctx, tag, tagColor, value, unit, valueColor, y) {
  ctx.textAlign = 'left'; ctx.font = `bold 14px ${LABEL_FONT}`
  ctx.fillStyle = tagColor; ctx.fillText(tag, 28, y)
  ctx.textAlign = 'right'
  ctx.fillStyle = valueColor; ctx.fillText(value, LABEL_W - 56, y)
  ctx.font = `12px ${LABEL_FONT}`
  ctx.fillStyle = '#8899aa'; ctx.fillText(unit, LABEL_W - 16, y)
}

export function drawLabelCard(ctx, focused) {
  const bg = ctx.createLinearGradient(0, 0, 0, LABEL_H)
  bg.addColorStop(0, focused ? 'rgba(22,32,48,0.97)' : 'rgba(13,20,32,0.95)')
  bg.addColorStop(1, focused ? 'rgba(16,24,38,0.97)' : 'rgba(8,14,26,0.95)')
  ctx.fillStyle = bg; ctx.fillRect(0, 0, LABEL_W, LABEL_H)
  ctx.strokeStyle = focused ? '#00e5ff' : 'rgba(0,180,216,0.20)'
  ctx.lineWidth = focused ? 1.5 : 1
  ctx.strokeRect(0.5, 0.5, LABEL_W - 1, LABEL_H - 1)
}
