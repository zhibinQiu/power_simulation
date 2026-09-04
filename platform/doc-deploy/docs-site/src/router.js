// 轻量 hash 路由：/#/ 首页，/#/promo 宣传手册，/#/manual 使用手册，/#/tech 技术文档
// 支持查询参数：/#/promo?from=<平台地址>，用于「返回平台」链接
import { ref } from 'vue'

function parse() {
  let p = (location.hash || '#/').replace(/^#/, '')
  if (!p.startsWith('/')) p = '/' + p
  const qi = p.indexOf('?')
  const query = {}
  if (qi >= 0) {
    const qs = p.slice(qi + 1)
    for (const pair of qs.split('&')) {
      const idx = pair.indexOf('=')
      if (idx <= 0) continue
      const k = decodeURIComponent(pair.slice(0, idx))
      const v = decodeURIComponent(pair.slice(idx + 1))
      query[k] = v
    }
    p = p.slice(0, qi)
  }
  return { path: p, query }
}

const parsed = parse()
export const route = ref(parsed.path)
export const routeQuery = ref(parsed.query)

export function navigate(to) {
  if (route.value === to && location.hash === '#' + to) return
  location.hash = to
}

export function buildHref(path, query) {
  let h = '#' + path
  if (query && Object.keys(query).length) {
    h += '?' + Object.entries(query)
      .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
      .join('&')
  }
  return h
}

window.addEventListener('hashchange', () => {
  const p = parse()
  route.value = p.path
  routeQuery.value = p.query
  window.scrollTo(0, 0)
})
