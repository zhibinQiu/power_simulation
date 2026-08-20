// 后端 API 客户端（原生 fetch 封装，零额外依赖）
const BASE = '/api'

async function jpost(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`API ${path} -> ${r.status}`)
  return r.json()
}

async function jget(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error(`API ${path} -> ${r.status}`)
  return r.json()
}

async function jput(path, body) {
  const r = await fetch(BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`API ${path} -> ${r.status}`)
  return r.json()
}

export const api = {
  presetModel: () => jget('/model/preset'),
  presetStrategies: () => jget('/presets/strategies'),
  getFactors: () => jget('/factors'),
  getParamSchema: () => jget('/param-schema'),
  getDevices: () => jget('/devices'),
  getDeviceHistory: () => jget('/devices/history'),
  getPlatformConfig: () => jget('/platform-config'),
  savePlatformConfig: (cfg) => jput('/platform-config', cfg),
  resetPlatformConfig: () => jpost('/platform-config/reset', {}),
  parse: (text, model) => jpost('/parse', { text, model }),
  simulate: (model, ops = [], factors = null) => jpost('/simulate', { model, ops, factors }),
  listStrategies: () => jget('/strategies'),
  createStrategy: (name, description, raw_text, ops) =>
    jpost('/strategies', { name, description, raw_text, ops }),
  deleteStrategy: (sid) => fetch(BASE + '/strategies/' + sid, { method: 'DELETE' }).then(r => r.json()),
  applyStrategy: (sid, model, factors = null) => jpost('/strategies/' + sid + '/apply', { model, factors }),
  updateStrategy: (sid, patch) => {
    const qs = new URLSearchParams()
    for (const k of ['name', 'description', 'raw_text']) {
      if (patch && patch[k] != null) qs.set(k, patch[k])
    }
    if (patch && Array.isArray(patch.ops)) qs.set('ops', JSON.stringify(patch.ops))
    return fetch(BASE + '/strategies/' + sid + (qs.toString() ? '?' + qs.toString() : ''), { method: 'PUT' }).then(r => r.json())
  },
  // 参数扫描（一维敏感性分析）：固定其余参数，扫描单工序某参数，返回随参数变化的全厂指标曲线
  scan: (model, unitId, param, low, high, steps = 11, factors = null) =>
    jpost('/scan', { model, unit_id: unitId, param, low, high, steps, factors }),
  // 碳素流守恒审计：逐工序核对碳输入与各去向，返回闭合余量
  audit: (model) => jpost('/audit', model),
  generateReport: (payload) => jpost('/report', payload),
  getReportTask: (taskId) => jget('/report/task/' + taskId),
  listReports: () => jget('/reports'),
  getReport: (id) => jget('/report/' + id),
  deleteReport: (id) => fetch(BASE + '/reports/' + id, { method: 'DELETE' }).then(r => r.json()),
  // AI 优化模型（GA / PSO / RL 在线训练）
  optimizerContext: (model, factors = null) => jpost('/optimizers/context', { model, factors }),
  listOptimizers: () => jget('/optimizers'),
  getOptimizer: (id) => jget('/optimizers/' + id),
  startOptimizer: (id) => jpost('/optimizers/' + id + '/start', {}),
  stopOptimizer: (id) => jpost('/optimizers/' + id + '/stop', {}),
  trainOptimizer: (id, steps = 1) => jpost('/optimizers/' + id + '/train', { steps }),
  resetOptimizer: (id) => jpost('/optimizers/' + id + '/reset', {}),
  setOptimizerHyper: (id, patch) => jput('/optimizers/' + id + '/hyper', patch),
  applyOptimizer: (id) => jpost('/optimizers/' + id + '/apply', {}),
  setOptimizerSettings: (id, patch) => jput('/optimizers/' + id + '/settings', patch),
  archiveOptimizer: (id) => jpost('/optimizers/' + id + '/archive', {}),
  switchOptimizerVersion: (id, versionId) => jpost('/optimizers/' + id + '/switch', { version_id: versionId }),
  ackOptimizer: (id) => jpost('/optimizers/' + id + '/ack', {}),
  // 碳市场实时行情（CEA / CCER）
  carbonMarketQuotes: () => jget('/carbon-market/quotes'),
  carbonMarketChart: (instrument = 'cea', kind = 'daily') =>
    jget('/carbon-market/chart?instrument=' + instrument + '&kind=' + kind),
  carbonMarketForecast: (instrument = 'cea', days = 10) =>
    jget('/carbon-market/forecast?instrument=' + instrument + '&days=' + days),
  // 市场快讯（中国煤炭交易网）
  marketNews: (page = 1) => jget('/market-news?page=' + page),
}

// WebSocket 模拟遥测（url 省略则连接内置模拟 /api/ws/feed）
export function openFeed(onMessage, onStatus, url) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const target = url || `${proto}://${location.host}/api/ws/feed`
  const ws = new WebSocket(target)
  ws.onopen = () => onStatus && onStatus('open')
  ws.onclose = () => onStatus && onStatus('closed')
  ws.onerror = () => onStatus && onStatus('error')
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch (_) {}
  }
  return ws
}
