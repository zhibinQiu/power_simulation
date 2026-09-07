import { chromium } from 'playwright'

const errs = []
const base = 'http://127.0.0.1:5173/sim/'

const browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader'] })
const page = await browser.newPage({ viewport: { width: 1680, height: 950 } })
page.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text()) })
await page.addInitScript(() => { window.requestIdleCallback = (fn) => setTimeout(() => fn({ didTimeout: false }), 0); window.cancelIdleCallback = (id) => clearTimeout(id) })
await page.goto(base, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)

async function clickText(text, opts = {}) {
  const el = page.getByText(text, { exact: false }).first()
  await el.click()
  await page.waitForTimeout(opts.wait ?? 600)
}

// 1) 打开系统设置
await clickText('文件')
await clickText('设置…')
await page.waitForTimeout(500)
const hasDcBtn = await page.getByText('机房温控', { exact: true }).count()
console.log('[1] 设置弹窗含「机房温控」情景按钮:', hasDcBtn > 0)

// 2) 切到 dc-thermal 场景
if (hasDcBtn) {
  await clickText('机房温控')
  await page.waitForTimeout(2500)
}
// 左侧工艺树（当前场景制冷设备分组）
const procCount = await page.locator('.lrow, .l-tt, .lt-row').count()
console.log('[2] dc 场景资源管理器工艺树条目数(>0):', procCount)
// 右栏场景总览标题
const title = await page.locator('.inspector .sidebar-head .ttl, .inspector .ttl').first().textContent().catch(() => '')
console.log('[3] dc 场景右栏标题:', title)
const isOverview = await page.getByText('场景总览', { exact: false }).count()
console.log('[4] dc 场景出现「场景总览」卡:', isOverview > 0)
await page.screenshot({ path: '/tmp/smoke-dc.png' })

// 3) 切回钢铁 0 回归
await clickText('文件')
await clickText('设置…')
await clickText('钢铁')
await page.waitForTimeout(2000)
const steelTab = await page.getByText('工艺', { exact: true }).count()
console.log('[5] 切回钢铁后资源管理器「工艺」tab:', steelTab > 0)
const steelOk = await page.getByText('仿真', { exact: false }).count()
await page.screenshot({ path: '/tmp/smoke-steel.png' })
console.log('[6] 钢铁场景顶栏可见:', steelOk > 0)

console.log('ERRORS(' + errs.length + '):')
errs.slice(0, 15).forEach((e) => console.log('  ' + e))
await browser.close()
