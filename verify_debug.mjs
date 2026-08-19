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
  store.loadTemplate('long')
  const inj = store.scheme.nodes.find((n) => n.name === '喷吹系统1')
  const before = store.scheme.groups.length
  store.setFlowCount(inj.id, 2)
  const newGroup = store.scheme.groups.find((g) => g.members && g.members.length > 0 && g.name.includes('喷吹'))
  // 直接打印各组
  const all = store.scheme.groups.map((g) => ({
    name: g.name,
    members: Array.isArray(g.members) ? g.members.slice() : g.members,
    len: g.members ? g.members.length : -1,
  }))
  // 通过 toRaw 检查真实内容
  const { toRaw } = await import('/node_modules/vue/dist/vue.runtime.esm-bundler.js').catch(() => null)
  return {
    before,
    injId: inj.id,
    injGroupId: inj.groupId,
    injCount: inj.count,
    all,
  }
})
console.log(JSON.stringify(res, null, 2))
await browser.close()
console.log('DONE')
