// 碳资产助手 API：报告生成 / 任务管理 / 列表 / 详情 / 下载 / HTML 查看
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

export const carbonAssistantApi = {
  // 提交碳资产报告生成任务（report_type: market_brief/policy_digest/compliance_analysis）
  submitReport: (payload) => jfetch(base + '/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }),

  // 获取报告列表（支持 keyword / report_type / offset / limit）
  listReports: (query = {}) => {
    const qs = new URLSearchParams()
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v)
    })
    return jfetch(base + '/reports?' + qs.toString())
  },

  // 获取单份报告（Markdown 正文）
  getReport: (id) => jfetch(`${base}/reports/${id}`),

  // 报告 HTML 阅读页地址（新窗口打开）
  viewReportUrl: (id) => `${base}/reports/${id}/view`,

  // 查询任务状态（含进度）
  getTask: (id) => jfetch(`${base}/tasks/${id}`),

  // 取消任务
  cancelTask: (id) => jfetch(`${base}/tasks/${id}/cancel`, { method: 'POST' }),

  // 删除报告
  deleteReport: (id) => jfetch(`${base}/reports/${id}`, { method: 'DELETE' }),
}
