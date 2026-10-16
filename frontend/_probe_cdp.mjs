import { chromium } from 'playwright'

const URL = process.env.U || 'http://127.0.0.1:5173/sim/'
const b = await chromium.connectOverCDP('http://127.0.0.1:9333')
const ctx = b.contexts()[0]
const p = await ctx.newPage()
const evs = []
p.on('console', (m) => { if (m.type() === 'error') evs.push('ERR ' + m.text().slice(0, 160)) })
p.on('pageerror', (e) => evs.push('PAGEERROR ' + (e.stack || e.message).slice(0, 250)))
p.on('crash', () => evs.push('!!! CRASH'))

const probe = async (tag) => {
  try {
    const r = await p.evaluate(() => {
      const q = (s) => document.querySelector(s)
      const ddev = q('.cbx-topo-mod.devgroup')
      const cv = q('.cbx-topo-canvas')
      const info = ddev ? {
        w: ddev.offsetWidth, h: ddev.offsetHeight, inline: ddev.getAttribute('style'),
        rect: (() => { const r = ddev.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })(),
        overflow: getComputedStyle(ddev).overflow,
      } : null
      return {
        view: !!q('.cbx-view'),
        canvas: cv ? { w: cv.offsetWidth, h: cv.offsetHeight, rect: (() => { const r = cv.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] })() } : null,
        devgroup: info,
        devCount: document.querySelectorAll('.cbx-topo-dev').length,
        devText: [...document.querySelectorAll('.cbx-topo-dev')].slice(0, 8).map((d) => (d.innerText || '').replace(/\s+/g, ' ').slice(0, 30)),
        lanes: [...document.querySelectorAll('.cbx-topo-lane')].map((l) => {
          const r2 = l.getBoundingClientRect()
          return { t: (l.querySelector('.cbx-topo-lane-title') || {}).innerText, w: Math.round(r2.width), x: Math.round(r2.left), y: Math.round(r2.top), h: Math.round(r2.height) }
        }),
        ph: document.querySelectorAll('.cbx-topo-mod-ph').length,
        svgLinks: document.querySelectorAll('.cbx-topo-svg-link').length,
        ls: (() => { try { return localStorage.getItem('cbx-topo-pos-v2') } catch (e) { return 'n/a' } })(),
      }
    })
    console.log('=== ' + tag + ' ===\n' + JSON.stringify(r, null, 1))
  } catch (e) { console.log('PROBE FAIL ' + tag + ' ' + e.message.slice(0, 120)) }
}

if (process.env.CLEAR_LS) {
  await p.goto(URL, { waitUntil: 'domcontentloaded' })
  await p.evaluate(() => { try { localStorage.removeItem('cbx-topo-pos-v2') } catch (e) {} })
  console.log('localStorage cleared')
}
await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
await p.waitForTimeout(5000)
try {
  await p.getByText('视图', { exact: true }).first().click({ timeout: 6000 })
  await p.waitForTimeout(700)
  await p.getByText('数据源管理', { exact: false }).first().click({ timeout: 6000 })
} catch (e) { console.log('菜单失败 ' + e.message.slice(0, 100)) }
await p.waitForTimeout(7000)
await probe('initial')
await p.screenshot({ path: '/tmp/cdp-initial.png' }).catch((e) => console.log('shot fail'))
const btn = p.getByRole('button', { name: '自动布局' })
console.log('自动布局 count=' + (await btn.count()))
if (await btn.count()) {
  await btn.first().click()
  await p.waitForTimeout(1500)
  await probe('after-auto-layout')
  await p.screenshot({ path: '/tmp/cdp-after.png' }).catch(() => {})
}
console.log('--- events ---\n' + (evs.slice(0, 8).join('\n') || '(none)'))
await b.close().catch(() => {})
