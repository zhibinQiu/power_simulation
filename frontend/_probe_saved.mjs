import { chromium } from 'playwright'

const URL = process.env.U || 'http://127.0.0.1:5173/sim/'
const TOP = Number(process.env.TOP || 600)
const LEFT = Number(process.env.LEFT || 348)
const b = await chromium.connectOverCDP('http://127.0.0.1:9333')
const ctx = b.contexts()[0]
const p = await ctx.newPage()
await p.setViewportSize({ width: 1600, height: 1000 }).catch(() => {})
const evs = []
p.on('console', (m) => { if (m.type() === 'error') evs.push('ERR ' + m.text().slice(0, 160)) })
p.on('pageerror', (e) => evs.push('PAGEERROR ' + (e.stack || e.message).slice(0, 250)))

await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
await p.evaluate(([left, top]) => {
  localStorage.setItem('cbx-topo-pos-v2', JSON.stringify({ d_devs: { left, top } }))
}, [LEFT, TOP])
await p.reload({ waitUntil: 'domcontentloaded' })
await p.waitForTimeout(4500)
await p.getByText('视图', { exact: true }).first().click({ timeout: 6000 })
await p.waitForTimeout(700)
await p.getByText('数据源管理', { exact: false }).first().click({ timeout: 6000 })
await p.waitForTimeout(7000)
try { await p.locator('.cbx-topo').scrollIntoViewIfNeeded({timeout:3000}) } catch(e){}
await p.waitForTimeout(400)
try { await p.locator('.cbx-topo').screenshot({path:'/tmp/topo-sec-'+TOP+'.png'}) } catch(e){ console.log('shot fail') }

const r = await p.evaluate(() => {
  const q = (s) => document.querySelector(s)
  const rect = (el) => { const x = el.getBoundingClientRect(); return [Math.round(x.left), Math.round(x.top), Math.round(x.width), Math.round(x.height)] }
  const ddev = q('.cbx-topo-mod.devgroup')
  const cv = q('.cbx-topo-canvas')
  let hit = null
  let vis = null
  if (ddev) {
    const rc = ddev.getBoundingClientRect()
    const cx = rc.left + rc.width / 2
    const cy = rc.top + 14
    const topEl = document.elementFromPoint(cx, cy)
    hit = topEl ? (topEl.className && String(topEl.className).slice(0, 60)) : 'null'
    vis = !!(topEl && (ddev.contains(topEl) || topEl === ddev))
  }
  return {
    viewport: [window.innerWidth, window.innerHeight],
    canvas: cv ? { rect: rect(cv), h: cv.offsetHeight, w: cv.offsetWidth } : null,
    devgroup: ddev ? { rect: rect(ddev), h: ddev.offsetHeight, w: ddev.offsetWidth, inline: ddev.getAttribute('style') } : null,
    devCount: document.querySelectorAll('.cbx-topo-dev').length,
    hitAtCardHeader: hit, cardVisibleAtHeader: vis,
    cards: [...document.querySelectorAll('.cbx-topo-mod')].map((m) => ({ c: String(m.className).slice(0, 40), rect: rect(m) })),
    devLaneRect: (() => { const l = q('.cbx-topo-lane.dev'); return l ? rect(l) : null })(),
    ls: localStorage.getItem('cbx-topo-pos-v2'),
  }
})
console.log('TOP=' + TOP + ' LEFT=' + LEFT + '\n' + JSON.stringify(r, null, 1))
await p.screenshot({ path: '/tmp/saved-' + TOP + '.png', fullPage: false }).catch(() => {})
await p.screenshot({ path: '/tmp/saved-' + TOP + '-full.png', fullPage: true }).catch(() => {})
console.log('--- events ---\n' + (evs.slice(0, 5).join('\n') || '(none)'))
await b.close().catch(() => {})
