import { chromium } from '/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs'

const base = 'http://127.0.0.1:5173'
const browser = await chromium.launch({
  executablePath: '/Users/qiuzhibin/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 200)))

await page.goto(base, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

const dump = await page.evaluate(() => {
  const sc = window.__twinScene
  if (!sc) return { error: 'no __twinScene' }
  const flows = sc.flows || []
  return { totalFlows: flows.length }
})
console.log('SCENE flows 数量:', JSON.stringify(dump))

await page.screenshot({ path: '/Users/qiuzhibin/project/simulation/verify_group_links.png' })
console.log('截图: /Users/qiuzhibin/project/simulation/verify_group_links.png')

await browser.close()
console.log('DONE')