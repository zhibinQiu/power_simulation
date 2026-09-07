// Node SSR 环境缺少浏览器全局：注入最小 stub，使模块顶层可求值
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}
globalThis.sessionStorage = globalThis.localStorage
const el = () => ({ style: {}, classList: { add() {}, remove() {}, toggle() {} }, setAttribute() {}, appendChild() {}, addEventListener() {}, removeEventListener() {}, getBoundingClientRect: () => ({ left: 0, top: 0, width: 0, height: 0 }) })
globalThis.document = { documentElement: el(), body: el(), createElement: el, querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {} }
globalThis.window = globalThis
try { Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'node', language: 'zh-CN' }, configurable: true }) } catch (e) {}
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', root: process.cwd(), logLevel: 'error' })
const mod = await server.ssrLoadModule('/src/components/CarbonBoxView.vue')
const app = createSSRApp(mod.default)
app.use(createPinia())
app.config.warnHandler = (msg) => console.log('[warn]', String(msg).slice(0, 200))

const t0 = Date.now()
const timer = setTimeout(() => { console.log('TIMEOUT: 渲染超过 25s，疑似死循环'); process.exit(2) }, 25000)
try {
  const html = await renderToString(app)
  clearTimeout(timer)
  console.log('RENDER OK, ms=', Date.now() - t0, 'htmlLen=', html.length)
  console.log('head:', html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 300))
} catch (e) {
  clearTimeout(timer)
  console.log('RENDER FAIL:', (e.stack || e.message).slice(0, 1200))
}
await server.close()
process.exit(0)
