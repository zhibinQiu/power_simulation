import { chromium } from 'playwright'

const BASE = process.env.BASE || 'http://localhost:5173'
const errors = []
const log = (...a) => console.log(...a)

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined })
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))
// 无 GPU 环境：绕过 requestIdleCallback 挂载 3D
await page.addInitScript(() => { window.requestIdleCallback = (cb) => setTimeout(cb, 50) })

log('open', BASE)
await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 20000 })
await page.waitForTimeout(3500)

// 1. 顶部找场景/机房温控入口
const topBtns = await page.evaluate(() =>
  Array.from(document.querySelectorAll('button, .menu-item, .top-menu, [class*="menu"]'))
    .map((b) => (b.textContent || '').trim())
    .filter((s) => s && s.length < 40)
)
log('TOP-BTNS:', JSON.stringify(topBtns.slice(0, 60)))

// 查找包含 机房/温控/数据中心 文本的可点击元素
const found = await page.evaluate(() => {
  const all = Array.from(document.querySelectorAll('button, span, div, li, a, .scn-item, [class*="scene"]'))
  const hit = all.filter((e) => /机房温控|数据中心温控|温控孪生|dc-thermal|制冷/.test((e.textContent || '').trim()) && (e.textContent || '').trim().length < 60)
  return hit.slice(0, 8).map((e) => ({ tag: e.tagName, cls: e.className && String(e.className).slice(0, 60), txt: (e.textContent || '').trim().slice(0, 50) }))
})
log('SCENE-HIT:', JSON.stringify(found))

await browser.close()
process.exit(errors.length ? 1 : 0)
