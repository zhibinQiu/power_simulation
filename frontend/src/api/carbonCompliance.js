// 碳合规（企业履约台账 / 策略 / 预警 / 行情库表）API
// 对应后端 /api/carbon-assistant 下 carbon_compliance router
import { t } from '../i18n'
const base = '/api/carbon-assistant'

async function jfetch(url, opts = {}) {
  const res = await fetch(url, opts)
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      msg = data.detail || data.message || msg
    } catch (_) {}
    throw new Error(msg)
  }
  return res.json()
}

async function jblob(url) {
  const res = await fetch(url)
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      msg = data.detail || data.message || msg
    } catch (_) {}
    throw new Error(msg)
  }
  return res.blob()
}

function downloadBlob(blob, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(a.href)
}

function qs(params = {}) {
  const usp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') usp.set(k, v)
  })
  const s = usp.toString()
  return s ? `?${s}` : ''
}

export const carbonComplianceApi = {
  // meta / settings
  fetchMeta: () => jfetch(`${base}/meta`),
  fetchSettings: () => jfetch(`${base}/settings`),
  updateSettings: (payload) =>
    jfetch(`${base}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload }),
    }),

  // enterprises
  listEnterprises: () => jfetch(`${base}/enterprises`),
  createEnterprise: (body) =>
    jfetch(`${base}/enterprises`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  getEnterprise: (id) => jfetch(`${base}/enterprises/${id}`),
  updateEnterprise: (id, body) =>
    jfetch(`${base}/enterprises/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteEnterprise: (id) =>
    jfetch(`${base}/enterprises/${id}`, { method: 'DELETE' }),

  // emissions
  listEmissions: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/emissions`),
  upsertEmission: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/emissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteEmission: (enterpriseId, year) =>
    jfetch(`${base}/enterprises/${enterpriseId}/emissions/${year}`, { method: 'DELETE' }),

  // forecasts
  listForecasts: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/forecasts`),
  upsertForecast: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/forecasts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // CEA
  listCea: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/cea`),
  upsertCea: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/cea`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteCea: (enterpriseId, vintageYear) =>
    jfetch(`${base}/enterprises/${enterpriseId}/cea/${vintageYear}`, { method: 'DELETE' }),
  addCeaTrade: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/cea/trades`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // CCER
  listCcer: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/ccer`),
  upsertCcer: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/ccer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteCcer: (enterpriseId, holdingId) =>
    jfetch(`${base}/enterprises/${enterpriseId}/ccer/${holdingId}`, { method: 'DELETE' }),
  addCcerTrade: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/ccer/trades`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // green power / certs
  listGreenPower: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/green-power`),
  upsertGreenPower: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/green-power`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listGreenCerts: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/green-certs`),
  upsertGreenCert: (enterpriseId, body) =>
    jfetch(`${base}/enterprises/${enterpriseId}/green-certs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // market quotes
  listMarketCea: () => jfetch(`${base}/market/cea`),
  upsertMarketCea: (body) =>
    jfetch(`${base}/market/cea`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listMarketCcer: () => jfetch(`${base}/market/ccer`),
  upsertMarketCcer: (body) =>
    jfetch(`${base}/market/ccer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listMarketEnergy: () => jfetch(`${base}/market/energy`),
  upsertMarketEnergy: (body) =>
    jfetch(`${base}/market/energy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  syncMarketQuotes: () => jfetch(`${base}/market/sync`, { method: 'POST' }),

  // kline / forecast
  fetchCeaKline: (kind = 'daily', { method } = {}) =>
    jfetch(`${base}/market/cea/kline${qs({ kind, method: kind === 'forecast' ? method : undefined })}`),
  fetchCcerKline: (kind = 'daily', { method } = {}) =>
    jfetch(`${base}/market/ccer/kline${qs({ kind, method: kind === 'forecast' ? method : undefined })}`),
  fetchCeaForecast: () => jfetch(`${base}/market/cea/forecast`),

  // strategy
  runStrategy: (enterpriseId, complianceYear) =>
    jfetch(`${base}/enterprises/${enterpriseId}/strategy/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compliance_year: complianceYear }),
    }),
  listStrategyRuns: (enterpriseId) => jfetch(`${base}/enterprises/${enterpriseId}/strategy/runs`),

  // alerts
  listAlerts: ({ enterpriseId = '', unackedOnly = false } = {}) =>
    jfetch(`${base}/alerts${qs({ enterprise_id: enterpriseId, unacked_only: unackedOnly || undefined })}`),
  ackAlert: (alertId) => jfetch(`${base}/alerts/${alertId}/ack`, { method: 'POST' }),

  // import
  async downloadImportTemplate(enterpriseId) {
    const blob = await jblob(`${base}/enterprises/${enterpriseId}/import/template`)
    downloadBlob(blob, 'carbon_import_template.xlsx')
  },
  async importEnterpriseExcel(enterpriseId, file) {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${base}/enterprises/${enterpriseId}/import`, {
      method: 'POST',
      body: fd,
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json?.detail || json?.message || t('导入失败'))
    return json
  },
  // 策略报告下载
  async downloadStrategyRun(enterpriseId, runId) {
    const blob = await jblob(`${base}/enterprises/${enterpriseId}/strategy/runs/${runId}/download`)
    downloadBlob(blob, `strategy_${String(runId).slice(0, 8)}.md`)
  },
}
