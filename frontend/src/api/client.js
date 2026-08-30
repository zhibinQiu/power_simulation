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
  // 实时数据源状态（MQTT 连接状态 / 订阅主题 / 最近消息）
  realtimeSource: () => jget('/realtime/source'),
  // 平台激活：查询激活状态 / 提交激活码激活
  licenseStatus: () => jget('/license/status'),
  licenseActivate: (code) => jpost('/license/activate', { code }),
  // 工况数据分析：多设备时间序列聚类（devices: [{id, label?, unit?, series:[{t,v}]}], k?）
  clusterDevices: (devices, k = null) =>
    jpost('/cluster', k ? { devices, k } : { devices }),
  // 云端设备 <-> 仿真设备实例关联：仅关联后云端读数才同步到对应设备实例
  boxLinks: () => jget('/realtime/link'),
  linkMqttDevice: (cloudId, localId, factor = 1) => jput('/realtime/link', { cloud_id: cloudId, local_id: localId, factor }),
  unlinkMqttDevice: (cloudId) =>
    fetch(BASE + '/realtime/link/' + encodeURIComponent(cloudId), { method: 'DELETE' }).then(r => r.json()),
  // 能碳一体机管理台（云端 K3s/KubeEdge 管理、设备 CRUD、盒子接入）
  boxOverview: () => jget('/box/overview'),
  boxDevices: () => jget('/box/devices'),
  boxCreateDevice: (payload) => jpost('/box/devices', payload),
  boxUpdateModel: (payload) => jpost('/box/models', payload),
  boxDeleteDevice: (kind, name, namespace = 'default', cloud = false, local = true) =>
    jpost('/box/devices/delete', { kind, name, namespace, cloud, local }),
  boxApplyDevices: (name = '', dryRun = false, modelName = '') =>
    jpost('/box/devices/apply', { name, dry_run: dryRun, model_name: modelName }),
  boxCloudConfig: () => jget('/box/cloud/config'),
  boxCloudConfigSave: (payload) => jpost('/box/cloud/config', payload),
  boxCloudAgentStatus: () => jget('/box/cloud/agent/status'),
  boxCloudRestart: (payload) => jpost('/box/cloud/restart', payload),
  boxCloudLogs: () => jget('/box/cloud/logs'),
  cloudTsdbHistory: (params = {}) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') q.set(k, v)
    }
    return jget('/box/cloud/tsdb/history?' + q.toString())
  },
  boxDevicesRealtime: () => jget('/box/devices/realtime'),
  boxCloudCrd: (force = false) => jget('/box/devices/cloud' + (force ? '?force=true' : '')),
  boxIngestDeviceValue: (device, namespace, property, value) =>
    jpost('/box/devices/realtime/ingest', { device, namespace, property, value }),
  boxOnboard: (hostname, cloudIP, boxIP) =>
    jpost('/box/nodes/onboard', { hostname, cloudIP, boxIP }),
  // 一键接入：下载自解压脚本（base64）/ 远程一键接入（云端 agent SSH 推送执行）
  boxOnboardScript: () => jget('/box/nodes/onboard/script'),
  boxOnboardRemote: (payload) => jpost('/box/nodes/onboard/remote', payload),
  // GitHub 托管：盒子现场一条 curl 命令拉取接入资产（部署包/证书/token 均托管在用户仓库）
  boxGithubConfig: () => jget('/box/onboard/github-config'),
  boxGithubConfigSave: (payload) => jpost('/box/onboard/github-config', payload),
  boxGithubPush: (cloudIP) => jpost('/box/onboard/github-push', { cloudIP }),
  boxConfigExport: (cloudIP, hostname) => jget(`/box/nodes/onboard/config-export?cloudIP=${encodeURIComponent(cloudIP)}&hostname=${encodeURIComponent(hostname)}`),
  boxStats: () => jget('/box/stats'),
  boxPublish: (topic, payload) => jpost('/box/publish', { topic, payload }),
  // 盒子连接配置（IP/SSH 凭据）与云端应用部署
  boxEdgeConfig: () => jget('/box/edge/config'),
  boxEdgeConfigSave: (payload) => jpost('/box/edge/config', payload),
  boxEdgeCheck: (host, port = 22) => jpost('/box/edge/check', { host, port }),
  boxAppCmd: (payload) => jpost('/box/apps/cmd', payload),
  boxApps: (box = 'nt001') => jget('/box/apps?box=' + encodeURIComponent(box)),
  // 云端 Broker 配置（前端配置化：能碳一体机管理 -> 总览 -> 云端数据链路「配置」，免手工编辑 mqtt.yaml）
  boxConfig: () => jget('/box/config'),
  boxConfigSave: (payload) => jpost('/box/config', payload),
  // 云端实时推送 WebSocket（/api/ws/cloud）：云端 agent 经 MQTT cloud/# 推送的概览/CRD/日志，平台后端实时转发
  openCloudFeed,
  // 知识库（LLM-WIKI 式：多级文件夹 + 文档上传解析，无需权限）
  kbTree: () => jget('/knowledge/tree'),
  kbCreateFolder: (name, parent = '') => jpost('/knowledge/folder', { name, parent }),
  kbRenameFolder: (path, name) => jput('/knowledge/folder', { path, name }),
  kbDeleteFolder: (path) =>
    fetch(BASE + '/knowledge/folder?path=' + encodeURIComponent(path), { method: 'DELETE' }).then(r => r.json()),
  kbUpload: (file, folder = '') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('folder', folder)
    return fetch(BASE + '/knowledge/upload', { method: 'POST', body: fd }).then(r => r.json())
  },
  kbRenameDoc: (id, name) => jput('/knowledge/doc/' + id, { name }),
  kbDeleteDoc: (id) => fetch(BASE + '/knowledge/doc/' + id, { method: 'DELETE' }).then(r => r.json()),
  kbDocContent: (id) => jget('/knowledge/doc/' + id + '/content'),
  kbRawUrl: (id) => BASE + '/knowledge/doc/' + id + '/raw',
  kbSearch: (q) => jget('/knowledge/search?q=' + encodeURIComponent(q)),
  // ---- 通用方法（管理界面用） ----
  get: jget,
  post: jpost,
  put: jput,
  del: (path) => fetch(BASE + path, { method: 'DELETE' }).then(r => r.json()),
  upload: (path, formData) =>
    fetch(BASE + path, { method: 'POST', body: formData }).then(r => r.json()),
}

// WebSocket 遥测（url 省略则连接平台实时数据 /api/ws/feed，数据来自 MQTT 订阅）
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

// 云端实时推送 WebSocket（/api/ws/cloud）：云端 agent 经 MQTT cloud/# 推送的
// 概览/CRD/日志，由平台后端实时转发。连接后先收 snapshot，之后收 state/crds/logs 增量。
export function openCloudFeed(onMessage, onStatus) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/ws/cloud`)
  ws.onopen = () => onStatus && onStatus('open')
  ws.onclose = () => onStatus && onStatus('closed')
  ws.onerror = () => onStatus && onStatus('error')
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch (_) {}
  }
  return ws
}
