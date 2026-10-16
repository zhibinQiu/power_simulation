import { chromium } from 'playwright'

const URL = process.env.U || 'http://127.0.0.1:8010/sim/'
const b = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } })
await ctx.addInitScript(() => { window.requestIdleCallback = () => {} })
const p = await ctx.newPage()
const evs = []
p.on('console', (m) => { if (m.type() === 'error') evs.push('ERR ' + m.text().slice(0, 150)) })
p.on('pageerror', (e) => evs.push('PAGEERROR ' + (e.stack || e.message).slice(0, 250)))
p.on('crash', () => evs.push('!!! CRASH'))

const sn = async (tag) => {
  const r = await p.evaluate(() => {
    const q = (s) => document.querySelector(s)
    const ddev = q('.cbx-topo-mod.devgroup')
    const cv = q('.cbx-topo-canvas')
    return {
      hasView: !!q('.cbx-view'),
      canvas: cv ? { h: cv.offsetHeight, w: cv.offsetWidth } : null,
      devgroup: ddev ? {
        w: ddev.offsetWidth, h: ddev.offsetHeight, inline: ddev.getAttribute('style'),
        rect: (() => { const r = ddev.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })(),
      } : null,
      devCount: document.querySelectorAll('.cbx-topo-dev').length,
      groups: [...document.querySelectorAll('.cbx-topo-devgroup')].map((g) => (g.querySelector('.cbx-topo-devlabel') || {}).innerText),
      devlistText: (q('.cbx-topo-mod.devgroup .cbx-topo-devlist') || {}).innerText,
      lanes: [...document.querySelectorAll('.cbx-topo-lane')].map((l) => {
        const r2 = l.getBoundingClientRect()
        return { t: (l.querySelector('.cbx-topo-lane-title') || {}).innerText, w: Math.round(r2.width), x: Math.round(r2.left), y: Math.round(r2.top) }
      }),
      ph: document.querySelectorAll('.cbx-topo-mod-ph').length,
      svgLinks: document.querySelectorAll('.cbx-topo-svg-link').length,
      ls: (() => { try { return localStorage.getItem('cbx-topo-pos-v2') } catch (e) { return null } })(),
    }
  })
  console.log('=== ' + tag + ' ===\n' + JSON.stringify(r, null, 1))
}

await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
await p.waitForTimeout(5000)
try {
  await p.getByText('视图', { exact: true }).first().click({ timeout: 5000 })
  await p.waitForTimeout(700)
  const items = await p.locator('text=数据源管理').count()
  console.log('菜单项 数据源管理 count=', items)
  await p.getByText('数据源管理', { exact: false }).first().click({ timeout: 5000 })
} catch (e) { console.log('菜单操作失败 ' + e.message.slice(0, 100)) }
await p.waitForTimeout(6000)
await sn('prod-initial')
await p.screenshot({ path: '/tmp/prod-initial.png' }).catch(() => {})
console.log('--- events ---')
console.log(evs.slice(0, 8).join('\n') || '(none)')
await b.close().catch(() => {})
