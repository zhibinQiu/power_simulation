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

// 1) 定位热风组 gid 与组内成员
const meta = await page.evaluate(() => {
  const sc = window.__twinScene
  if (!sc) return { error: 'no __twinScene' }
  let gid = null
  for (const [k, m] of sc.groupModels) {
    if (/热风/.test(m.groupName || '')) { gid = k; break }
  }
  if (!gid) return { error: 'no 热风 group' }
  const members = sc.model.units.filter((u) => u.groupId === gid).map((u) => u.id)
  return { gid, members, topFlowCount: sc.flows.length }
})
console.log('META:', JSON.stringify(meta))
if (!meta.gid) { await browser.close(); process.exit(1) }

// 2) 同步块：相机对准热风组 → 投影组标签坐标 → 点击标签（走 onSelectGroup → store.enterGroup）
const clickRes = await page.evaluate((gid) => {
  const sc = window.__twinScene
  if (sc.setAutoRotate) sc.setAutoRotate(false)
  if (sc.controls) sc.controls.autoRotate = false
  const grp = sc.groupModels.get(gid)
  sc.camera.position.set(grp.centerX, 0, grp.centerZ + 300)
  sc.controls.target.set(grp.centerX, 0, grp.centerZ)
  sc.controls.update()
  const labelObj = grp.labelObj || {}
  const sprite = labelObj.sprite || (grp.label && grp.label.children && grp.label.children.find((c) => c.isSprite))
  if (!sprite) return { error: 'no sprite', labelKeys: Object.keys(labelObj) }
  const v = sc.camera.position.clone()
  sprite.getWorldPosition(v)
  v.project(sc.camera)
  const rect = sc.renderer.domElement.getBoundingClientRect()
  const sx = (v.x * 0.5 + 0.5) * rect.width
  const sy = (-v.y * 0.5 + 0.5) * rect.height
  const inView = sx >= 0 && sx <= rect.width && sy >= 0 && sy <= rect.height
  window.__clickedGroup = null
  const orig = sc.onSelectGroup
  sc.onSelectGroup = (g) => { window.__clickedGroup = g; orig(g) }
  if (inView) {
    sc.renderer.domElement.dispatchEvent(new MouseEvent('click', {
      bubbles: true, cancelable: true,
      clientX: rect.left + sx, clientY: rect.top + sy,
    }))
  }
  return { sx, sy, inView }
}, meta.gid)
console.log('CLICK:', JSON.stringify(clickRes))
if (clickRes.error || !clickRes.inView) { await browser.close(); process.exit(1) }

await page.waitForTimeout(2200)

// 3) 进入组场景后的 3D 状态
const inGroup = await page.evaluate(({ gid, members }) => {
  const sc = window.__twinScene
  const keys = [...sc.unitGroups.keys()]
  return {
    clickedGroup: window.__clickedGroup,
    groupScene: sc.groupScene,
    unitGroupsSize: keys.length,
    memberOnly: keys.length === members.length && members.every((id) => keys.includes(id)),
    members,
    groupModelsSize: sc.groupModels.size,
    flowIds: sc.flows.map((f) => f.flowId),
    // 组内连线判定：取 model.flows 中两端均为该组成员的连线，与场景实际绘制条数比对
    allFlowsGroupInternal: (() => {
      const internal = new Set()
      for (const f of sc.model.flows) {
        const a = sc.model.units.find((u) => u.id === f.from_unit)
        const b = sc.model.units.find((u) => u.id === f.to_unit)
        if (a && b && a.groupId === gid && b.groupId === gid) internal.add(f.id || f.flowId)
      }
      return sc.flows.length === internal.size && sc.flows.every((fl) => internal.has(fl.flowId))
    })(),
  }
}, meta)
console.log('IN-GROUP-3D:', JSON.stringify(inGroup, null, 2))

// 4) DOM 检查：返回浮层 + 右侧小组属性面板
const dom = await page.evaluate(() => {
  const bar = document.querySelector('.group-scene-bar')
  const title = document.querySelector('.gs-title')
  const flowTitle = document.querySelector('.right-drawer .rd-head, .rpanel .rd-head, .right-panel .rd-head')
  const rightText = document.body.innerText
  return {
    barExists: !!bar,
    barText: bar ? bar.innerText : '',
    titleText: title ? title.textContent : '',
    hasMemberSection: /成员设备/.test(rightText),
    hasCo2Trail: /tCO₂\/h/.test(rightText),
    headTitle: flowTitle ? flowTitle.textContent.trim() : (document.querySelector('.rd-head') ? document.querySelector('.rd-head').textContent.trim() : null),
  }
})
console.log('DOM:', JSON.stringify(dom, null, 2))

// 5) 点击「返回顶层」
if (dom.barExists) {
  await page.click('.group-scene-bar .gs-back')
  await page.waitForTimeout(2200)
}
const back = await page.evaluate(() => {
  const sc = window.__twinScene
  return {
    groupScene: sc.groupScene,
    groupModelsSize: sc.groupModels.size,
    unitGroupsSize: sc.unitGroups.size,
    barGone: !document.querySelector('.group-scene-bar'),
  }
})
console.log('BACK-TO-TOP:', JSON.stringify(back, null, 2))

console.log('--- 结论 ---')
console.log('点击标签命中 onSelectGroup:', inGroup.clickedGroup === meta.gid ? 'YES ✓' : 'NO ✗')
console.log('进入小组子场景 (groupScene=gid):', inGroup.groupScene === meta.gid ? 'YES ✓' : 'NO ✗')
console.log('成员全部展开为独立工序:', inGroup.memberOnly ? 'YES ✓' : 'NO ✗ (' + JSON.stringify(inGroup.members) + ' vs keys)')
console.log('组内连线已绘制:', inGroup.allFlowsGroupInternal ? 'YES ✓ (' + inGroup.flowIds.join(',') + ')' : 'NO ✗')
console.log('返回浮层显示:', dom.barExists ? 'YES ✓' : 'NO ✗')
console.log('右侧小组属性(成员列表+实测值):', (dom.hasMemberSection && dom.hasCo2Trail) ? 'YES ✓' : 'NO ✗')
console.log('返回顶层恢复:', back.groupScene === null && back.groupModelsSize > 0 && back.barGone ? 'YES ✓' : 'NO ✗')

await page.screenshot({ path: '/Users/qiuzhibin/project/simulation/verify_group_scene.png' })
console.log('截图: /Users/qiuzhibin/project/simulation/verify_group_scene.png')
await browser.close()
console.log('DONE')
