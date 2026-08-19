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

// 同一同步块：相机对准组 → 计算组标签(sprite)屏幕坐标 → 清空选中 → dispatch 真实 click
const res = await page.evaluate((gid) => {
  const sc = window.__twinScene
  if (sc.setAutoRotate) sc.setAutoRotate(false)
  if (sc.controls) sc.controls.autoRotate = false
  const grp = sc.groupModels.get(gid)
  sc.camera.position.set(grp.centerX, 0, grp.centerZ + 300)
  sc.controls.target.set(grp.centerX, 0, grp.centerZ)
  sc.controls.update()

  // 组标签世界坐标 → 屏幕坐标（sprite.getWorldPosition）
  const labelObj = grp.labelObj || {}
  const sprite = labelObj.sprite || (grp.label && grp.label.children && grp.label.children.find((c) => c.isSprite))
  if (!sprite) return { error: 'no sprite', labelKeys: Object.keys(grp.labelObj || {}) }
  const v = sc.camera.position.clone()
  sprite.getWorldPosition(v)
  v.project(sc.camera)
  const rect = sc.renderer.domElement.getBoundingClientRect()
  const sx = (v.x * 0.5 + 0.5) * rect.width
  const sy = (-v.y * 0.5 + 0.5) * rect.height
  const inView = sx >= 0 && sx <= rect.width && sy >= 0 && sy <= rect.height

  // 清空选中，包装回调，点击标签
  sc.setSelected(null)
  window.__clickedGroup = null
  const orig = sc.onSelectGroup
  sc.onSelectGroup = (g) => { window.__clickedGroup = g; orig(g) }
  if (inView) {
    sc.renderer.domElement.dispatchEvent(new MouseEvent('click', {
      bubbles: true, cancelable: true,
      clientX: rect.left + sx, clientY: rect.top + sy,
    }))
  }
  return { sx, sy, rectW: rect.width, rectH: rect.height, inView, labelTop: grp.topY }
}, gid)
console.log('标签坐标与点击:', JSON.stringify(res))
if (res.error) { await browser.close(); process.exit(1) }
if (!res.inView) { console.log('标签不在画布内，无法点击'); await browser.close(); process.exit(1) }

await page.waitForTimeout(1500)

const after = await page.evaluate((gid) => {
  const sc = window.__twinScene
  const grp = sc.groupModels.get(gid)
  return {
    clickedGroup: window.__clickedGroup,
    focusedId: sc.focusedId,
    ringOpacity: grp && grp.ring ? grp.ring.material.opacity : null,
  }
}, gid)
console.log('AFTER:', JSON.stringify(after, null, 2))
console.log('点击标签命中 onSelectGroup:', after.clickedGroup === gid ? 'YES ✓' : 'NO ✗ (' + after.clickedGroup + ')')
console.log('聚焦 focusedId:', after.focusedId === gid ? 'YES ✓' : 'NO ✗ (' + after.focusedId + ')')
console.log('小组选中环:', after.ringOpacity === 0.95 ? '已点亮 ✓' : '未点亮 ✗ (' + after.ringOpacity + ')')

await page.screenshot({ path: '/Users/qiuzhibin/project/simulation/verify_label_click.png' })
console.log('截图: /Users/qiuzhibin/project/simulation/verify_label_click.png')

await browser.close()
console.log('DONE')