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


