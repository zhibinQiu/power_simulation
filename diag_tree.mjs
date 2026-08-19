import pkg from '/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs'
import fs from 'fs'
const { chromium } = pkg

const URL = 'http://127.0.0.1:5173'
const log = []
const browser = await chromium.launch({
  executablePath: '/Users/qiuzhibin/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell',
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--use-gl=swiftshader', '--enable-unsafe-swiftshader']
})
log.push('launched')
const page = await browser.newPage()
const errors = []
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', (e) => errors.push('PAGEERR: ' + e.message))

await page.goto(URL, { waitUntil: 'domcontentloaded' })
log.push('goto-done')
const deadline = Date.now() + 20000
while (Date.now() < deadline) {
  const ok = await page.evaluate(() => {
    const sc = window.__twinScene
    return sc && sc.flows && sc.flows.length > 0
  })
  if (ok) break
  await page.waitForTimeout(300)
}
log.push('scene-ready')
const probe = await page.evaluate(() => {
  const sc = window.__twinScene
  const out = { flows: sc && sc.flows ? sc.flows.length : 0, unitGroups: sc && sc.unitGroups ? sc.unitGroups.size : 0 }
  out.units = []
  if (sc && sc.unitGroups && typeof sc.unitGroups.forEach === 'function') {
    sc.unitGroups.forEach((g) => {
      const p = g.group && g.group.position
      if (p) out.units.push({ id: g.unitId, x: Math.round(p.x), y: Math.round(p.y), z: Math.round(p.z) })
    })
  }
  return out
})

await page.screenshot({ path: 'diag_tree.png' })
const units = probe.units || []
function analyze() {
  if (!units.length) return 'no units'
  const zs = units.map((u) => u.z)
  const ys = units.map((u) => u.y)
  const xs = units.map((u) => u.x)
  return {
    count: units.length,
    xRange: [Math.min(...xs), Math.max(...xs)],
    yRange: [Math.min(...ys), Math.max(...ys)],
    zRange: [Math.min(...zs), Math.max(...zs)],
    distinctZ: [...new Set(zs)].sort((a,b)=>a-b)
  }
}
const result = { log, errors: errors.slice(0, 8), probe, analyze: analyze() }
fs.writeFileSync('diag_tree_result.json', JSON.stringify(result, null, 2))
await browser.close()
process.stdout.write('DONE\n')

