import { chromium } from '/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs'

const base = 'http://127.0.0.1:5173'
const browser = await chromium.launch({
  executablePath: '/Users/qiuzhibin/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 300)))

await page.goto(base, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

const gid = await page.evaluate(() => {
  const sc = window.__twinScene
  for (const gid of sc.groupModels.keys()) {
    const m = sc.groupModels.get(gid)
    if (/热风/.test(m.groupName || '')) return gid
  }
  return null
})
console.log('热风组 gid:', gid)
if (!gid) { await browser.close(); process.exit(1) }

// 同一同步块：关闭自转 + 相机移到组正后方 + 包装回调 + dispatch 真实 click
const res = await page.evaluate((gid) => {
  const sc = window.__twinScene
  if (sc.setAutoRotate) sc.setAutoRotate(false)
  if (sc.controls) sc.controls.autoRotate = false
  const grp = sc.groupModels.get(gid)
  sc.camera.position.set(grp.centerX, 0, grp.centerZ + 300)
  sc.controls.target.set(grp.centerX, 0, grp.centerZ)
  sc.controls.update()

  window.__clickedGroup = null
  const orig = sc.onSelectGroup
  sc.onSelectGroup = (g) => { window.__clickedGroup = g; orig(g) }

  const rect = sc.renderer.domElement.getBoundingClientRect()
  sc.renderer.domElement.dispatchEvent(new MouseEvent('click', {
    bubbles: true, cancelable: true,
    clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2,
  }))
  return {
    cam: { x: sc.camera.position.x, y: sc.camera.position.y, z: sc.camera.position.z },
    target: { x: sc.controls.target.x, y: sc.controls.target.y, z: sc.controls.target.z },
    cx: grp.centerX, cz: grp.centerZ,
  }
}, gid)
console.log('相机对准组+点击:', JSON.stringify(res))

await page.waitForTimeout(1500)

const after = await page.evaluate((gid) => {
  const sc = window.__twinScene
  const grp = sc.groupModels.get(gid)
  return {
    clickedGroup: window.__clickedGroup,
    focusedId: sc.focusedId,
    ringOpacity: grp && grp.ring ? grp.ring.material.opacity : null,
    cam: { x: sc.camera.position.x, y: sc.camera.position.y, z: sc.camera.position.z },
  }
}, gid)
console.log('AFTER:', JSON.stringify(after, null, 2))
console.log('拾取命中 onSelectGroup:', after.clickedGroup === gid ? 'YES ✓' : 'NO ✗ (' + after.clickedGroup + ')')
console.log('聚焦 focusedId:', after.focusedId === gid ? 'YES ✓' : 'NO ✗ (' + after.focusedId + ')')
console.log('小组选中环:', after.ringOpacity === 0.95 ? '已点亮 ✓' : '未点亮 ✗ (' + after.ringOpacity + ')')

await page.screenshot({ path: '/Users/qiuzhibin/project/simulation/verify_group_focus.png' })
console.log('截图: /Users/qiuzhibin/project/simulation/verify_group_focus.png')

await browser.close()
console.log('DONE')