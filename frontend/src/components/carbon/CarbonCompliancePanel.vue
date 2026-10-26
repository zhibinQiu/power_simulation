<script setup>
import { ref, reactive, onMounted, computed, nextTick, watch } from 'vue'
import { carbonComplianceApi as api } from '../../api/carbonCompliance.js'
import { t } from '../../i18n'

// ---------------- 状态 ----------------
const tab = ref('emissions') // emissions|forecasts|cea|ccer|green|strategy|alerts
const enterprises = ref([])
const selectedId = ref('')
const meta = ref({ industries: [], risk_profiles: [] })
const msg = ref('')
const errMsg = ref('')

const emissions = ref([])
const forecasts = ref([])
const ceaRows = ref([])
const ccerRows = ref([])
const ceaTrades = ref([])
const ccerTrades = ref([])
// 流水接口的失败原因（空串 = 正常）。后端缺 GET 路由时不能再静默成空表
const tradeErr = ref('')
const greenPower = ref([])
const greenCerts = ref([])
const runs = ref([])
const alerts = ref([])
const lastRun = ref(null)
const running = ref(false)

const selected = computed(() => enterprises.value.find(e => e.id === selectedId.value) || null)
const industryLabel = (k) => (meta.value.industries.find(i => i.value === k) || {}).label || k
const riskLabel = (k) => (meta.value.risk_profiles.find(i => i.value === k) || {}).label || k

async function flashOk(t) { msg.value = t; setTimeout(() => { msg.value = '' }, 2500) }
async function flashErr(e) { errMsg.value = e?.message || String(e); setTimeout(() => { errMsg.value = '' }, 4000) }

async function loadMeta() {
  try { meta.value = await api.fetchMeta() } catch (e) { console.warn(e) }
}
async function loadEnterprises() {
  try {
    enterprises.value = await api.listEnterprises()
    if (!selectedId.value || !enterprises.value.find(e => e.id === selectedId.value)) {
      selectedId.value = enterprises.value[0]?.id || ''
    }
    if (selectedId.value) await loadSelected()
  } catch (e) { flashErr(e) }
}
async function loadSelected() {
  if (!selectedId.value) return
  const id = selectedId.value
  try {
    const [em, fc, cea, ccer, gp, gc, rn, al] = await Promise.all([
      api.listEmissions(id), api.listForecasts(id), api.listCea(id),
      api.listCcer(id), api.listGreenPower(id), api.listGreenCerts(id),
      api.listStrategyRuns(id).catch(() => []),
      api.listAlerts({ enterpriseId: id }),
    ])
    emissions.value = em; forecasts.value = fc; ceaRows.value = cea
    ccerRows.value = ccer; greenPower.value = gp; greenCerts.value = gc
    runs.value = rn
    alerts.value = al
  } catch (e) { flashErr(e) }
  loadTrades()
}
// 交易流水：CEA / CCER 各自独立，互不混流。
// 注意：以前这里一律 .catch(() => [])，后端缺 GET 接口时会静默成空列表 ——
// 用户看到的是「登记了但没显示、指标也不动」，完全无法判断是没写进去还是读不出来。
// 现在把失败原因留下来，在流水区顶部明确提示（tradeErr 为空即正常）。
async function loadTrades() {
  const id = selectedId.value
  if (!id) { ceaTrades.value = []; ccerTrades.value = []; tradeErr.value = ''; return }
  const [cea, ccer] = await Promise.all([
    api.listCeaTrades(id).catch((e) => e),
    api.listCcerTrades(id).catch((e) => e),
  ])
  if (id !== selectedId.value) return // 快速切企业时丢弃过期响应
  const bad = [cea, ccer].find((v) => !Array.isArray(v))
  tradeErr.value = bad ? String(apiErrText(bad)) : ''
  ceaTrades.value = Array.isArray(cea) ? cea : []
  ccerTrades.value = Array.isArray(ccer) ? ccer : []
}
function apiErrText(e) {
  if (!e) return ''
  return e.message || e.detail || String(e)
}
function tradeSum(rows) {
  let buy = 0; let sell = 0
  for (const r of rows) {
    const q = Number(r.qty) || 0
    if (r.side === 'sell') sell += q; else buy += q
  }
  return { buy, sell, net: sell - buy }
}
// 流水也跟随年度作用域：否则切到某一年后，表格按年过滤而右上汇总仍是全量，两个数对不上
const ceaScopedTrades = computed(() => (ceaScopeYear.value === ''
  ? ceaTrades.value
  : ceaTrades.value.filter(r => Number(ceaTradeYearOf(r)) === Number(ceaScopeYear.value))))
const ceaTradeSum = computed(() => tradeSum(ceaScopedTrades.value))
const ccerTradeSum = computed(() => tradeSum(ccerTrades.value))

// ---------------- CCER 口径：当前持仓 = 台账基准量 + 买入 − 卖出 ----------------
// 与 CEA「可用配额 = 配额基准 − 卖出 + 买入」同构：持仓表「数量」是手填的基准量，
// 交易登记（买入/卖出）按「项目类型」归集后，增/减到对应类型的持仓上，使流水与持仓联动。
function ccerTradeTypeOf(r) {
  return r && r.project_type ? String(r.project_type) : 'general'
}
// 按项目类型归集买卖量：{ [project_type]: { buy, sell } }
const ccerTradeByType = computed(() => {
  const map = {}
  for (const r of ccerTrades.value) {
    const t = ccerTradeTypeOf(r)
    const q = Number(r.qty) || 0
    const cur = map[t] || (map[t] = { buy: 0, sell: 0, buyAmt: 0 })
    if (r.side === 'sell') cur.sell += q
    else { cur.buy += q; cur.buyAmt += q * (Number(r.price) || 0) }
  }
  return map
})
function ccerBuyOf(row) {
  const agg = ccerTradeByType.value[ccerTradeTypeOf(row)]
  return agg ? agg.buy : 0
}
function ccerSellOf(row) {
  const agg = ccerTradeByType.value[ccerTradeTypeOf(row)]
  return agg ? agg.sell : 0
}
// 当前持仓 = 基准量 + 买入 − 卖出
function ccerCurrentOf(row) {
  const base = Number(row.qty) || 0
  return base + ccerBuyOf(row) - ccerSellOf(row)
}
// 当前成本 = (签发量 × 手填成本 + 买入金额) / (签发量 + 买入量)：买入按流水单价加权摊入成本
function ccerCostOf(row) {
  const base = Number(row.qty) || 0
  const buy = ccerBuyOf(row)
  const agg = ccerTradeByType.value[ccerTradeTypeOf(row)]
  const buyAmt = agg ? agg.buyAmt : 0
  const cost0 = Number(row.cost) || 0
  const denom = base + buy
  if (denom <= 0) return 0
  return (base * cost0 + buyAmt) / denom
}
// 悬空流水：project_type 没有对应持仓行的流水笔数（卖出/买入都不会体现在任何一行持仓上）
const ccerOrphanTrades = computed(() => {
  const types = new Set(ccerRows.value.map(r => ccerTradeTypeOf(r)))
  return ccerTrades.value.filter(r => !types.has(ccerTradeTypeOf(r)))
})

// ---------------- CEA 口径：可用 = 配额基准 − 卖出 + 买入 ----------------
// 配额基准 = max(免费配额, 预分配) + 结转量；卖出/买入以「交易流水」为准，
// 按归属年度（vintage_year，缺省回退 traded_at 的年份）归集到对应配额年度；
// 该年度一条流水都没有时，卖出回退到持仓台账手填的 net_sell_qty、买入回退到 buy_qty（兼容老数据）。
function tradeYear(r) {
  const m = String(r && r.traded_at ? r.traded_at : '').match(/(\d{4})/)
  return m ? Number(m[1]) : null
}
// 归属年度：优先取流水自带的 vintage_year（登记时选定），
// 老数据没有这个字段时退回交易发生年，保证历史流水不会凭空消失
function ceaTradeYearOf(r) {
  const vy = r ? r.vintage_year : null
  if (vy !== null && vy !== undefined && vy !== '') return Number(vy)
  return tradeYear(r)
}
const ceaTradeByYear = computed(() => {
  const map = {}
  for (const r of ceaTrades.value) {
    const y = ceaTradeYearOf(r)
    if (y === null) continue
    const q = Number(r.qty) || 0
    const cur = map[y] || (map[y] = { buy: 0, sell: 0, buyAmt: 0, count: 0 })
    if (r.side === 'sell') cur.sell += q
    else { cur.buy += q; cur.buyAmt += q * (Number(r.price) || 0) }
    cur.count += 1
  }
  return map
})
// 配额年度作用域：'' = 全部年度（跨年合计），否则只看该年。默认全部，保持与其它三张卡同口径
const ceaScopeYear = ref('')
const ceaYears = computed(() => {
  const ys = [...new Set(ceaRows.value.map(r => Number(r.vintage_year)).filter(y => !!y))].sort((a, b) => b - a)
  // 还没有任何持仓时也给出当年，避免「配额年度」下拉是空的、登记时无从选择
  return ys.length ? ys : [new Date().getFullYear()]
})
// CCER 交易登记的「登记年份」候选：持仓签发年 + 当前年（倒序去重），保证下拉非空
const ccerYears = computed(() => {
  const ys = [...new Set(ccerRows.value.map(r => Number(r.issue_year)).filter(y => !!y))]
  ys.push(new Date().getFullYear())
  return [...new Set(ys)].sort((a, b) => b - a)
})
const ceaScopedRows = computed(() => (ceaScopeYear.value === ''
  ? ceaRows.value
  : ceaRows.value.filter(r => Number(r.vintage_year) === Number(ceaScopeYear.value))))
// 归属年度在该企业没有持仓台账的流水：卖出/买入不会落到任何一行，卡片也不会动。
// 旧版后端不认识 vintage_year（登记时被丢弃），只能按交易发生年归档，最容易落进这一类，
// 所以要把这类「悬空流水」显式提示出来，否则用户会以为登记没生效。
const ceaOrphanTrades = computed(() => {
  const ys = new Set(ceaRows.value.map(r => Number(r.vintage_year)).filter(Boolean))
  return ceaTrades.value.filter(r => {
    const y = Number(ceaTradeYearOf(r))
    return !y || !ys.has(y)
  })
})
// 返回 { sell, buy, fromTrades, net }：卖出/买入分开呈现，net 供可用量计算；
// fromTrades=false 表示当年无流水，卖出回退到台账手填的 net_sell_qty、买入回退到 buy_qty
function ceaSellBuyOf(row) {
  const agg = ceaTradeByYear.value[Number(row.vintage_year)]
  if (agg && agg.count) return { sell: agg.sell, buy: agg.buy, net: agg.sell - agg.buy, fromTrades: true }
  const sell = Number(row.net_sell_qty) || 0
  const buy = Number(row.buy_qty) || 0
  return { sell, buy, net: sell - buy, fromTrades: false }
}
function ceaNetSellOf(row) {
  return { qty: ceaSellBuyOf(row).net, fromTrades: ceaSellBuyOf(row).fromTrades }
}
// 预分配（estimated_free_quota）是「替代值」不是叠加值：>0 时与免费配额取 max，与后端 free_cea 一致
function ceaUsableOf(row) {
  const free = Number(row.free_quota) || 0
  const carry = Number(row.carry_forward_qty) || 0
  const est = Number(row.estimated_free_quota) || 0
  const base = Math.max(free + carry, est > 0 ? est + carry : 0)
  return base - ceaNetSellOf(row).qty
}
// 当前平均成本 = (买入前可用量 × 手填成本 + 买入金额) / (买入前可用量 + 买入量)：买入按流水单价加权摊入
function ceaCostOf(row) {
  const buy = ceaSellBuyOf(row).buy
  const agg = ceaTradeByYear.value[Number(row.vintage_year)]
  const buyAmt = agg ? agg.buyAmt : 0
  const cost0 = Number(row.avg_cost) || 0
  const baseBeforeBuy = ceaUsableOf(row) - buy  // 不含买入的可用量（买入前基数）
  const denom = baseBeforeBuy + buy
  if (denom <= 0) return 0
  return (baseBeforeBuy * cost0 + buyAmt) / denom
}
const ceaScopedUsable = computed(() => ceaScopedRows.value.reduce((s, r) => s + ceaUsableOf(r), 0))
const ceaScopedFree = computed(() => ceaScopedRows.value.reduce((s, r) => s + (Number(r.free_quota) || 0), 0))
const ceaScopedCarry = computed(() => ceaScopedRows.value.reduce((s, r) => s + (Number(r.carry_forward_qty) || 0), 0))
const ceaScopedSell = computed(() => ceaScopedRows.value.reduce((s, r) => s + ceaSellBuyOf(r).sell, 0))
const ceaScopedBuy = computed(() => ceaScopedRows.value.reduce((s, r) => s + ceaSellBuyOf(r).buy, 0))
// 配额基准 = max(免费配额, 预分配) + 结转量，是可用量的「毛量」（未扣买卖）
const ceaScopedBase = computed(() => ceaScopedRows.value.reduce((s, r) => {
  const free = Number(r.free_quota) || 0
  const carry = Number(r.carry_forward_qty) || 0
  const est = Number(r.estimated_free_quota) || 0
  return s + Math.max(free + carry, est > 0 ? est + carry : 0)
}, 0))
const ceaScopedEst = computed(() => ceaScopedRows.value.reduce((s, r) => s + (Number(r.estimated_free_quota) || 0), 0))
const ceaScopedCost = computed(() => {
  // 平均成本按「可用量」加权：可用量为 0 的行不参与，避免 0 成本把整体拉平
  let q = 0
  let c = 0
  for (const r of ceaScopedRows.value) {
    const w = Math.max(0, ceaUsableOf(r))
    q += w
    c += w * (Number(r.avg_cost) || 0)
  }
  return q > 0 ? c / q : 0
})
const ceaScopeLabel = computed(() => (ceaScopeYear.value === '' ? t('全部年度') : String(ceaScopeYear.value)))
const ceaHint = computed(() => t('可用 {usable} 万吨 = 配额基准 {base}（max(免费配额 {free}, 预分配 {est}) + 结转 {carry}）− 卖出 {sell} + 买入 {buy}', {
  usable: ceaScopedUsable.value.toFixed(1),
  base: ceaScopedBase.value.toFixed(1),
  free: ceaScopedFree.value.toFixed(1),
  est: ceaScopedEst.value.toFixed(1),
  carry: ceaScopedCarry.value.toFixed(1),
  sell: ceaScopedSell.value.toFixed(1),
  buy: ceaScopedBuy.value.toFixed(1),
}))
// 0 / 空 一律显示「—」，避免「没填」被当成真实的 0
const numOrDash = (v) => (v === null || v === undefined || Number(v) === 0 ? '—' : Number(v).toFixed(1))
function sellTextOf(r) {
  const v = ceaSellBuyOf(r)
  return v.sell === 0 && !v.fromTrades ? '—' : v.sell.toFixed(1)
}
function buyTextOf(r) {
  return numOrDash(ceaSellBuyOf(r).buy)
}
async function delCeaTrade(row) {
  if (!selectedId.value || !row.id) return
  const side = row.side === 'buy' ? t('买入') : t('卖出')
  if (!confirm(t('删除这条 CEA 交易记录（{side} {qty} 万吨）？删除后持仓表的卖出/买入与可用配额会同步重算。', { side, qty: Number(row.qty || 0).toFixed(2) }))) return
  try {
    await api.deleteCeaTrade(selectedId.value, row.id)
    await loadTrades()
    flashOk(t('交易记录已删除'))
  } catch (e) { flashErr(e) }
}
const fmtTime = (s) => String(s || '').slice(0, 16).replace('T', ' ')
function loadAll() { loadMeta(); loadEnterprises() }
onMounted(loadAll)
// 排放台账的新增/编辑弹窗只能通过右上角 ✕ 或「取消」关闭：
// 点遮罩空白处、按 Esc 都不关，避免填一半手滑丢掉已输入的数据

defineExpose({ loadAll })

// ---------------- 企业 CRUD ----------------
const entForm = reactive({ name: '', uscc: '', industry: 'power', market_start_year: new Date().getFullYear() - 1, risk_profile: 'balanced', annual_budget_cap: 0, single_trade_limit: 0 })
const showEntForm = ref(false)
async function createEnterprise() {
  if (!entForm.name.trim()) return flashErr(new Error(t('请填写企业名称')))
  try {
    await api.createEnterprise({ ...entForm })
    showEntForm.value = false
    entForm.name = ''; entForm.uscc = ''
    await loadEnterprises()
    flashOk(t('企业已创建'))
  } catch (e) { flashErr(e) }
}
async function deleteEnterprise() {
  if (!selectedId.value) return
  if (!confirm(t('确认删除企业「{name}」及其全部台账？', { name: selected.value?.name || selectedId.value }))) return
  try {
    await api.deleteEnterprise(selectedId.value)
    selectedId.value = ''
    await loadEnterprises()
    flashOk(t('企业已删除'))
  } catch (e) { flashErr(e) }
}
async function updateEnterprise(patch) {
  if (!selectedId.value) return
  try {
    await api.updateEnterprise(selectedId.value, patch)
    await loadEnterprises()
    flashOk(t('企业已更新'))
  } catch (e) { flashErr(e) }
}

// ---------------- 排放台账 ----------------
// 录入统一走弹窗：新增 / 编辑共用同一个表单（年份是该企业的台账主键）
const emForm = reactive({ year: new Date().getFullYear(), verified_total: 0, scope1_combustion: 0, scope1_process: 0, scope2_power: 0, purchased_mwh: 0, historical_gap: null, ccer_used: 0, monthly_detail: {} })
const emDialogOpen = ref(false)
const emEditingYear = ref(null) // null 表示新增
const emSaving = ref(false)
const emYearInput = ref(null)
const emIsEdit = computed(() => emEditingYear.value !== null)
function openEmDialog(row = null) {
  if (row) {
    emEditingYear.value = Number(row.year)
    Object.assign(emForm, {
      year: Number(row.year),
      verified_total: Number(row.verified_total || 0),
      scope1_combustion: Number(row.scope1_combustion || 0),
      scope1_process: Number(row.scope1_process || 0),
      scope2_power: Number(row.scope2_power || 0),
      purchased_mwh: Number(row.purchased_mwh || 0),
      historical_gap: row.historical_gap ?? null,
      ccer_used: Number(row.ccer_used || 0),
      // 弹窗里不编辑月度明细，但必须原样带回去：后端 model_dump 总会带上该字段，
      // 漏了就会把已有月度数据覆盖成空对象
      monthly_detail: row.monthly_detail || {},
    })
  } else {
    emEditingYear.value = null
    const thisYear = new Date().getFullYear()
    const maxYear = emissions.value.reduce((m, r) => Math.max(m, Number(r.year) || 0), 0)
    Object.assign(emForm, {
      year: maxYear >= thisYear ? maxYear + 1 : thisYear,
      verified_total: 0, scope1_combustion: 0, scope1_process: 0,
      scope2_power: 0, purchased_mwh: 0, historical_gap: null, ccer_used: 0, monthly_detail: {},
    })
  }
  emDialogOpen.value = true
  nextTick(() => emYearInput.value?.focus())
}
function closeEmDialog() { emDialogOpen.value = false }
async function saveEmission() {
  if (!selectedId.value) return flashErr(new Error(t('请先选择企业')))
  if (!Number(emForm.year)) return flashErr(new Error(t('请填写年份')))
  emSaving.value = true
  const wasEdit = emIsEdit.value
  try {
    await api.upsertEmission(selectedId.value, { ...emForm })
    emDialogOpen.value = false
    await loadSelected()
    flashOk(wasEdit ? t('排放记录已更新') : t('排放记录已新增'))
  } catch (e) { flashErr(e) } finally { emSaving.value = false }
}
// CEA / CCER 的持仓录入已与排放台账统一成「右上角新增 + 行内编辑 + 弹窗录入」（见下方 dlg* 系列）；
// 这个开关现在只负责展开/收起该页的「交易登记」表单（买卖流水仍走内联表单，不塞进弹窗）
const editOpen = ref({ cea: false, ccer: false })
const editTabs = ['cea', 'ccer']
function toggleEdit(key) {
  editOpen.value[key] = !editOpen.value[key]
  if (!editOpen.value[key]) return
  nextTick(() => {
    const el = document.querySelector(
      `.tab-body[data-tab="${key}"] .entry input, .tab-body[data-tab="${key}"] .entry select`
    )
    el?.focus()
  })
}
async function delEmission(row) {
  if (!confirm(t('删除 {year} 年排放记录？', { year: row.year }))) return
  try { await api.deleteEmission(selectedId.value, row.year); await loadSelected(); flashOk(t('排放记录已删除')) } catch (e) { flashErr(e) }
}
// 排放预测按 id 删：老数据可能有「同年不同 id」的脏记录，按年份删会一次抹掉多行
async function delForecast(row) {
  if (!selectedId.value || !row.id) return
  if (!confirm(t('删除 {year} 年排放预测？', { year: row.year }))) return
  try { await api.deleteForecast(selectedId.value, row.id); await loadSelected(); flashOk(t('排放预测已删除')) } catch (e) { flashErr(e) }
}

// ---------------- 通用录入弹窗（CEA / CCER 持仓 / 排放预测 / 绿电 / 绿证） ----------------
// 与排放台账同一套交互：入口是「+ 新增」和行内「编辑」，填报在弹窗里完成，只能由 ✕ / 取消 关闭
const dlgKind = ref('') // '' | 'cea' | 'ccer' | 'forecast' | 'greenPower' | 'greenCert'
const dlgEditingKey = ref(null) // 预测/绿电/CEA 按年份判编辑，绿证/CCER 按 id
const dlgSaving = ref(false)
const dlgIsEdit = computed(() => dlgEditingKey.value !== null)
// 年份是预测/绿电/CEA 持仓的建档主键，编辑时锁住；绿证、CCER 按批次建档，年份可以改
const dlgYearLocked = computed(() => dlgIsEdit.value && ['forecast', 'greenPower', 'cea'].includes(dlgKind.value))
const dlgMeta = {
  cea: {
    add: '新增 CEA 持仓', edit: '编辑 CEA 持仓',
    tipAdd: 'CEA 持仓按配额年份建档，同一企业同一年份只保留一条记录。',
    tipEdit: 'CEA 持仓按配额年份建档，编辑时年份不可修改；如需换年份请先删掉旧记录。',
    okAdd: 'CEA 持仓已新增', okEdit: 'CEA 持仓已更新',
  },
  ccer: {
    add: '新增 CCER 持仓', edit: '编辑 CCER 持仓',
    tipAdd: 'CCER 按批次建档，同一企业同一年份可以有多条记录（不同项目类型或批次）。',
    tipEdit: 'CCER 按批次建档，编辑时改年份不影响其它批次。',
    okAdd: 'CCER 持仓已新增', okEdit: 'CCER 持仓已更新',
  },
  forecast: {
    add: '新增排放预测', edit: '编辑排放预测',
    tipAdd: '同一企业同一年份只保留一条预测，重复新增会覆盖该年度数据。',
    tipEdit: '排放预测按年份建档，编辑时年份不可修改；如需换年份请先删掉旧记录。',
    okAdd: '排放预测已新增', okEdit: '排放预测已更新',
  },
  greenPower: {
    add: '新增绿电记录', edit: '编辑绿电记录',
    tipAdd: '绿电按年份建档，同一企业同一年份只保留一条记录。',
    tipEdit: '绿电按年份建档，编辑时年份不可修改；如需换年份请重新新增。',
    okAdd: '绿电记录已新增', okEdit: '绿电记录已更新',
  },
  greenCert: {
    add: '新增绿证记录', edit: '编辑绿证记录',
    tipAdd: '绿证按批次建档，同一企业同一年份可以有多条记录。',
    tipEdit: '绿证按批次建档，年份可以修改，不影响其它批次。',
    okAdd: '绿证记录已新增', okEdit: '绿证记录已更新',
  },
}
const dlgTitle = computed(() => {
  const m = dlgMeta[dlgKind.value]
  return m ? t(dlgIsEdit.value ? m.edit : m.add) : ''
})
const dlgTip = computed(() => {
  const m = dlgMeta[dlgKind.value]
  return m ? t(dlgIsEdit.value ? m.tipEdit : m.tipAdd) : ''
})

// ---------------- 预测 ----------------
const fcForm = reactive({ year: new Date().getFullYear() + 1, forecast_total: 0, capacity_plan: '', production_plan: '', abatement_projects: [] })

// ---------------- 绿电 / 绿证 ----------------
const gpForm = reactive({ year: new Date().getFullYear(), market_green_mwh: 0, self_gen_mwh: 0, premium_per_mwh: 0, contract_ref: '' })
const gcForm = reactive({ id: null, year: new Date().getFullYear(), qty: 0, unit_price: 0, retired: false, ren_weight_target: null })

// 新增时默认年份取「台账最大年份 + 1」和当年中的较大值，避免一开窗就撞已有年份
function nextYear(rows) {
  const thisYear = new Date().getFullYear()
  const maxYear = rows.reduce((m, r) => Math.max(m, Number(r.year) || 0), 0)
  return maxYear >= thisYear ? maxYear + 1 : thisYear
}
// CEA 持仓的年份字段叫 vintage_year（配额年份），默认值口径同上
function nextVintageYear(rows) {
  const thisYear = new Date().getFullYear()
  const maxYear = rows.reduce((m, r) => Math.max(m, Number(r.vintage_year) || 0), 0)
  return maxYear >= thisYear ? maxYear + 1 : thisYear
}
function openDlg(kind, row = null) {
  dlgKind.value = kind
  if (kind === 'cea') {
    dlgEditingKey.value = row ? Number(row.vintage_year) : null
    Object.assign(ceaForm, row ? {
      vintage_year: Number(row.vintage_year),
      free_quota: Number(row.free_quota || 0),
      carry_forward_qty: Number(row.carry_forward_qty || 0),
      estimated_free_quota: Number(row.estimated_free_quota || 0),
      net_sell_qty: Number(row.net_sell_qty || 0),
      buy_qty: Number(row.buy_qty || 0),
      avg_cost: Number(row.avg_cost || 0),
    } : {
      vintage_year: nextVintageYear(ceaRows.value),
      free_quota: 0, carry_forward_qty: 0, estimated_free_quota: 0,
      net_sell_qty: 0, buy_qty: 0, avg_cost: 0,
    })
  } else if (kind === 'ccer') {
    // CCER 按 id 判编辑（同年份允许多批次），年份可改
    dlgEditingKey.value = row ? String(row.id) : null
    Object.assign(ccerForm, row ? {
      id: row.id,
      project_type: row.project_type || 'forest',
      issue_year: Number(row.issue_year) || new Date().getFullYear(),
      expire_at: row.expire_at || '',
      qty: Number(row.qty || 0),
      cost: Number(row.cost || 0),
      eligible_qty: row.eligible_qty === null || row.eligible_qty === undefined ? null : Number(row.eligible_qty),
      linked_green_cert: !!row.linked_green_cert,
    } : {
      id: null, project_type: 'forest',
      issue_year: nextYear((ccerRows.value || []).map(r => ({ year: r.issue_year }))),
      expire_at: '', qty: 0, cost: 0, eligible_qty: null, linked_green_cert: false,
    })
  } else if (kind === 'forecast') {
    dlgEditingKey.value = row ? Number(row.year) : null
    Object.assign(fcForm, row ? {
      year: Number(row.year),
      forecast_total: Number(row.forecast_total || 0),
      capacity_plan: row.capacity_plan || '',
      production_plan: row.production_plan || '',
      // 弹窗不编辑减排项目清单，但必须原样带回：后端会用传上去的值整体覆盖
      abatement_projects: row.abatement_projects || [],
    } : {
      year: nextYear(forecasts.value), forecast_total: 0,
      capacity_plan: '', production_plan: '', abatement_projects: [],
    })
  } else if (kind === 'greenPower') {
    dlgEditingKey.value = row ? Number(row.year) : null
    Object.assign(gpForm, row ? {
      year: Number(row.year),
      market_green_mwh: Number(row.market_green_mwh || 0),
      self_gen_mwh: Number(row.self_gen_mwh || 0),
      premium_per_mwh: Number(row.premium_per_mwh || 0),
      contract_ref: row.contract_ref || '',
    } : {
      year: nextYear(greenPower.value), market_green_mwh: 0, self_gen_mwh: 0, premium_per_mwh: 0, contract_ref: '',
    })
  } else if (kind === 'greenCert') {
    dlgEditingKey.value = row ? String(row.id) : null
    Object.assign(gcForm, row ? {
      id: row.id, year: Number(row.year),
      qty: Number(row.qty || 0), unit_price: Number(row.unit_price || 0),
      retired: !!row.retired,
      // 可再生能源权重目标当前不在弹窗里编辑，但要原样带回，否则会被覆盖成 null
      ren_weight_target: row.ren_weight_target ?? null,
    } : {
      id: null, year: nextYear(greenCerts.value), qty: 0, unit_price: 0, retired: false, ren_weight_target: null,
    })
  }
}
function closeDlg() { dlgKind.value = '' }
async function saveDlg() {
  if (!selectedId.value) return flashErr(new Error(t('请先选择企业')))
  const kind = dlgKind.value
  const wasEdit = dlgIsEdit.value
  const year = kind === 'cea' ? ceaForm.vintage_year
    : kind === 'ccer' ? ccerForm.issue_year
      : kind === 'forecast' ? fcForm.year
        : kind === 'greenPower' ? gpForm.year : gcForm.year
  if (!Number(year)) return flashErr(new Error(t('请填写年份')))
  dlgSaving.value = true
  try {
    if (kind === 'cea') {
      await api.upsertCea(selectedId.value, { ...ceaForm })
    } else if (kind === 'ccer') {
      await api.upsertCcer(selectedId.value, { ...ccerForm })
    } else if (kind === 'forecast') {
      await api.upsertForecast(selectedId.value, { ...fcForm, abatement_projects: (fcForm.abatement_projects || []).filter(Boolean) })
    } else if (kind === 'greenPower') {
      await api.upsertGreenPower(selectedId.value, { ...gpForm })
    } else {
      await api.upsertGreenCert(selectedId.value, { ...gcForm })
    }
    dlgKind.value = ''
    await loadSelected()
    const m = dlgMeta[kind]
    flashOk(t(wasEdit ? m.okEdit : m.okAdd))
  } catch (e) { flashErr(e) } finally { dlgSaving.value = false }
}

// ---------------- CEA 台账 ----------------
// 持仓的新增 / 编辑统一走弹窗（openDlg('cea')），年份 vintage_year 是主键
const ceaForm = reactive({ vintage_year: new Date().getFullYear(), free_quota: 0, carry_forward_qty: 0, net_sell_qty: 0, buy_qty: 0, avg_cost: 0, estimated_free_quota: 0 })
async function delCea(row) {
  if (!confirm(t('删除 {vintage_year} 年度 CEA 持仓？', { vintage_year: row.vintage_year }))) return
  try { await api.deleteCea(selectedId.value, row.vintage_year); await loadSelected() } catch (e) { flashErr(e) }
}
// 交易：CEA / CCER 拆成两套表单，各自登记、各自回读，界面上不再选「交易品种」
// CEA 多一个「配额年度」：成交年份 ≠ 配额年份（2026 年可能卖的是 2025 年度配额），
// 不带这个字段就会把卖出记到错误的年度上，导致持仓表的卖出/买入永远不动
const ceaTradeForm = reactive({ side: 'buy', qty: 1, price: 80, note: '', vintage_year: null })
// 当前交易表单所选配额年度对应的「当前可用配额」：用于卖出时的全量上限校验。
// 可用 = 配额基准(max(免费,预分配)+结转) − 卖出 + 买入，即该年度持仓行 ceaUsableOf 的值；
// 卖出量不能超过这个数（卖出后可用不能为负）。
const ceaTradeAvailable = computed(() => {
  const y = Number(ceaTradeForm.vintage_year)
  if (!y) return null
  const row = ceaRows.value.find(r => Number(r.vintage_year) === y)
  return row ? ceaUsableOf(row) : 0
})
// CCER 的「登记时间」用年份下拉（与 CEA「配额年度」对齐）：只选年份，提交时转成该年 1 月 1 日
const ccerTradeForm = reactive({ side: 'buy', qty: 1, price: 80, note: '', trade_year: new Date().getFullYear(), project_type: 'general' })
// 当前交易表单所选项目类型对应的「可抵扣」（签发量 + 买入 − 卖出）：卖出量不能超过它（卖出后不能为负）。
// 若该类型没有持仓行，返回 0（意味着卖出会立即超限，被拦截）。
const ccerTradeAvailable = computed(() => {
  const t = ccerTradeForm.project_type
  const row = ccerRows.value.find(r => ccerTradeTypeOf(r) === t)
  return row ? ccerCurrentOf(row) : 0
})
// 展开交易登记时把「配额年度」默认设成当前作用域年度（全部年度时取最新台账年度）
// 注意：script 里访问 ref 必须走 .value，写 editOpen.cea 拿到的是 undefined，watch 永远不触发
watch(() => editOpen.value.cea, (open) => {
  if (!open) return
  ceaTradeForm.vintage_year = ceaScopeYear.value !== ''
    ? Number(ceaScopeYear.value)
    : (ceaYears.value[0] || new Date().getFullYear())
})
async function addTrade(kind) {
  if (!selectedId.value) return flashErr(new Error(t('请先选择企业')))
  const isCea = kind === 'cea'
  const form = isCea ? ceaTradeForm : ccerTradeForm
  const fn = isCea ? api.addCeaTrade : api.addCcerTrade
  if (isCea && !Number(form.vintage_year)) return flashErr(new Error(t('请选择这笔交易归属的配额年度')))
  // 卖出上限：卖出量不得超过该配额年度的「当前可用配额」，否则卖出后可用会变负，现实中不可能卖超出持仓
  if (isCea && form.side === 'sell') {
    const avail = ceaTradeAvailable.value
    if (avail !== null && Number(form.qty) > avail) {
      return flashErr(new Error(t('卖出量超过该配额年度当前可用配额（{avail} 万吨），无法登记。', { avail: avail.toFixed(2) })))
    }
  }
  // CCER 卖出上限：卖出量不得超过该项目类型的「可抵扣」（签发量 + 买入 − 卖出）
  if (!isCea && form.side === 'sell') {
    const avail = ccerTradeAvailable.value
    if (Number(form.qty) > avail) {
      return flashErr(new Error(t('卖出量超过该类型当前可抵扣（{avail} 万吨），无法登记。', { avail: avail.toFixed(2) })))
    }
  }
  try {
    // CCER 提交前把「登记年份」转成完整时间串（该年 1 月 1 日 00:00），
    // 保证后端 _norm_trade_at 能按字符串倒序正确排序，而不是拿纯年份和完整时间串混排
    const payload = isCea ? { ...form } : { side: form.side, qty: form.qty, price: form.price, note: form.note, traded_at: `${Number(form.trade_year) || new Date().getFullYear()}-01-01T00:00`, project_type: form.project_type }
    await fn(selectedId.value, payload)
    await loadSelected() // 流水与台账一起回读，避免「流水变了、上面的数没跟上」
    // CCER 的登记年份在提交后回到当前年，否则连续登记第二笔会沿用上一笔选的年份
    if (!isCea) ccerTradeForm.trade_year = new Date().getFullYear()
    // 写成功但读不出来：多半是后端缺流水 GET 接口（旧版本），必须明确告诉用户，
    // 否则界面看起来就是「登记了但什么都没有」
    if (tradeErr.value) flashErr(new Error(t('交易已登记，但流水读取失败：{msg}', { msg: tradeErr.value })))
    else flashOk(t('交易已登记'))
  }
  catch (e) { flashErr(e) }
}

// ---------------- CCER 台账 ----------------
// 持仓的新增 / 编辑统一走弹窗（openDlg('ccer')），按 id 判编辑、同年份可有多个批次
const ccerForm = reactive({ id: null, project_type: 'forest', issue_year: new Date().getFullYear() - 1, expire_at: '', qty: 0, cost: 0, eligible_qty: null, linked_green_cert: false })
// 后端存的是英文枚举（forest/renewable/...），表格与删除确认里统一显示中文标签
const CCER_TYPE_LABELS = { forest: '林业碳汇', renewable: '可再生能源', methane: '甲烷利用', general: '其他' }
const ccerTypeLabel = (k) => (CCER_TYPE_LABELS[k] ? t(CCER_TYPE_LABELS[k]) : (k || '—'))
async function delCcer(row) {
  if (!confirm(t('删除 CCER 持仓（{project_type} {issue_year}）？', { project_type: ccerTypeLabel(row.project_type), issue_year: row.issue_year }))) return
  try { await api.deleteCcer(selectedId.value, row.id); await loadSelected() } catch (e) { flashErr(e) }
}
// 绿电按年份删（建档主键 year），绿证按 id 删（同年份可有多个批次）
async function delGreenPower(row) {
  if (!confirm(t('删除 {year} 年绿电记录？', { year: row.year }))) return
  try { await api.deleteGreenPower(selectedId.value, row.year); await loadSelected(); flashOk(t('绿电记录已删除')) } catch (e) { flashErr(e) }
}
async function delGreenCert(row) {
  if (!confirm(t('删除 {year} 年绿证记录？', { year: row.year }))) return
  try { await api.deleteGreenCert(selectedId.value, row.id); await loadSelected(); flashOk(t('绿证记录已删除')) } catch (e) { flashErr(e) }
}

// ---------------- 策略运行 ----------------
// 右上角「年度选择」：'' = 全年度，否则为具体履约年度。同时作为指标卡（排放累计/CEA 可用）的全局年度作用域。
const runYear = ref('')
// 年度选择器的显示标签：全年度 / YYYY 年度（策略引擎页与运行按钮复用）
const runYearLabel = computed(() => (runYear.value === '' ? t('全年度') : `${runYear.value} ${t('年度')}`))
const planLabels = { conservative: '保守', balanced: '平衡', aggressive: '进取' }
const actionLabels = { buy_cea: '购入 CEA', sell_cea: '出售 CEA', use_ccer: '使用自有 CCER', buy_ccer: '外购 CCER', hold: '持有不动', stockpile: '低位囤存' }
async function runStrategy() {
  if (!selectedId.value) return flashErr(new Error(t('请先选择企业')))
  // ''（全年度）时传 0，后端聚合所有年度数据运行策略
  const year = runYear.value === '' ? 0 : Number(runYear.value)
  running.value = true
  try {
    lastRun.value = await api.runStrategy(selectedId.value, year)
    await loadSelected()
    tab.value = 'strategy'
    flashOk(t('策略已运行'))
  } catch (e) { flashErr(e) } finally { running.value = false }
}

// ---------------- 预警 ----------------
async function ackAlert(row) {
  try { await api.ackAlert(row.id); await loadSelected() } catch (e) { flashErr(e) }
}

// ---------------- 导入导出 ----------------
async function downloadTemplate() {
  try { await api.downloadImportTemplate(selectedId.value) } catch (e) { flashErr(e) }
}
async function importExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return
  try {
    const res = await api.importEnterpriseExcel(selectedId.value, file)
    flashOk(t('导入完成：{detail}', { detail: JSON.stringify(res.counts || res) }))
    await loadSelected()
  } catch (err) { flashErr(err) }
  e.target.value = ''
}

// ---------------- 派生统计 ----------------
// 年度候选：排放台账 + CEA 配额年度 + 当前年，去重倒序；供右上角「年度选择」下拉使用（另加「全年度」）
const runYearOptions = computed(() => {
  const ys = new Set()
  emissions.value.forEach(r => { const y = Number(r.year); if (y) ys.add(y) })
  ceaRows.value.forEach(r => { const y = Number(r.vintage_year); if (y) ys.add(y) })
  ys.add(new Date().getFullYear())
  return [...ys].sort((a, b) => b - a)
})
const stats = computed(() => {
  // 排放累计：跟随右上角年度作用域——全年度时全量累加，选某年只算该年
  const em = emissions.value.reduce((s, r) => {
    if (runYear.value !== '' && Number(r.year) !== Number(runYear.value)) return s
    return s + (Number(r.verified_total) || 0)
  }, 0)
  // CEA 可用：跟随右上角年度作用域——全年度时全量，选某年只算该配额年度
  const cea = ceaRows.value.reduce((s, r) => {
    if (runYear.value !== '' && Number(r.vintage_year) !== Number(runYear.value)) return s
    return s + ceaUsableOf(r)
  }, 0)
  const ccer = ccerRows.value.reduce((s, r) => s + ccerCurrentOf(r), 0)
  return { emissions: em, cea, ccer, gap: lastRun.value?.accounting_snapshot?.compliance_gap ?? null }
})
const gapClass = computed(() => {
  const g = stats.value.gap
  if (g === null) return ''
  return g > 0 ? 'gap-pos' : 'gap-neg'
})
// 当前页签的记录条数：显示在内容卡底部的页脚里，避免「表格上方有内容、下方空一大片」的失衡感
const tabCount = computed(() => {
  switch (tab.value) {
    case 'emissions': return emissions.value.length
    case 'forecasts': return forecasts.value.length
    case 'cea': return ceaRows.value.length
    case 'ccer': return ccerRows.value.length
    case 'green': return greenPower.value.length + greenCerts.value.length
    case 'strategy': return runs.value.length
    case 'alerts': return alerts.value.length
    default: return 0
  }
})
</script>

<template>
  <div class="compliance-panel" @click.stop>

    <div v-if="msg" class="flash ok">{{ msg }}</div>
    <div v-if="errMsg" class="flash err">{{ errMsg }}</div>

    <div class="layout">
      <!-- 企业列表 -->
      <aside class="ent-list">
        <div class="ent-head">
          <span>{{ t('控排企业') }}（{{ enterprises.length }}）</span>
          <button class="mini" @click="showEntForm = !showEntForm">{{ showEntForm ? t('收起') : '+ ' + t('新建') }}</button>
        </div>
        <div v-if="showEntForm" class="ent-form">
          <input v-model="entForm.name" :placeholder="t('企业名称 *')" />
          <input v-model="entForm.uscc" :placeholder="t('统一社会信用代码')" />
          <label class="fld">
            <span class="fl">{{ t('行业') }}</span>
            <select v-model="entForm.industry">
              <option v-for="i in meta.industries" :key="i.value" :value="i.value">{{ t(i.label) }}</option>
            </select>
          </label>
          <div class="row2">
            <label class="fld">
              <span class="fl">{{ t('纳入年度') }}</span>
              <input v-model.number="entForm.market_start_year" type="number" :placeholder="t('纳入年度')" />
            </label>
            <label class="fld">
              <span class="fl">{{ t('风险偏好') }}</span>
              <select v-model="entForm.risk_profile">
                <option v-for="r in meta.risk_profiles" :key="r.value" :value="r.value">{{ t(r.label) }}</option>
              </select>
            </label>
          </div>
          <div class="row2">
            <label class="fld" :title="t('年度预算上限(元)')">
              <span class="fl">{{ t('年度预算上限') }}</span>
              <span class="uf">
                <input v-model.number="entForm.annual_budget_cap" type="number" min="0" :placeholder="t('年度预算上限')" />
                <i>{{ t('元') }}</i>
              </span>
            </label>
            <label class="fld" :title="t('单笔限额(万吨)')">
              <span class="fl">{{ t('单笔限额') }}</span>
              <span class="uf">
                <input v-model.number="entForm.single_trade_limit" type="number" min="0" :placeholder="t('单笔限额')" />
                <i>{{ t('万吨') }}</i>
              </span>
            </label>
          </div>
          <button class="btn primary block" @click="createEnterprise">{{ t('创建企业') }}</button>
        </div>
        <ul>
          <li
            v-for="e in enterprises"
            :key="e.id"
            :class="{ active: e.id === selectedId }"
            @click="selectedId = e.id; loadSelected()"
          >
            <div class="li-title">{{ e.name }}</div>
            <div class="li-meta">{{ industryLabel(e.industry) }} · {{ e.market_start_year }} {{ t('纳入') }}</div>
          </li>
          <li v-if="!enterprises.length" class="empty">{{ t('暂无企业，点击上方「+ 新建」') }}</li>
        </ul>
      </aside>

      <!-- 右侧面板 -->
      <section class="detail">
        <div v-if="!selected" class="placeholder">
          <p>{{ t('请选择或新建一个控排企业') }}</p>
        </div>
        <template v-else>
          <div class="detail-head">
            <div class="head-main">
              <h3>{{ selected.name }}</h3>
              <div class="meta-line">
                {{ t(industryLabel(selected.industry)) }} · {{ t(riskLabel(selected.risk_profile)) }} ·
                {{ selected.market_start_year }} {{ t('年纳入') }} · {{ t('预算') }} {{ Number(selected.annual_budget_cap || 0).toLocaleString() }} {{ t('元') }}
              </div>
            </div>
            <div class="detail-actions">
              <select v-model="runYear" class="year-select">
                <option value="">{{ t('全年度') }}</option>
                <option v-for="y in runYearOptions" :key="y" :value="String(y)">{{ y }} {{ t('年度') }}</option>
              </select>
              <button class="btn primary" :disabled="running || !selectedId" @click="runStrategy">
                <span v-if="running" class="spinner"></span>
                {{ running ? t('策略运行中…') : t('运行履约策略') }}
              </button>
              <button class="btn" :disabled="!selectedId" @click="downloadTemplate">{{ t('模板下载') }}</button>
              <label class="btn file">
                {{ t('台账导入') }}
                <input type="file" accept=".xlsx,.xls" style="display:none" @change="importExcel" />
              </label>
              <button class="btn danger" :disabled="!selectedId" @click="deleteEnterprise">{{ t('删除企业') }}</button>
            </div>
          </div>

          <!-- 四张指标卡：各带自己的语义色（左侧色条 + 数值着色 + 右上角柔光），
               履约缺口按正负切换红/绿（gapClass），无数据时走中性灰 -->
          <div class="stats-bar">
            <div class="stat s-em">
              <span class="k"><i class="dot"></i>{{ t('排放累计') }}</span>
              <span class="v">{{ stats.emissions.toFixed(1) }}<em>{{ t('万吨') }}</em></span>
            </div>
            <div class="stat s-cea" :title="ceaHint">
              <span class="k">
                <i class="dot"></i>CEA {{ t('可用') }}
                <i class="k-scope">{{ ceaScopeLabel }}</i>
              </span>
              <span class="v">{{ stats.cea.toFixed(1) }}<em>{{ t('万吨') }}</em></span>
            </div>
            <div class="stat s-ccer">
              <span class="k"><i class="dot"></i>CCER {{ t('存量') }}</span>
              <span class="v">{{ stats.ccer.toFixed(1) }}<em>{{ t('万吨') }}</em></span>
            </div>
            <div class="stat s-gap" :class="gapClass || 'gap-na'">
              <span class="k"><i class="dot"></i>{{ t('履约缺口') }}</span>
              <span class="v">{{ stats.gap === null ? '—' : stats.gap.toFixed(1) }}<em v-if="stats.gap !== null">{{ t('万吨') }}</em></span>
            </div>
          </div>

          <!-- 内容卡：页签 + 表格放在同一张白色卡片里，卡片撑满剩余高度，
               避免「表格浮在灰底上、下方一大片空白」的失衡感 -->
          <div class="work-card">
          <div class="tabs">
            <button :class="{ active: tab === 'emissions' }" @click="tab = 'emissions'">{{ t('排放台账') }}</button>
            <button :class="{ active: tab === 'forecasts' }" @click="tab = 'forecasts'">{{ t('排放预测') }}</button>
            <button :class="{ active: tab === 'cea' }" @click="tab = 'cea'">CEA</button>
            <button :class="{ active: tab === 'ccer' }" @click="tab = 'ccer'">CCER</button>
            <button :class="{ active: tab === 'green' }" @click="tab = 'green'">{{ t('绿电') }}/{{ t('绿证') }}</button>
            <button :class="{ active: tab === 'strategy' }" @click="tab = 'strategy'">{{ t('策略引擎') }}</button>
            <button :class="{ active: tab === 'alerts' }" @click="tab = 'alerts'">{{ t('预警') }}<span v-if="alerts.filter(a => !a.acked).length" class="badge">{{ alerts.filter(a => !a.acked).length }}</span></button>
            <!-- 排放台账 / 排放预测 / CEA / CCER：持仓录入都走弹窗，右上角是「+ 新增」；
                 CEA / CCER 另外保留一个「交易登记」开关展开买卖登记表单 -->
            <button
              v-if="tab === 'emissions'"
              class="tabs-act add"
              :title="t('新增排放记录')"
              @click="openEmDialog()"
            >+ {{ t('新增') }}</button>
            <button
              v-else-if="tab === 'forecasts'"
              class="tabs-act add"
              :title="t('新增排放预测')"
              @click="openDlg('forecast')"
            >+ {{ t('新增') }}</button>
            <button
              v-else-if="tab === 'cea'"
              class="tabs-act add"
              :title="t('新增 CEA 持仓')"
              @click="openDlg('cea')"
            >+ {{ t('新增') }}</button>
            <button
              v-else-if="tab === 'ccer'"
              class="tabs-act add"
              :title="t('新增 CCER 持仓')"
              @click="openDlg('ccer')"
            >+ {{ t('新增') }}</button>
            <button
              v-if="editTabs.includes(tab)"
              class="tabs-act"
              :class="{ on: editOpen[tab] }"
              :title="editOpen[tab] ? t('收起') : t('交易登记')"
              @click="toggleEdit(tab)"
            >{{ editOpen[tab] ? t('收起') : t('交易登记') }}</button>
          </div>

          <!-- 排放台账 -->
          <div v-show="tab === 'emissions'" class="tab-body">
            <table class="tbl-num">
              <thead><tr><th>{{ t('年份') }}</th><th>{{ t('核查排放') }}</th><th>{{ t('范畴1燃料') }}</th><th>{{ t('范畴1过程') }}</th><th>{{ t('范畴2电力') }}</th><th>{{ t('CCER已用') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in emissions" :key="r.id">
                  <td>{{ r.year }}</td><td>{{ Number(r.verified_total).toFixed(1) }}</td>
                  <td>{{ Number(r.scope1_combustion || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.scope1_process || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.scope2_power || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.ccer_used || 0).toFixed(1) }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openEmDialog(r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delEmission(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!emissions.length" class="empty-row"><td colspan="7">{{ t('暂无排放记录，点右上角「新增」录入') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 排放预测 -->
          <div v-show="tab === 'forecasts'" class="tab-body" data-tab="forecasts">
            <table class="tbl-ops tbl-fc">
              <thead><tr><th>{{ t('年份') }}</th><th class="n">{{ t('预测排放') }}</th><th>{{ t('产能计划') }}</th><th>{{ t('生产计划') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in forecasts" :key="r.id">
                  <td>{{ r.year }}</td><td class="n">{{ Number(r.forecast_total).toFixed(1) }}</td>
                  <td>{{ r.capacity_plan || '—' }}</td><td>{{ r.production_plan || '—' }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openDlg('forecast', r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delForecast(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!forecasts.length" class="empty-row"><td colspan="5">{{ t('暂无预测记录，点右上角「新增」录入') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- CEA -->
          <div v-show="tab === 'cea'" class="tab-body" data-tab="cea">
            <!-- 年度作用域：卡片、表格、合计都跟着它走，避免把不同配额年度加成一个数 -->
            <div class="cea-scope">
              <label class="fld inline">
                <span class="fl">{{ t('配额年度') }}</span>
                <select v-model="ceaScopeYear">
                  <option value="">{{ t('全部年度') }}</option>
                  <option v-for="y in ceaYears" :key="y" :value="String(y)">{{ y }}</option>
                </select>
              </label>
              <span class="scope-sum">
                <b>{{ t('可用') }} {{ ceaScopedUsable.toFixed(1) }}</b> {{ t('万吨') }}
                <em :title="ceaHint">= {{ t('配额基准') }} {{ ceaScopedBase.toFixed(1) }} − {{ t('卖出') }} {{ ceaScopedSell.toFixed(1) }} + {{ t('买入') }} {{ ceaScopedBuy.toFixed(1) }}</em>
              </span>
              <span
                v-if="ceaOrphanTrades.length"
                class="scope-warn"
                :title="t('这些流水的归属年度没有对应的 CEA 持仓记录，因此不会计入任何一行的卖出/买入，也不会改变可用配额。可删掉后按正确的配额年度重新登记。')"
              >
                {{ t('{n} 笔流水的归属年度无对应持仓，未计入', { n: ceaOrphanTrades.length }) }}
              </span>
            </div>
            <table class="tbl-ops tbl-cea">
              <thead><tr>
                <th>{{ t('配额年份') }}</th>
                <th class="n">{{ t('免费配额') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('结转量') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('预分配') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('卖出') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('买入') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('可用配额') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('平均成本') }}<em>{{ t('元/吨') }}</em></th>
                <th></th>
              </tr></thead>
              <tbody>
                <tr v-for="r in ceaScopedRows" :key="r.id">
                  <td>{{ r.vintage_year }}</td>
                  <td class="n">{{ Number(r.free_quota || 0).toFixed(1) }}</td>
                  <td class="n">{{ numOrDash(r.carry_forward_qty) }}</td>
                  <td class="n">
                    {{ numOrDash(r.estimated_free_quota) }}
                    <i
                      v-if="Number(r.estimated_free_quota) > 0"
                      class="cea-tag"
                      :title="t('当年预分配配额按「替代值」参与可用量计算，不与免费配额相加')"
                    >{{ t('替代') }}</i>
                  </td>
                  <td
                    class="n"
                    :title="ceaSellBuyOf(r).fromTrades ? t('由当年交易流水汇总') : t('当年无交易流水，取台账手填的卖出量')"
                  >
                    {{ sellTextOf(r) }}<i v-if="ceaSellBuyOf(r).fromTrades && ceaSellBuyOf(r).sell !== 0" class="cea-tag src">{{ t('流水') }}</i>
                  </td>
                  <td
                    class="n"
                    :title="ceaSellBuyOf(r).fromTrades ? t('由当年交易流水汇总') : t('当年无交易流水，取台账手填的买入量')"
                  >
                    {{ buyTextOf(r) }}<i v-if="ceaSellBuyOf(r).fromTrades && ceaSellBuyOf(r).buy !== 0" class="cea-tag src">{{ t('流水') }}</i>
                  </td>
                  <td class="n strong">{{ ceaUsableOf(r).toFixed(1) }}</td>
                  <td class="n" :title="t('平均成本 = (买入前可用量 × 手填成本 + 买入金额) ÷ (买入前可用量 + 买入量)')">{{ ceaCostOf(r) > 0 ? ceaCostOf(r).toFixed(2) : '—' }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openDlg('cea', r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delCea(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!ceaScopedRows.length" class="empty-row">
                  <td colspan="9">{{ ceaRows.length ? t('该年度暂无 CEA 持仓，可切换到「全部年度」查看') : t('暂无 CEA 持仓，点右上角「新增」录入') }}</td>
                </tr>
              </tbody>
              <tfoot v-if="ceaScopedRows.length">
                <tr class="sum-row">
                  <td>{{ t('合计') }}</td>
                  <td class="n">{{ ceaScopedFree.toFixed(1) }}</td>
                  <td class="n">{{ ceaScopedCarry.toFixed(1) }}</td>
                  <td class="n">{{ ceaScopedEst.toFixed(1) }}</td>
                  <td class="n">{{ numOrDash(ceaScopedSell) }}</td>
                  <td class="n">{{ numOrDash(ceaScopedBuy) }}</td>
                  <td class="n strong">{{ ceaScopedUsable.toFixed(1) }}</td>
                  <td class="n">{{ ceaScopedCost > 0 ? ceaScopedCost.toFixed(1) : '—' }}</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
            <template v-if="editOpen.cea">
              <div class="sub-title">CEA · {{ t('交易登记') }}</div>
              <div class="form-grid entry">
                <label class="fld">
                  <span class="fl">{{ t('配额年度') }}</span>
                  <select v-model.number="ceaTradeForm.vintage_year">
                    <option v-for="y in ceaYears" :key="y" :value="y">{{ y }}</option>
                  </select>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('买卖方向') }}</span>
                  <select v-model="ceaTradeForm.side"><option value="buy">{{ t('买入') }}</option><option value="sell">{{ t('卖出') }}</option></select>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('数量') }}<em>{{ t('万吨') }}</em></span>
                  <input v-model.number="ceaTradeForm.qty" type="number" :min="0" :max="ceaTradeForm.side === 'sell' && ceaTradeAvailable !== null ? ceaTradeAvailable : undefined" />
                  <em v-if="ceaTradeForm.side === 'sell' && ceaTradeAvailable !== null" class="field-hint">
                    {{ t('当前可用配额') }} {{ ceaTradeAvailable.toFixed(2) }} {{ t('万吨') }}
                  </em>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('单价') }}<em>{{ t('元/吨') }}</em></span>
                  <input v-model.number="ceaTradeForm.price" type="number" />
                </label>
                <label class="fld">
                  <span class="fl">{{ t('备注') }}</span>
                  <input v-model="ceaTradeForm.note" />
                </label>
                <button class="btn primary" @click="addTrade('cea')">{{ t('登记交易') }}</button>
              </div>
            </template>
            <!-- 交易流水：登记成功后立即回读，避免「点了按钮但界面上什么都没变」 -->
            <div class="sub-title">
              CEA · {{ t('交易流水') }}<em class="dim">{{ ceaScopeLabel }}</em>
              <span class="sum">
                {{ t('买入') }} {{ ceaTradeSum.buy.toFixed(2) }} ·
                {{ t('卖出') }} {{ ceaTradeSum.sell.toFixed(2) }} ·
                <b>{{ t('流水净卖出') }} {{ ceaTradeSum.net.toFixed(2) }}</b> {{ t('万吨') }}
                <em class="dim">{{ t('（持仓表「卖出 / 买入」两列即由此汇总）') }}</em>
              </span>
            </div>
            <div v-if="tradeErr" class="trade-warn">
              <b>{{ t('交易流水读取失败：{msg}', { msg: tradeErr }) }}</b>
              <em>{{ t('登记动作本身已提交给后端，但页面拿不到流水（后端缺少流水查询接口时，卖出/买入与可用配额都不会变动）。请更新并重启后端服务后刷新页面。') }}</em>
            </div>
            <table class="tbl-trade tbl-cea-trade">
              <thead><tr>
                <th>{{ t('时间') }}</th><th>{{ t('归属年度') }}</th><th>{{ t('方向') }}</th>
                <th class="n">{{ t('数量') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('单价') }}<em>{{ t('元/吨') }}</em></th><th class="n">{{ t('金额') }}<em>{{ t('万元') }}</em></th>
                <th>{{ t('备注') }}</th><th></th>
              </tr></thead>
              <tbody>
                <tr v-for="r in ceaScopedTrades" :key="r.id">
                  <td class="mono">{{ fmtTime(r.traded_at) }}</td>
                  <td>{{ ceaTradeYearOf(r) || '—' }}</td>
                  <td :class="r.side === 'buy' ? 'side-buy' : 'side-sell'">{{ r.side === 'buy' ? t('买入') : t('卖出') }}</td>
                  <td class="n">{{ Number(r.qty || 0).toFixed(2) }}</td>
                  <td class="n">{{ Number(r.price || 0).toFixed(2) }}</td>
                  <td class="n">{{ (Number(r.qty || 0) * Number(r.price || 0)).toFixed(1) }}</td>
                  <td class="note">{{ r.note || '—' }}</td>
                  <td class="row-ops"><button class="link danger" @click="delCeaTrade(r)">{{ t('删') }}</button></td>
                </tr>
                <tr v-if="!ceaScopedTrades.length" class="empty-row">
                  <td colspan="8">{{ ceaTrades.length ? t('该年度没有 CEA 交易记录，可切换到「全部年度」查看') : t('暂无 CEA 交易记录，点右上角「交易登记」后可录入') }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- CCER -->
          <div v-show="tab === 'ccer'" class="tab-body" data-tab="ccer">
            <span
              v-if="ccerOrphanTrades.length"
              class="scope-warn"
              :title="t('这些流水的项目类型没有对应的 CCER 持仓记录，因此不会增减任何一行的当前持仓。可删除后按已有项目类型重新登记，或先在持仓表新增该类型。')"
            >
              {{ t('{n} 笔流水的项目类型无对应持仓，未计入', { n: ccerOrphanTrades.length }) }}
            </span>
            <table class="tbl-ops tbl-ccer">
              <thead><tr><th>{{ t('项目类型') }}</th><th>{{ t('签发年') }}</th><th>{{ t('到期日') }}</th><th class="n">{{ t('签发量') }}</th><th class="n">{{ t('买入') }}</th><th class="n">{{ t('卖出') }}</th><th class="n">{{ t('可抵扣') }}</th><th class="n">{{ t('成本') }}</th><th>{{ t('绿证') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in ccerRows" :key="r.id">
                  <td>{{ ccerTypeLabel(r.project_type) }}</td><td>{{ r.issue_year }}</td><td>{{ r.expire_at || '—' }}</td>
                  <td class="n">{{ Number(r.qty).toFixed(1) }}</td>
                  <td class="n" :title="t('由该类型交易流水汇总')">{{ numOrDash(ccerBuyOf(r)) }}<i v-if="ccerBuyOf(r) !== 0" class="cea-tag src">{{ t('流水') }}</i></td>
                  <td class="n" :title="t('由该类型交易流水汇总')">{{ numOrDash(ccerSellOf(r)) }}<i v-if="ccerSellOf(r) !== 0" class="cea-tag src">{{ t('流水') }}</i></td>
                  <td class="n strong" :title="t('可抵扣 = 签发量 + 买入 − 卖出')">{{ ccerCurrentOf(r).toFixed(1) }}</td>
                  <td class="n" :title="t('成本 = (签发量 × 手填成本 + 买入金额) ÷ (签发量 + 买入量)')">{{ ccerCostOf(r) > 0 ? ccerCostOf(r).toFixed(2) : '—' }}</td>
                  <td>{{ r.linked_green_cert ? t('是') : '—' }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openDlg('ccer', r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delCcer(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!ccerRows.length" class="empty-row"><td colspan="10">{{ t('暂无 CCER 持仓，点右上角「新增」录入') }}</td></tr>
              </tbody>
              <tfoot v-if="ccerRows.length">
                <tr class="sum-row">
                  <td>{{ t('合计') }}</td><td></td><td></td>
                  <td class="n">{{ ccerRows.reduce((s, r) => s + (Number(r.qty) || 0), 0).toFixed(1) }}</td>
                  <td class="n">{{ ccerTradeSum.buy.toFixed(1) }}</td>
                  <td class="n">{{ ccerTradeSum.sell.toFixed(1) }}</td>
                  <td class="n strong">{{ ccerRows.reduce((s, r) => s + ccerCurrentOf(r), 0).toFixed(1) }}</td>
                  <td class="n"></td><td></td><td></td>
                </tr>
              </tfoot>
            </table>
            <template v-if="editOpen.ccer">
              <div class="sub-title">CCER · {{ t('交易登记') }}</div>
              <div class="form-grid entry">
                <label class="fld">
                  <span class="fl">{{ t('登记年份') }}</span>
                  <select v-model.number="ccerTradeForm.trade_year" :title="t('默认取当前年份；补录历史成交时改成实际成交年份')">
                    <option v-for="y in ccerYears" :key="y" :value="y">{{ y }}</option>
                  </select>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('项目类型') }}</span>
                  <select v-model="ccerTradeForm.project_type">
                    <option v-for="(label, k) in CCER_TYPE_LABELS" :key="k" :value="k">{{ t(label) }}</option>
                  </select>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('买卖方向') }}</span>
                  <select v-model="ccerTradeForm.side"><option value="buy">{{ t('买入') }}</option><option value="sell">{{ t('卖出') }}</option></select>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('数量') }}<em>{{ t('万吨') }}</em></span>
                  <input v-model.number="ccerTradeForm.qty" type="number" :min="0" :max="ccerTradeForm.side === 'sell' ? ccerTradeAvailable : undefined" />
                  <em v-if="ccerTradeForm.side === 'sell'" class="field-hint">
                    {{ t('可抵扣') }} {{ ccerTradeAvailable.toFixed(2) }} {{ t('万吨') }}
                  </em>
                </label>
                <label class="fld">
                  <span class="fl">{{ t('单价') }}<em>{{ t('元/吨') }}</em></span>
                  <input v-model.number="ccerTradeForm.price" type="number" />
                </label>
                <label class="fld">
                  <span class="fl">{{ t('备注') }}</span>
                  <input v-model="ccerTradeForm.note" />
                </label>
                <button class="btn primary" @click="addTrade('ccer')">{{ t('登记交易') }}</button>
              </div>
            </template>
            <div class="sub-title">
              CCER · {{ t('交易流水') }}
              <span class="sum">
                {{ t('买入') }} {{ ccerTradeSum.buy.toFixed(2) }} ·
                {{ t('卖出') }} {{ ccerTradeSum.sell.toFixed(2) }} ·
                <b>{{ t('净卖出') }} {{ ccerTradeSum.net.toFixed(2) }}</b> {{ t('万吨') }}
              </span>
            </div>
            <div v-if="tradeErr" class="trade-warn">
              <b>{{ t('交易流水读取失败：{msg}', { msg: tradeErr }) }}</b>
              <em>{{ t('登记动作本身已提交给后端，但页面拿不到流水。请更新并重启后端服务后刷新页面。') }}</em>
            </div>
            <table class="tbl-trade tbl-ccer-trade">
              <thead><tr>
                <th>{{ t('时间') }}</th><th>{{ t('方向') }}</th><th>{{ t('项目类型') }}</th><th class="n">{{ t('数量') }}<em>{{ t('万吨') }}</em></th>
                <th class="n">{{ t('单价') }}<em>{{ t('元/吨') }}</em></th><th class="n">{{ t('金额') }}<em>{{ t('万元') }}</em></th><th>{{ t('备注') }}</th>
              </tr></thead>
              <tbody>
                <tr v-for="r in ccerTrades" :key="r.id">
                  <td class="mono">{{ fmtTime(r.traded_at) }}</td>
                  <td :class="r.side === 'buy' ? 'side-buy' : 'side-sell'">{{ r.side === 'buy' ? t('买入') : t('卖出') }}</td>
                  <td>{{ ccerTypeLabel(r.project_type) }}</td>
                  <td class="n">{{ Number(r.qty || 0).toFixed(2) }}</td>
                  <td class="n">{{ Number(r.price || 0).toFixed(2) }}</td>
                  <td class="n">{{ (Number(r.qty || 0) * Number(r.price || 0)).toFixed(1) }}</td>
                  <td class="note">{{ r.note || '—' }}</td>
                </tr>
                <tr v-if="!ccerTrades.length" class="empty-row"><td colspan="7">{{ t('暂无 CCER 交易记录，展开「编辑」后可登记') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 绿电/绿证：两张表各自带「+ 新增」，行内「编辑」进弹窗 -->
          <div v-show="tab === 'green'" class="tab-body" data-tab="green">
            <div class="sub-title">
              {{ t('绿电台账') }}
              <button class="sub-add" :title="t('新增绿电记录')" @click="openDlg('greenPower')">+ {{ t('新增') }}</button>
            </div>
            <table class="tbl-ops tbl-gp">
              <thead><tr><th>{{ t('年份') }}</th><th class="n">{{ t('市场绿电') }}</th><th class="n">{{ t('自发自用') }}</th><th class="n">{{ t('溢价') }}</th><th>{{ t('合同') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in greenPower" :key="r.id">
                  <td>{{ r.year }}</td><td class="n">{{ Number(r.market_green_mwh || 0).toFixed(1) }}</td>
                  <td class="n">{{ Number(r.self_gen_mwh || 0).toFixed(1) }}</td>
                  <td class="n">{{ Number(r.premium_per_mwh || 0).toFixed(1) }}</td><td>{{ r.contract_ref || '—' }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openDlg('greenPower', r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delGreenPower(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!greenPower.length" class="empty-row"><td colspan="6">{{ t('暂无绿电记录，点右上角「新增」录入') }}</td></tr>
              </tbody>
            </table>
            <div class="sub-title">
              {{ t('绿证台账') }}
              <button class="sub-add" :title="t('新增绿证记录')" @click="openDlg('greenCert')">+ {{ t('新增') }}</button>
            </div>
            <table class="tbl-ops tbl-gc">
              <thead><tr><th>{{ t('年份') }}</th><th class="n">{{ t('数量') }}</th><th class="n">{{ t('单价') }}</th><th>{{ t('状态') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in greenCerts" :key="r.id">
                  <td>{{ r.year }}</td><td class="n">{{ Number(r.qty).toFixed(1) }}</td>
                  <td class="n">{{ Number(r.unit_price || 0).toFixed(1) }}</td><td>{{ r.retired ? t('已注销') : t('持有') }}</td>
                  <td class="row-ops">
                    <button class="link" @click="openDlg('greenCert', r)">{{ t('编辑') }}</button>
                    <button class="link danger" @click="delGreenCert(r)">{{ t('删') }}</button>
                  </td>
                </tr>
                <tr v-if="!greenCerts.length" class="empty-row"><td colspan="5">{{ t('暂无绿证记录，点右上角「新增」录入') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 策略引擎 -->
          <div v-show="tab === 'strategy'" class="tab-body">
            <div class="run-head">
              <div>
                <strong>{{ runYearLabel }} {{ t('年度策略') }}</strong>
                <span class="hint">{{ t('口径：保守 / 平衡 / 进取 三档 + 价格窗口 + 结转测算') }}</span>
              </div>
              <button class="btn primary" :disabled="running" @click="runStrategy">
                <span v-if="running" class="spinner"></span>{{ t('重新运行') }}
              </button>
            </div>
            <div v-if="lastRun" class="run-result">
              <div class="run-meta">
                <span class="chip">{{ t('窗口') }}：{{ lastRun.market_tags?.time_window || '—' }}</span>
                <span class="chip">{{ t('价格带') }}：{{ lastRun.market_tags?.price_band || '—' }}</span>
                <span class="chip">{{ t('动作') }}：{{ lastRun.market_tags?.action_tag || '—' }}</span>
                <span class="chip">CCER {{ t('上限') }}：{{ lastRun.accounting_snapshot?.ccer_cap ?? '—' }}</span>
                <span class="chip" :class="(lastRun.accounting_snapshot?.compliance_gap || 0) > 0 ? 'pos' : 'neg'">
                  {{ t('缺口') }}：{{ Number(lastRun.accounting_snapshot?.compliance_gap || 0).toFixed(1) }} {{ t('万吨') }}
                </span>
              </div>
              <div class="plans">
                <div v-for="(label, key) in planLabels" :key="key" class="plan" :class="key">
                  <h4>{{ t(label) }}{{ t('方案') }}</h4>
                  <div class="plan-nums">
                    <span>{{ t('总成本') }} <b>{{ Number((lastRun.plans || []).find(p => p.key === key)?.total_cost || 0).toLocaleString() }}</b> {{ t('元') }}</span>
                    <span>{{ t('净节约') }} <b class="ok">{{ Number((lastRun.plans || []).find(p => p.key === key)?.net_saving || 0).toLocaleString() }}</b> {{ t('元') }}</span>
                  </div>
                  <ul>
                    <li v-for="a in ((lastRun.plans || []).find(p => p.key === key)?.actions || [])" :key="a.action + a.window">
                      {{ t(actionLabels[a.action] || a.action) }}：
                      <b>{{ Number(a.qty).toFixed(1) }} {{ t('万吨') }}</b> @ {{ Number(a.unit_price).toFixed(1) }} {{ t('元/吨') }}
                      <span class="w">({{ a.window }})</span>
                    </li>
                    <li v-if="!((lastRun.plans || []).find(p => p.key === key)?.actions || []).length" class="dim">—</li>
                  </ul>
                </div>
              </div>
            </div>
            <div v-else-if="runs.length" class="run-history">
              <p class="hint">{{ t('最近一次运行：') }}</p>
              <table>
                <thead><tr><th>{{ t('运行时间') }}</th><th>{{ t('年度') }}</th><th>{{ t('缺口') }}({{ t('万吨') }})</th><th>{{ t('窗口') }}</th><th>{{ t('价格带') }}</th><th>{{ t('计划数') }}</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="r in runs.slice(0, 5)" :key="r.id">
                    <td>{{ r.created_at }}</td><td>{{ r.compliance_year ? r.compliance_year : t('全年度') }}</td>
                    <td>{{ Number(r.accounting_snapshot?.compliance_gap || 0).toFixed(1) }}</td>
                    <td>{{ r.market_tags?.time_window || '—' }}</td>
                    <td>{{ r.market_tags?.price_band || '—' }}</td>
                    <td>{{ (r.plans || []).length }}</td>
                    <td><button class="link" @click="api.downloadStrategyRun(selectedId, r.id)">{{ t('下载') }}</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-box">
              <p>{{ t('尚未运行策略') }}</p>
              <button class="btn primary" @click="runStrategy">{{ t('立即运行') }} {{ runYearLabel }} {{ t('年度策略') }}</button>
            </div>
          </div>

          <!-- 预警 -->
          <div v-show="tab === 'alerts'" class="tab-body">
            <table>
              <thead><tr><th>{{ t('级别') }}</th><th>{{ t('类型') }}</th><th>{{ t('内容') }}</th><th>{{ t('触发时间') }}</th><th>{{ t('到期') }}</th><th></th></tr></thead>
              <tbody>
                <tr v-for="a in alerts" :key="a.id" :class="a.level">
                  <td>{{ a.level }}</td><td>{{ a.alert_type }}</td>
                  <td class="msg">{{ a.message }}</td>
                  <td>{{ a.created_at }}</td><td>{{ a.due_at || '—' }}</td>
                  <td>
                    <button v-if="!a.acked" class="link" @click="ackAlert(a)">{{ t('已处理') }}</button>
                    <span v-else class="dim">{{ t('已确认') }}</span>
                  </td>
                </tr>
                <tr v-if="!alerts.length" class="empty-row"><td colspan="6">{{ t('暂无预警') }}</td></tr>
              </tbody>
            </table>
          </div>
            <!-- 页脚：只放条数，给内容卡一个「收口」，卡片撑满高度时不至于下半截空荡 -->
            <div class="work-foot">
              <span>{{ t('共 {n} 条记录', { n: tabCount }) }}</span>
            </div>
          </div>
        </template>
      </section>
    </div>

    <!-- 排放台账录入弹窗：新增 / 编辑共用（Teleport 到 body，避免被面板的 absolute 容器裁切） -->
    <Teleport to="body">
      <!-- 遮罩只负责挡住背景点击，不绑定关闭：只能由 ✕ / 取消 关闭 -->
      <div v-if="emDialogOpen" class="em-mask">
        <div class="em-dialog" role="dialog" aria-modal="true" :aria-label="emIsEdit ? t('编辑排放数据') : t('新增排放数据')">
          <div class="em-head">
            <b>{{ emIsEdit ? t('编辑排放数据') : t('新增排放数据') }}</b>
            <span v-if="selected" class="em-ent">{{ selected.name }}</span>
            <button class="em-x" :aria-label="t('关闭')" @click="closeEmDialog">✕</button>
          </div>
          <div class="em-body">
            <div class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('年份') }}</span>
                <input ref="emYearInput" v-model.number="emForm.year" type="number" :disabled="emIsEdit" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('核查排放') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="emForm.verified_total" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('范畴1燃料') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="emForm.scope1_combustion" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('范畴1过程') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="emForm.scope1_process" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('范畴2电力') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="emForm.scope2_power" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('净购入电量') }}<em>{{ t('万MWh') }}</em></span>
                <input v-model.number="emForm.purchased_mwh" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('CCER已用') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="emForm.ccer_used" type="number" step="0.01" />
              </label>
            </div>
            <p class="em-tip">
              {{ emIsEdit ? t('年份是该企业台账的主键，编辑时不可修改；如需改年份请删掉后重新新增。') : t('同一企业同一年份只保留一条记录，重复新增会覆盖该年度的数据。') }}
            </p>
          </div>
          <div class="em-foot">
            <button class="btn" @click="closeEmDialog">{{ t('取消') }}</button>
            <button class="btn primary" :disabled="emSaving" @click="saveEmission">
              <span v-if="emSaving" class="spinner"></span>
              {{ emSaving ? t('保存中…') : t('保存') }}
            </button>
          </div>
        </div>
      </div>
      <!-- 排放预测 / 绿电 / 绿证 录入弹窗：结构与关闭规则同排放台账（只能 ✕ / 取消 关） -->
      <div v-if="dlgKind" class="em-mask">
        <div class="em-dialog" role="dialog" aria-modal="true" :aria-label="dlgTitle">
          <div class="em-head">
            <b>{{ dlgTitle }}</b>
            <span v-if="selected" class="em-ent">{{ selected.name }}</span>
            <button class="em-x" :aria-label="t('关闭')" @click="closeDlg">✕</button>
          </div>
          <div class="em-body">
            <div v-if="dlgKind === 'cea'" class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('配额年份') }}</span>
                <input v-model.number="ceaForm.vintage_year" type="number" :disabled="dlgYearLocked" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('免费配额') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="ceaForm.free_quota" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('结转量') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="ceaForm.carry_forward_qty" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('预分配配额') }}<em>{{ t('万吨') }}</em></span>
                <input
                  v-model.number="ceaForm.estimated_free_quota" type="number" step="0.01"
                  :title="t('当年预分配配额，填了之后按「替代值」参与可用量计算，不与免费配额相加')"
                />
              </label>
              <label class="fld">
                <span class="fl">{{ t('卖出量') }}<em>{{ t('万吨') }} · {{ t('无流水时回退') }}</em></span>
                <input
                  v-model.number="ceaForm.net_sell_qty" type="number" step="0.01"
                  :title="t('该配额年度有交易流水时以流水汇总为准，此值仅在无流水时作为卖出量回退')"
                />
              </label>
              <label class="fld">
                <span class="fl">{{ t('买入量') }}<em>{{ t('万吨') }} · {{ t('无流水时回退') }}</em></span>
                <input
                  v-model.number="ceaForm.buy_qty" type="number" step="0.01"
                  :title="t('该配额年度有交易流水时以流水汇总为准，此值仅在无流水时作为买入量回退；买入会增加可用配额')"
                />
              </label>
              <label class="fld">
                <span class="fl">{{ t('平均成本') }}<em>{{ t('元/吨') }}</em></span>
                <input v-model.number="ceaForm.avg_cost" type="number" step="0.01" />
              </label>
              <div class="em-note full">
                {{ t('可用配额 = 配额基准 − 卖出 + 买入，其中配额基准 = max(免费配额, 预分配配额) + 结转量。卖出/买入优先取该配额年度的交易流水汇总，当年无流水时取上面填的卖出量与买入量。') }}
              </div>
            </div>
            <div v-else-if="dlgKind === 'ccer'" class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('项目类型') }}</span>
                <select v-model="ccerForm.project_type">
                  <option value="forest">{{ t('林业碳汇') }}</option><option value="renewable">{{ t('可再生能源') }}</option>
                  <option value="methane">{{ t('甲烷利用') }}</option><option value="general">{{ t('其他') }}</option>
                </select>
              </label>
              <label class="fld">
                <span class="fl">{{ t('签发年份') }}</span>
                <input v-model.number="ccerForm.issue_year" type="number" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('到期日') }}</span>
                <input v-model="ccerForm.expire_at" type="date" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('数量') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="ccerForm.qty" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('成本') }}<em>{{ t('元/吨') }}</em></span>
                <input v-model.number="ccerForm.cost" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('可抵扣量') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="ccerForm.eligible_qty" type="number" step="0.01" />
              </label>
              <div class="fld">
                <span class="fl">{{ t('绿证') }}</span>
                <label class="em-check">
                  <input v-model="ccerForm.linked_green_cert" type="checkbox" />
                  <span>{{ t('已关联绿证') }}</span>
                </label>
              </div>
            </div>
            <div v-else-if="dlgKind === 'forecast'" class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('年份') }}</span>
                <input v-model.number="fcForm.year" type="number" :disabled="dlgYearLocked" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('预测排放') }}<em>{{ t('万吨') }}</em></span>
                <input v-model.number="fcForm.forecast_total" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('产能计划') }}</span>
                <input v-model="fcForm.capacity_plan" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('生产计划') }}</span>
                <input v-model="fcForm.production_plan" />
              </label>
            </div>
            <div v-else-if="dlgKind === 'greenPower'" class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('年份') }}</span>
                <input v-model.number="gpForm.year" type="number" :disabled="dlgYearLocked" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('市场绿电') }}<em>{{ t('万MWh') }}</em></span>
                <input v-model.number="gpForm.market_green_mwh" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('自发自用') }}<em>{{ t('万MWh') }}</em></span>
                <input v-model.number="gpForm.self_gen_mwh" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('绿电溢价') }}<em>{{ t('元/MWh') }}</em></span>
                <input v-model.number="gpForm.premium_per_mwh" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('合同编号') }}</span>
                <input v-model="gpForm.contract_ref" />
              </label>
            </div>
            <div v-else class="em-grid">
              <label class="fld">
                <span class="fl">{{ t('年份') }}</span>
                <input v-model.number="gcForm.year" type="number" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('数量') }}<em>{{ t('万张') }}</em></span>
                <input v-model.number="gcForm.qty" type="number" step="0.01" />
              </label>
              <label class="fld">
                <span class="fl">{{ t('单价') }}<em>{{ t('元/张') }}</em></span>
                <input v-model.number="gcForm.unit_price" type="number" step="0.01" />
              </label>
              <div class="fld">
                <span class="fl">{{ t('状态') }}</span>
                <label class="em-check">
                  <input v-model="gcForm.retired" type="checkbox" />
                  <span>{{ t('已注销') }}</span>
                </label>
              </div>
            </div>
            <p class="em-tip">{{ dlgTip }}</p>
          </div>
          <div class="em-foot">
            <button class="btn" @click="closeDlg">{{ t('取消') }}</button>
            <button class="btn primary" :disabled="dlgSaving" @click="saveDlg">
              <span v-if="dlgSaving" class="spinner"></span>
              {{ dlgSaving ? t('保存中…') : t('保存') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ===== 参照能碳一体机管理（cbx-*）体系统一：panel-2 外层背景 + 圆角卡片 + 浅色透明底按钮 ===== */
.compliance-panel {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
}
.year-select {
  padding: 3px 8px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text);
  font-size: 11px;
  outline: none;
  height: 26px;
}
.btn {
  padding: 3px 11px;
  border-radius: 5px;
  border: 1px solid var(--accent-l);
  background: var(--accent-l);
  color: var(--accent-d);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  height: 26px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: border-color .15s, background .15s, color .15s;
}
.btn:hover { border-color: var(--accent-d); color: var(--accent-d); }
.btn.primary { background: var(--accent); border-color: var(--accent-d); color: var(--on-accent); font-weight: 600; }
.btn.primary:hover { background: var(--accent-d); border-color: var(--accent-d); color: var(--on-accent); }
.btn.danger { background: rgba(188, 59, 48, 0.1); border-color: rgba(188, 59, 48, 0.3); color: var(--red); }
.btn.danger:hover { border-color: var(--red); background: rgba(188, 59, 48, 0.18); color: var(--red); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.file { position: relative; }
.spinner {
  width: 11px; height: 11px; border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff; border-radius: 50%; animation: spin 0.8s linear infinite;
}
.btn:not(.primary) .spinner { border-color: var(--muted); border-top-color: var(--text); }
@keyframes spin { to { transform: rotate(360deg); } }
/* 提示条改为悬浮在面板底部中央：原来插在面板最顶部参与布局，用户在 CEA 页签底部
   点「登记交易」时提示在视野外，看起来就像「点了没反应」，而且插入还会把整页顶一下 */
.flash {
  position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%);
  z-index: 30; margin: 0; padding: 7px 16px; border-radius: 6px; font-size: 12px;
  background: var(--panel); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
  pointer-events: none; animation: flash-in 0.16s ease-out;
}
@keyframes flash-in { from { opacity: 0; transform: translate(-50%, 6px); } to { opacity: 1; transform: translate(-50%, 0); } }
.flash.ok { color: var(--green); border: 1px solid rgba(46, 139, 87, 0.45); }
.flash.err { color: var(--red); border: 1px solid rgba(188, 59, 48, 0.45); }
.layout { flex: 1; display: flex; min-height: 0; }
/* 左侧企业列表：VS Code 资源管理器风格 */
.ent-list {
  width: 236px; flex: 0 0 236px; border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow-y: auto; background: var(--panel-2);
}
.ent-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px 6px; font-size: 11px; color: var(--muted); font-weight: 600;
   background: var(--panel-2);
}
.mini {
  background: var(--accent-l); border: 1px solid var(--accent-l); color: var(--accent-d);
  font-size: 11px; padding: 2px 10px; border-radius: 5px; cursor: pointer; height: 22px;
  transition: border-color .15s;
}
.mini:hover { border-color: var(--accent-d); }
.ent-form { padding: 10px 12px; display: grid; gap: 6px; border-bottom: 1px solid var(--line-soft); }
.ent-form input, .ent-form select, .form-grid input, .form-grid select {
  padding: 4px 8px; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 5px; color: var(--text); font-size: 11px; outline: none;
}
.ent-form input:focus, .ent-form select:focus, .form-grid input:focus, .form-grid select:focus {
  border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l);
}
/* 输入框与下拉框统一高度：浏览器默认下 select 比 input 高 ~4px，同一行并排会高低不齐 */
.ent-form input, .ent-form select { height: 25px; box-sizing: border-box; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
/* 带字段名的表单项：行业 / 纳入年度 / 风险偏好 / 预算 / 单笔限额 都靠这一层显示「这一项是什么」 */
.fld { display: grid; gap: 3px; min-width: 0; align-content: start; }
.fl { font-size: 11px; color: var(--muted); line-height: 14px; white-space: nowrap; }
/* 带单位后缀的输入框：单位常显，避免只靠 placeholder 提示（有默认值 0 时 placeholder 根本不显示） */
.uf { position: relative; display: block; min-width: 0; }
.ent-form .uf input { width: 100%; box-sizing: border-box; padding-right: 32px; }
.uf i {
  position: absolute; right: 7px; top: 50%; transform: translateY(-50%);
  font-style: normal; font-size: 10px; color: var(--muted); pointer-events: none;
}
.block { width: 100%; }
.ent-list ul { list-style: none; margin: 0; padding: 2px 8px 8px; }
.ent-list li { position: relative; padding: 8px 10px; border-radius: 6px; cursor: pointer; border: 1px solid transparent; }
.ent-list li:hover { background: var(--panel-3); }
.ent-list li.active { background: var(--sel); }
.ent-list li.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 2px;
  border-radius: 2px;
  background: var(--accent);
}
.li-title { font-size: 12.5px; font-weight: 600; color: var(--text); }
.li-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }
.ent-list .empty { color: var(--muted); font-size: 12px; text-align: center; cursor: default; }
/* 右侧工作区：灰底画布 + 自上而下「标题/指标卡/内容卡」三段，内容卡撑满剩余高度 */
.detail {
  flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0;
  padding: 12px 14px 14px; background: var(--panel-2); overflow: hidden;
}
.placeholder { flex: 1; display: grid; place-items: center; color: var(--faint); font-size: 14px; }
.detail-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 10px 16px; margin-bottom: 12px; flex-wrap: wrap;
}
.head-main { min-width: 0; flex: 1 1 auto; }
.detail-head h3 { margin: 0 0 3px; font-size: 17px; font-weight: 600; color: var(--text); letter-spacing: -.2px; }
.meta-line { font-size: 11.5px; color: var(--muted); line-height: 1.5; }
/* 操作条作为整体不拆行：宽度够就并排在标题右侧，不够就整体落到第二行靠右，
   不会出现「年度选择单独一行、按钮又一行」的碎裂排布 */
.detail-actions { display: flex; align-items: center; gap: 6px; flex: none; flex-wrap: nowrap; margin-left: auto; }
/* ===== 指标卡：左侧语义色条 + 右上角柔光 + 数值着色，圆角 10px 的轻卡片 =====
   色相全部取自主题变量（--accent / --green / --orange / --red / --muted），
   跟随「系统主题色」与深浅色模式自动变化；柔光用伪元素的低透明度叠加，
   避免 color-mix / rgba(var()) 这类不兼容写法。 */
.stats-bar { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.stat {
  --tint: var(--accent);
  position: relative; overflow: hidden;
  padding: 10px 14px 11px 16px;
  border-radius: 10px;
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  display: flex; flex-direction: column; justify-content: center; gap: 7px;
  min-height: 64px;
  transition: transform var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease),
              border-color var(--dur-fast) var(--ease);
}
/* 左侧色条：卡片最直观的“形状记忆点” */
.stat::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--tint);
}
/* 同色薄雾：左上斜向渐隐的一层淡色，避免整卡纯白显得空；文字在下层 z-index 提升后不受影响 */
.stat::after {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(150deg, var(--tint) 0%, transparent 60%); opacity: .075;
}
.stat:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, .10);
  border-color: var(--tint);
}
.stat .k {
  position: relative; z-index: 1;
  display: flex; align-items: center; gap: 6px;
  font-size: 10.5px; color: var(--muted); letter-spacing: .2px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
/* 标签前的实心圆点：与左侧色条同色，强化识别 */
.stat .k .dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--tint); flex: none;
}
/* 数值 + 单位：单位紧跟数值（小一号、非等宽、弱灰），比浮在卡片右角的胶囊更像“一个数” */
.stat .v {
  position: relative; z-index: 1;
  display: flex; align-items: baseline; gap: 5px;
  font-size: 21px; font-weight: 700; line-height: 1.05; color: var(--tint);
  font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -.4px;
}
.stat .v em {
  font-style: normal; font-family: var(--ui); font-size: 10.5px; font-weight: 500;
  letter-spacing: 0; color: var(--faint);
}
/* 指标卡上的作用域胶囊：明确这个数是「全部年度合计」还是某一年，避免跨年误读 */
.stat .k-scope {
  font-style: normal; font-size: 9.5px; line-height: 1; padding: 2px 5px;
  border-radius: 3px; background: var(--panel-2); border: 1px solid var(--border);
  color: var(--faint); flex: none;
}
/* 四张卡的语义色：排放=主题色，CEA=绿，CCER=橙，缺口=红/绿/灰（按正负与有无数据） */
.stat.s-em   { --tint: var(--accent); }
.stat.s-cea  { --tint: var(--green); }
.stat.s-ccer { --tint: var(--orange); }
.stat.s-gap  { --tint: var(--muted); }
.stat.s-gap.gap-pos { --tint: var(--red); }    /* 缺口为正 = 还需买入配额 */
.stat.s-gap.gap-neg { --tint: var(--green); }  /* 缺口为负 = 配额富余 */
/* 窄面板退成两列，避免四列挤压成“细长条” */
@media (max-width: 1040px) { .stats-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
/* 宽屏（卡面被拉到 300px 以上）改成「标签在左、数值在右」的横排：
   否则标签和单位胶囊会隔着一大片空白、卡片变成又长又扁的条 */
@media (min-width: 1500px) {
  .stat { flex-direction: row; align-items: center; justify-content: space-between; gap: 10px; }
  .stat .k { flex: 1 1 auto; }
  .stat .v { font-size: 26px; }
}
/* ===== 内容卡：页签 + 表格共用一张白卡，撑满标题/指标卡之后的剩余高度 ===== */
.work-card {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: var(--shadow); overflow: hidden;
}
.work-card .tabs { margin: 0; padding: 0 14px; flex: none; }
/* 二级页签：激活态用主题色下划线（设计系统里 tab 底边属于主题色的合法用法） */
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); align-items: stretch; flex-wrap: wrap; }
.tabs button {
  position: relative; padding: 8px 12px; background: transparent; border: none;
  color: var(--muted); font-size: 12px; cursor: pointer; border-radius: 0;
}
.tabs button:hover { color: var(--text); background: var(--panel-2); }
.tabs button.active { color: var(--accent-d); font-weight: 600; background: transparent; }
.tabs button.active::after {
  content: ''; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px;
  background: var(--accent); border-radius: 2px 2px 0 0;
}
/* 页签行右端的「编辑」入口：点击才展开排放录入表单 */
.tabs .tabs-act {
  margin-left: auto; align-self: center; margin-bottom: 0;
  height: 23px; padding: 0 12px; line-height: 21px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--panel); color: var(--accent-d);
  font-size: 11.5px; font-weight: 600;
}
.tabs .tabs-act:hover { background: var(--accent); border-color: var(--accent-d); color: var(--on-accent); }
.tabs .tabs-act.on { background: var(--panel-2); border-color: var(--line-soft); color: var(--muted); font-weight: 400; }
.badge {
  display: inline-block; min-width: 16px; height: 16px; padding: 0 4px; margin-left: 5px;
  background: var(--red); color: #fff; border-radius: 999px; font-size: 10px; line-height: 16px; text-align: center;
}
/* 内容区自己滚，卡片外框不动 */
.work-card .tab-body { flex: 1; min-height: 0; overflow-y: auto; padding: 12px 14px 14px; }
/* 页脚：卡片底部的收口线 + 条数，卡片被撑高时下半截不至于空荡 */
.work-foot {
  flex: none; display: flex; align-items: center; justify-content: flex-end;
  padding: 7px 14px; border-top: 1px solid var(--line-soft);
  font-size: 10.5px; color: var(--faint); letter-spacing: .2px;
}
.tab-body { animation: fade 0.2s ease; }
@keyframes fade { from { opacity: 0 } to { opacity: 1 } }
.form-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px; margin-bottom: 14px; align-items: end;
}
.form-grid.sub { margin-top: 18px; border-top: 1px dashed var(--border); padding-top: 12px; }
.form-grid.entry {
  padding: 9px 10px 10px; border: 1px solid var(--line-soft); border-radius: 6px;
  background: var(--panel-2); margin-bottom: 14px; row-gap: 8px;
}
/* 录入行的字段名右缀单位：小一号、更淡，不与字段名抢注意力 */
.form-grid.entry .fl em { font-style: normal; font-size: 10px; color: var(--faint); margin-left: 4px; }
/* 卖出数量输入框下方的可用额度提示：小字、弱化，紧跟输入框不占太多空间 */
.form-grid.entry .fld .field-hint { font-style: normal; font-size: 10px; color: var(--faint); margin-top: 1px; }
/* 输入框统一高度并吃满单元格，标签在上、输入在下，同一行基线自然对齐 */
.form-grid.entry .fld input,
.form-grid.entry .fld select { width: 100%; box-sizing: border-box; height: 24px; }
/* 复选框没有标签行，贴底对齐到同一行输入框的基线 */
.form-grid.entry > .check { align-self: end; }
/* 「保存排放」钉在最后一列：窗口变窄换行时也不会停在行中间、右边空一大块 */
.form-grid.entry .btn { grid-column: -2 / -1; justify-self: end; }
.form-grid .btn { grid-column: span 1; height: 24px; }
.check {
  display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted);
  align-self: center; padding: 0; min-height: 24px;
}
.check input { width: auto; height: auto; margin: 0; flex-shrink: 0; }
/* 同一页签下有两张表时（绿电 / 绿证）用小标题分节，收起录入区后两张表不会挤成一张 */
.sub-title {
  font-size: 11px; font-weight: 600; color: var(--muted);
  margin: 2px 0 6px; letter-spacing: .3px;
  display: flex; align-items: baseline; gap: 8px;
}
/* 标题后跟的年度作用域标注：不要斜体、不要抢主标题的字重 */
.sub-title > em.dim { font-style: normal; font-weight: 400; }
.sub-title .sum { margin-left: auto; font-weight: 400; color: var(--faint); font-size: 10.5px; }
.sub-title .sum b { color: var(--text); font-weight: 600; }
/* 小标题右侧的「+ 新增」：绿电 / 绿证两张表各有自己的入口，不需要先选类型 */
.sub-add {
  margin-left: auto; align-self: center; display: inline-flex; align-items: center;
  height: 20px; padding: 0 7px; border-radius: 4px; cursor: pointer; line-height: 1;
  background: var(--panel); border: 1px solid var(--border); color: var(--accent);
  font-size: 10.5px; font-weight: 500;
}
.sub-add:hover { border-color: var(--accent); background: var(--accent); color: var(--on-accent); }
/* 交易流水：时间等宽、数字右对齐、备注截断，避免长备注把表横向撑破 */
.tbl-trade { table-layout: fixed; }
.tbl-trade th, .tbl-trade td { padding: 6px 8px; }
.tbl-trade th:first-child { width: 118px; }
.tbl-trade th:nth-child(2) { width: 56px; }
.tbl-trade th:nth-child(3), .tbl-trade th:nth-child(4), .tbl-trade th:nth-child(5) { width: 92px; }
.tbl-trade th em { display: block; font-style: normal; font-weight: 400; font-size: 9.5px; color: var(--faint); }
.tbl-trade .n { text-align: right; font-variant-numeric: tabular-nums; }
.tbl-trade .mono { font-variant-numeric: tabular-nums; color: var(--muted); }
.tbl-trade .note { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
.tbl-trade .side-buy { color: var(--red); }
.tbl-trade .side-sell { color: var(--green); }
.sub-title + table { margin-bottom: 12px; }
/* 表格：白卡内不再画外框（外框由 .work-card 承担），表头用一条略深的横线压住 */
table {
  width: 100%; border-collapse: collapse; font-size: 11.5px;
}
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line-soft); }
tbody tr:last-child td { border-bottom: none; }
th {
  color: var(--muted); font-weight: 500; font-size: 10.5px; background: transparent;
  letter-spacing: .3px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
tbody tr:hover td { background: var(--panel-2); }
.empty-row td { text-align: center; color: var(--faint); padding: 24px; }
/* 数值型表格：固定列宽 + 数字右对齐（位数对齐才好逐行比较），首列文字左对齐、末列操作右对齐。
   不固定列宽时，空的「操作」列表头会自动吃掉剩余空间，把数字列挤成左宽右空的怪比例。 */
.tbl-num { table-layout: fixed; }
.tbl-num th:first-child, .tbl-num td:first-child { width: 86px; }
.tbl-num th:last-child, .tbl-num td:last-child { width: 62px; text-align: right; }
.tbl-num th:not(:first-child):not(:last-child),
.tbl-num td:not(:first-child):not(:last-child) { text-align: right; font-variant-numeric: tabular-nums; }
/* 含文字列的台账表（排放预测 / 绿电 / 绿证）：固定布局 + 操作列只占按钮宽度，
   否则空的「操作」表头会吃掉剩余宽度，把「编辑」推到离数据很远的最右边 */
.tbl-ops { table-layout: fixed; }
.tbl-ops th:last-child, .tbl-ops td:last-child { width: 58px; text-align: right; }
.tbl-ops th.n, .tbl-ops td.n { text-align: right; font-variant-numeric: tabular-nums; }
/* 数字列钉成固定窄列、剩余宽度交给文字列：否则固定布局会平均分配，
   数字被摊到很宽的列里、彼此拉得很开，表头还会挤成一团 */
.tbl-fc th:nth-child(1), .tbl-gp th:nth-child(1), .tbl-gc th:nth-child(1) { width: 90px; }
.tbl-fc th:nth-child(2) { width: 130px; }
.tbl-gp th:nth-child(2), .tbl-gp th:nth-child(3) { width: 120px; }
.tbl-gp th:nth-child(4) { width: 100px; }
.tbl-gc th:nth-child(2) { width: 130px; }
.tbl-gc th:nth-child(3) { width: 110px; }
/* 排放预测 / CEA / CCER / 绿电 / 绿证 台账表：操作列都放「编辑 + 删」两个链接，
   （58px 会放不下「编辑」+「删」，末列被内容顶宽、按钮溢出到表格外） */
.tbl-fc th:last-child, .tbl-fc td:last-child,
.tbl-gp th:last-child, .tbl-gp td:last-child,
.tbl-gc th:last-child, .tbl-gc td:last-child,
.tbl-cea th:last-child, .tbl-cea td:last-child,
.tbl-ccer th:last-child, .tbl-ccer td:last-child { width: 84px; }
.tbl-cea th:nth-child(1) { width: 84px; }
/* CEA 表共 9 列（卖出/买入拆开后多一列）：把数量列全部钉住，
   否则固定布局会把数字摊到很宽的列里、彼此拉得很开 */
.tbl-cea th:nth-child(2), .tbl-cea th:nth-child(3), .tbl-cea th:nth-child(4) { width: 96px; }
.tbl-cea th:nth-child(5), .tbl-cea th:nth-child(6) { width: 88px; }
.tbl-cea th:nth-child(7) { width: 96px; }
.tbl-cea th:nth-child(8) { width: 92px; }
/* 可用配额是主指标：加粗 + 主色，一眼能在行里找到 */
.tbl-cea td.strong { font-weight: 700; color: var(--text); }
/* 表头单位另起一行（与交易流水表一致），避免「万吨 / 元/吨」混在一行里读错 */
.tbl-cea th em { display: block; font-style: normal; font-weight: 400; font-size: 9.5px; color: var(--faint); }
/* 合计行：tfoot 里单独一条，和明细拉开层级 */
.sum-row td {
  font-weight: 600; color: var(--text);
  background: var(--panel-2);
  border-top: 1px solid var(--border);
}
/* 行内小徽标：「替代」说明预分配是替代值、「流水」说明卖出/买入由交易流水汇总。
   类名不能叫 .tag —— 全局 .tag 是通用徽章（inline-flex + padding + border-radius !important），会串样式 */
.cea-tag {
  display: inline-block; font-style: normal; font-size: 9.5px; line-height: 1; vertical-align: 1px;
  margin-left: 4px; padding: 2px 4px; border-radius: 3px;
  background: var(--panel-2); border: 1px solid var(--border); color: var(--muted);
}
.cea-tag.src { color: var(--accent-d); border-color: var(--accent-d); }
/* CEA 页的年度作用域条：下拉选年度 + 一行可追溯的算式。
   类名不能用 .scope-bar —— 全局样式里已有同名类（进度条口径，height:4px + overflow:hidden），
   会把这条压成 4px 高、内容被裁掉 */
.cea-scope { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
.cea-scope .fld.inline { display: flex; align-items: center; gap: 6px; }
.cea-scope .fld.inline > .fl { font-size: 11px; color: var(--muted); white-space: nowrap; }
.cea-scope select { height: 26px; }
.scope-sum { font-size: 11.5px; color: var(--muted); }
.scope-sum b { color: var(--text); font-variant-numeric: tabular-nums; }
.scope-sum em { font-style: normal; color: var(--faint); margin-left: 6px; }
/* 悬空流水提示：登记了但归属年度没有对应持仓 —— 数字不会动，必须说清楚为什么 */
.scope-warn {
  font-size: 11px; line-height: 1.4; color: var(--yellow);
  background: rgba(191, 138, 0, 0.08);
  border: 1px dashed var(--yellow); border-radius: 4px; padding: 2px 8px;
  cursor: help;
}
/* 流水读取失败的警示条：后端缺 GET 接口时不能再「静默空表」，否则用户只会觉得登记没生效 */
.trade-warn {
  display: grid; gap: 3px; margin: 6px 0 8px; padding: 7px 10px;
  border: 1px solid var(--red); border-left-width: 3px; border-radius: 4px;
  background: rgba(188, 59, 48, 0.06);
  font-size: 11px; line-height: 1.55;
}
.trade-warn b { color: var(--red); font-weight: 600; }
.trade-warn em { font-style: normal; color: var(--muted); }
/* CEA 交易流水比 CCER 多一列「归属年度」，列宽单独覆盖（.tbl-trade 的 nth-child 是 6 列口径） */
.tbl-cea-trade th:nth-child(2) { width: 78px; }
.tbl-cea-trade th:nth-child(3) { width: 56px; }
.tbl-cea-trade th:nth-child(4), .tbl-cea-trade th:nth-child(5), .tbl-cea-trade th:nth-child(6) { width: 88px; }
.tbl-cea-trade th:last-child { width: 44px; }
/* CCER 交易流水 7 列：时间 | 方向 | 项目类型 | 数量 | 单价 | 金额 | 备注。
   与 CEA 流水表列宽对齐（同口径的列用同宽），「项目类型」是文字列给足宽度 */
.tbl-ccer-trade th:first-child { width: 118px; }
.tbl-ccer-trade th:nth-child(2) { width: 56px; }
.tbl-ccer-trade th:nth-child(3) { width: 96px; }
.tbl-ccer-trade th:nth-child(4), .tbl-ccer-trade th:nth-child(5), .tbl-ccer-trade th:nth-child(6) { width: 88px; }
.tbl-ccer-trade th:last-child { width: auto; }
.tbl-ccer th:nth-child(1), .tbl-ccer th:nth-child(2), .tbl-ccer th:nth-child(3) { width: 92px; }
.tbl-ccer th:nth-child(4), .tbl-ccer th:nth-child(5), .tbl-ccer th:nth-child(6) { width: 96px; }
.tbl-ccer th:nth-child(7) { width: 70px; }
.link { background: none; border: none; color: var(--accent-d); font-size: 12px; cursor: pointer; padding: 2px 6px; }
.link:hover { text-decoration: underline; }
.dim { color: var(--faint); }
.run-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.run-head strong { font-size: 14px; color: var(--text); }
.hint { font-size: 11px; color: var(--muted); margin-left: 8px; }
.run-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.chip {
  padding: 2px 10px; border-radius: 2px; background: var(--panel-2);
  border: 1px solid var(--border); font-size: 10px; color: var(--muted);
}
.chip.pos { color: var(--red); border-color: rgba(188, 59, 48, 0.4); }
.chip.neg { color: var(--green); border-color: rgba(46, 139, 87, 0.4); }
.plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.plan { padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); }
.plan h4 { margin: 0 0 10px; font-size: 13px; color: var(--text); }
.plan.conservative { border-top: 3px solid var(--accent); }
.plan.balanced { border-top: 3px solid var(--accent); }
.plan.aggressive { border-top: 3px solid var(--yellow); }
.plan-nums { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); margin-bottom: 10px; }
.plan-nums b { color: var(--text); font-weight: 600; }
.plan-nums b.ok { color: var(--green); }
.plan ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.plan li { font-size: 12px; color: var(--text); }
.plan li b { color: var(--text); font-weight: 600; }
.plan li .w { color: var(--muted); font-size: 11px; }
.empty-box { text-align: center; padding: 48px 0; color: var(--muted); display: grid; gap: 12px; justify-items: center; }
.empty-box p { margin: 0; }
tr.low td:first-child { color: var(--green); }
tr.medium td:first-child { color: var(--yellow); }
tr.high td:first-child { color: var(--red); }
td.msg { max-width: 320px; }

/* ===== 排放台账录入弹窗（新增 / 编辑共用）=====
   遮罩底色不用自己写：styles/main.css 里 `[class*="-mask"]` 已统一成中性暗场 + 背景模糊
   （浅色 .38 / 深色 .55 且带 !important），这里只需负责位置和层级 */
.em-mask {
  position: fixed; inset: 0; z-index: 400;
  display: flex; align-items: center; justify-content: center;
  /* 与平台确认弹窗（.cd-mask）统一：遮罩压暗背景，否则弹窗压在表格上看不清字段。
     遮罩本身不响应点击（关闭只能走 ✕ / 取消），见模板里的关闭规则注释 */
  background: rgba(0, 0, 0, .42);
}
.em-dialog {
  width: 620px; max-width: 94vw; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.38); overflow: hidden;
}
.em-head {
  display: flex; align-items: center; gap: 10px;
  padding: 11px 14px; border-bottom: 1px solid var(--line-soft); background: var(--panel-2);
}
.em-head b { font-size: 13px; font-weight: 600; letter-spacing: .2px; }
.em-ent { font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.em-x {
  margin-left: auto; width: 22px; height: 22px; flex: 0 0 22px; border-radius: 4px;
  border: 1px solid transparent; background: none; color: var(--muted); font-size: 12px; cursor: pointer;
}
.em-x:hover { background: var(--panel); border-color: var(--border); color: var(--text); }
.em-body { padding: 14px; }
.em-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
.em-grid .fld > span.fl { font-size: 11px; color: var(--muted); }
.em-grid .fld > span.fl em { font-style: normal; font-size: 10px; color: var(--faint); margin-left: 4px; }
.em-grid .fld input {
  width: 100%; box-sizing: border-box; height: 28px;
  border: 1px solid var(--border); border-radius: 5px; padding: 0 8px;
  background: var(--panel); color: var(--text); font-size: 12px;
}
.em-grid .fld input:focus { border-color: var(--accent); outline: none; }
.em-grid .fld input:disabled { background: var(--panel-2); color: var(--muted); cursor: not-allowed; }
.em-tip { margin: 11px 0 0; font-size: 11px; line-height: 1.5; color: var(--muted); }
/* 弹窗里的口径说明块：占满两列，左侧一道主色细边，提示「这个数怎么算出来的」 */
.em-note {
  font-size: 11px; line-height: 1.55; color: var(--muted);
  background: var(--panel-2); border: 1px solid var(--border);
  border-left: 2px solid var(--accent-d); border-radius: 4px;
  padding: 7px 10px;
}
.em-note.full { grid-column: 1 / -1; }
/* 弹窗里的复选框：与 28px 输入框等高，数字框和勾选框混排时不会一个高一个低 */
.em-grid .fld .em-check {
  display: flex; align-items: center; gap: 6px; height: 28px;
  font-size: 12px; color: var(--text); cursor: pointer;
}
.em-grid .fld .em-check input { width: auto; height: auto; margin: 0; }
.em-foot {
  display: flex; align-items: center; justify-content: flex-end; gap: 8px;
  padding: 10px 14px; border-top: 1px solid var(--line-soft); background: var(--panel-2);
}
.em-foot .btn { display: inline-flex; align-items: center; gap: 6px; height: 26px; }
/* 行内操作列：编辑 / 删 两个文字按钮并排，不再挤掉数字列的宽度 */
td.row-ops { white-space: nowrap; }
td.row-ops .link + .link { margin-left: 2px; }
.link.danger { color: var(--red); }
/* 页签行右上角的「+ 新增」用实心强调色，与其它页签的「编辑」开关区分开 */
.tabs .tabs-act.add { background: var(--accent); border-color: var(--accent-d); color: var(--on-accent); }
.tabs .tabs-act.add:hover { background: var(--accent-d); border-color: var(--accent-d); color: var(--on-accent); }
</style>
