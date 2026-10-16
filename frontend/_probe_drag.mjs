import { chromium } from 'playwright'

const URL = process.env.U || 'http://127.0.0.1:5173/sim/'
const b = await chromium.connectOverCDP('http://127.0.0.1:9333')
const ctx = b.contexts()[0]
const p = await ctx.newPage()
const evs = []
p.on('console', (m) => { if (m.type() === 'error') evs.push('ERR ' + m.text().slice(0, 160)) })
p.on('pageerror', (e) => evs.push('PAGEERROR ' + (e.stack || e.message).slice(0, 250)))

const openView = async () => {
  await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await p.waitForTimeout(4500)
  await p.getByText('视图', { exact: true }).first().click({ timeout: 6000 })
  await p.waitForTimeout(700)
  await p.getByText('数据源管理', { exact: false }).first().click({ timeout: 6000 })
  await p.waitForTimeout(6000)
}

const probe = async (tag) => {
  const r = await p.evaluate(() => {
    const q = (s) => document.querySelector(s)
    const ddev = q('.cbx-topo-mod.devgroup')
    return {
      devgroup: ddev ? {
        w: ddev.offsetWidth, h: ddev.offsetHeight, inline: ddev.getAttribute('style'),
        rect: (() => { const r = ddev.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })(),
      } : null,
      devCount: document.querySelectorAll('.cbx-topo-dev').length,
      canvasH: (q('.cbx-topo-canvas') || {}).offsetHeight,
      canvasRect: (() => { const c = q('.cbx-topo-canvas'); if (!c) return null; const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })(),
      ph: document.querySelectorAll('.cbx-topo-mod-ph').length,
      ls: (() => { try { return localStorage.getItem('cbx-topo-pos-v2') } catch (e) { return 'n/a' } })(),
    }
  })
  console.log('=== ' + tag + ' ===\n' + JSON.stringify(r, null, 1))
  return r
}

// 打开视图（首次会先清掉历史位置）
await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
await p.evaluate(() => { try { localStorage.removeItem('cbx-topo-pos-v2') } catch (e) {} })
await openView()
await probe('before-drag')

// 模拟拖拽「采集设备」卡片（位移 40x30）
const drag = await p.evaluate(() => {
  const el = document.querySelector('.cbx-topo-mod.devgroup')
  if (!el) return 'no-el'
  const r = el.getBoundingClientRect()
  const x0 = r.left + r.width - 10, y0 = r.top + 12
  const mk = (type, x, y) => new PointerEvent(type, { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse', isPrimary: true })
  el.dispatchEvent(mk('pointerdown', x0, y0))
  window.dispatchEvent(mk('pointermove', x0 + 20, y0 + 15))
  window.dispatchEvent(mk('pointermove', x0 + 40, y0 + 30))
  window.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, clientX: x0 + 40, clientY: y0 + 30, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true }))
  return 'dragged'
})
console.log('drag: ' + drag)
await p.waitForTimeout(1200)
await probe('after-drag')

// 刷新后再看（模拟用户重新打开页面）
await openView()
await probe('after-reload')
await p.screenshot({ path: '/tmp/cdp-after-reload.png' }).catch(() => {})
console.log('--- events ---\n' + (evs.slice(0, 6).join('\n') || '(none)'))
await b.close().catch(() => {})
