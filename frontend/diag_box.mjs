import { chromium } from 'playwright'

const URL = process.env.U || 'http://127.0.0.1:41021/sim/'
const NO_RO = !!process.env.NO_RO
const NO_WS = !!process.env.NO_WS
const b = await chromium.launch({ headless: true, args: ['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage'] })
const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } })
await ctx.addInitScript(({ noRo, noWs }) => {
  window.requestIdleCallback = () => {}
  if (noRo) { try { delete window.ResizeObserver } catch (e) { window.ResizeObserver = undefined } }
  if (noWs) { window.WebSocket = undefined }
}, { noRo: NO_RO, noWs: NO_WS })
const p = await ctx.newPage()
const logs = []
p.on('console', (m) => { if (m.type() === 'error') logs.push('ERR: ' + m.text().slice(0, 160)) })
p.on('pageerror', (e) => logs.push('PAGEERROR: ' + (e.stack || e.message).slice(0, 500)))
p.on('crash', () => logs.push('!! CRASH'))
console.log('NO_RO=', NO_RO, 'NO_WS=', NO_WS)
await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
await p.waitForTimeout(6000)
await p.getByText('视图', { exact: true }).first().click()
await p.waitForTimeout(800)
await p.getByText('能碳一体机管理', { exact: false }).first().click()
for (const t of [1500, 3000, 4000]) {
  await p.waitForTimeout(t)
  try {
    const r = await p.evaluate(() => {
      const c = document.querySelector('.cbx-view')
      return { len: c ? c.innerHTML.length : 0, txt: c ? (c.innerText || '').replace(/\s+/g, ' ').slice(0, 120) : null }
    })
    console.log('probe +' + t, JSON.stringify(r))
  } catch (e) { console.log('probe +' + t, 'FAIL', e.message.slice(0, 80)) }
}
console.log('--- logs ---')
console.log(logs.slice(0, 8).join('\n') || '(none)')
await b.close().catch(() => {})
