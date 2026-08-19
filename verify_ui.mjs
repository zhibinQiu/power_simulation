import { chromium } from '/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs'

const base = 'http://127.0.0.1:5174'
const browser = await chromium.launch({
  executablePath: '/Users/qiuzhibin/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell',
  headless: true,
})
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
page.on('pageerror', (e) => console.log('[pageerror]', String(e).slice(0, 200)))

await page.goto(base, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

const res = await page.evaluate(async () => {
  const app = document.querySelector('#app').__vue_app__
  const pinia = app.config.globalProperties.$pinia
  const store = pinia._s.get('sim')
  if (!store) return { error: 'no sim store' }

  // 1. 加载长流程模板
  store.loadTemplate('long')
  const groups = store.scheme.groups.map((g) => ({ name: g.name, members: g.members.length }))
  const auxCounts = store.scheme.nodes.filter((n) => n.kind === 'process').map((n) => `${n.name}:${n.count || 1}`)

  // 2. 测试 setFlowCount：把「喷吹系统1」设为 2 台 → 自动成组
  const inj = store.scheme.nodes.find((n) => n.name === '喷吹系统1')
  const beforeGroups = store.scheme.groups.length
  store.setFlowCount(inj.id, 2)
  const afterUp = {
    gid: inj.groupId, count: inj.count,
    group: store.scheme.groups.find((g) => g.members.includes(inj.id)),
    totalGroups: store.scheme.groups.length,
  }
  // 3. 再设回 1 台 → 解散该组
  store.setFlowCount(inj.id, 1)
  const afterDown = { gid: inj.groupId, count: inj.count, totalGroups: store.scheme.groups.length }

  // 4. 测试 addPort 去重：给高炉输入加已有的煤粉端口
  const bf = store.scheme.nodes.find((n) => n.type === 'blast_furnace')
  const inBefore = bf.ports.in.length
  store.addPort(bf.id, 'in', 'pulverized_coal')
  const inAfter = bf.ports.in.length
  const dupToast = store.toast

  // 5. 测试 addConnection 多对一：同一输入端口连两个不同源
  const coke = store.scheme.nodes.find((n) => n.type === 'coke_oven')   // 焦炉
  const sinter = store.scheme.nodes.find((n) => n.type === 'sinter_plant') // 烧结机
  const bfIn = bf.ports.in.find((p) => p.material === 'sinter')   // 烧结矿输入口
  const connBefore = store.scheme.connections.length
  // 焦炉输出焦炭 → 烧结矿输入口（不同物料也可以先连上，验证多对一行为）
  const cokeOut = coke.ports.out[0]
  const ok1 = store.addConnection(coke.id, cokeOut.id, bf.id, bfIn.id, 'sinter', false)
  const ok2 = store.addConnection(sinter.id, sinter.ports.out[0].id, bf.id, bfIn.id, 'sinter', false)
  const connAfter = store.scheme.connections.length
  // 完全相同连接应去重
  const ok3 = store.addConnection(sinter.id, sinter.ports.out[0].id, bf.id, bfIn.id, 'sinter', false)

  return {
    groups,
    auxCounts,
    setFlowCount: { beforeGroups, afterUp, afterDown },
    portDedup: { inBefore, inAfter, dupToast },
    multiConn: { connBefore, ok1, ok2, connAfter, ok3 },
  }
})
console.log(JSON.stringify(res, null, 2))

await page.waitForTimeout(800)
await page.screenshot({ path: '/Users/qiuzhibin/project/simulation/edit_check.png' })
await browser.close()
console.log('DONE')
