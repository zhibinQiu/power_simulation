<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { carbonComplianceApi as api } from '../../api/carbonCompliance.js'

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
}
function loadAll() { loadMeta(); loadEnterprises() }
onMounted(loadAll)

defineExpose({ loadAll })

// ---------------- 企业 CRUD ----------------
const entForm = reactive({ name: '', uscc: '', industry: 'power', market_start_year: new Date().getFullYear() - 1, risk_profile: 'balanced', annual_budget_cap: 0, single_trade_limit: 0 })
const showEntForm = ref(false)
async function createEnterprise() {
  if (!entForm.name.trim()) return flashErr(new Error('请填写企业名称'))
  try {
    await api.createEnterprise({ ...entForm })
    showEntForm.value = false
    entForm.name = ''; entForm.uscc = ''
    await loadEnterprises()
    flashOk('企业已创建')
  } catch (e) { flashErr(e) }
}
async function deleteEnterprise() {
  if (!selectedId.value) return
  if (!confirm(`确认删除企业「${selected.value?.name || selectedId.value}」及其全部台账？`)) return
  try {
    await api.deleteEnterprise(selectedId.value)
    selectedId.value = ''
    await loadEnterprises()
    flashOk('企业已删除')
  } catch (e) { flashErr(e) }
}
async function updateEnterprise(patch) {
  if (!selectedId.value) return
  try {
    await api.updateEnterprise(selectedId.value, patch)
    await loadEnterprises()
    flashOk('企业已更新')
  } catch (e) { flashErr(e) }
}

// ---------------- 排放台账 ----------------
const emForm = reactive({ year: new Date().getFullYear(), verified_total: 0, scope1_combustion: 0, scope1_process: 0, scope2_power: 0, purchased_mwh: 0, historical_gap: null, ccer_used: 0 })
async function upsertEmission() {
  try {
    await api.upsertEmission(selectedId.value, { ...emForm })
    await loadSelected(); flashOk('排放台账已保存')
  } catch (e) { flashErr(e) }
}
async function delEmission(row) {
  if (!confirm(`删除 ${row.year} 年排放记录？`)) return
  try { await api.deleteEmission(selectedId.value, row.year); await loadSelected() } catch (e) { flashErr(e) }
}

// ---------------- 预测 ----------------
const fcForm = reactive({ year: new Date().getFullYear() + 1, forecast_total: 0, capacity_plan: '', production_plan: '', abatement_projects: [] })
async function upsertForecast() {
  try {
    await api.upsertForecast(selectedId.value, { ...fcForm, abatement_projects: fcForm.abatement_projects.filter(Boolean) })
    await loadSelected(); flashOk('排放预测已保存')
  } catch (e) { flashErr(e) }
}

// ---------------- CEA 台账 ----------------
const ceaForm = reactive({ vintage_year: new Date().getFullYear(), free_quota: 0, carry_forward_qty: 0, net_sell_qty: 0, avg_cost: 0, estimated_free_quota: 0 })
async function upsertCea() {
  try { await api.upsertCea(selectedId.value, { ...ceaForm }); await loadSelected(); flashOk('CEA 持仓已保存') }
  catch (e) { flashErr(e) }
}
async function delCea(row) {
  if (!confirm(`删除 ${row.vintage_year} 年度 CEA 持仓？`)) return
  try { await api.deleteCea(selectedId.value, row.vintage_year); await loadSelected() } catch (e) { flashErr(e) }
}
// 交易
const tradeForm = reactive({ side: 'buy', qty: 1, price: 80, note: '' })
const tradeKind = ref('cea')
async function addTrade() {
  const fn = tradeKind.value === 'cea' ? api.addCeaTrade : api.addCcerTrade
  try { await fn(selectedId.value, { ...tradeForm }); flashOk('交易已登记') }
  catch (e) { flashErr(e) }
}

// ---------------- CCER 台账 ----------------
const ccerForm = reactive({ project_type: 'forest', issue_year: new Date().getFullYear() - 1, expire_at: '', qty: 0, cost: 0, eligible_qty: null, linked_green_cert: false })
async function upsertCcer() {
  try { await api.upsertCcer(selectedId.value, { ...ccerForm }); await loadSelected(); flashOk('CCER 持仓已保存') }
  catch (e) { flashErr(e) }
}
async function delCcer(row) {
  if (!confirm(`删除 CCER 持仓（${row.project_type} ${row.issue_year}）？`)) return
  try { await api.deleteCcer(selectedId.value, row.id); await loadSelected() } catch (e) { flashErr(e) }
}

// ---------------- 绿电 / 绿证 ----------------
const gpForm = reactive({ year: new Date().getFullYear(), market_green_mwh: 0, self_gen_mwh: 0, premium_per_mwh: 0, contract_ref: '' })
async function upsertGp() {
  try { await api.upsertGreenPower(selectedId.value, { ...gpForm }); await loadSelected(); flashOk('绿电台账已保存') }
  catch (e) { flashErr(e) }
}
const gcForm = reactive({ year: new Date().getFullYear(), qty: 0, unit_price: 0, retired: false })
async function upsertGc() {
  try { await api.upsertGreenCert(selectedId.value, { ...gcForm }); await loadSelected(); flashOk('绿证台账已保存') }
  catch (e) { flashErr(e) }
}

// ---------------- 策略运行 ----------------
const runYear = ref(new Date().getFullYear())
const planLabels = { conservative: '保守', balanced: '平衡', aggressive: '进取' }
const actionLabels = { buy_cea: '购入 CEA', sell_cea: '出售 CEA', use_ccer: '使用自有 CCER', buy_ccer: '外购 CCER', hold: '持有不动', stockpile: '低位囤存' }
async function runStrategy() {
  if (!selectedId.value) return flashErr(new Error('请先选择企业'))
  running.value = true
  try {
    lastRun.value = await api.runStrategy(selectedId.value, Number(runYear.value))
    await loadSelected()
    tab.value = 'strategy'
    flashOk('策略已运行')
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
    flashOk(`导入完成：${JSON.stringify(res.counts || res)}`)
    await loadSelected()
  } catch (err) { flashErr(err) }
  e.target.value = ''
}

// ---------------- 派生统计 ----------------
const stats = computed(() => {
  const em = emissions.value.reduce((s, r) => s + (Number(r.verified_total) || 0), 0)
  const cea = ceaRows.value.reduce((s, r) => s + (Number(r.free_quota) || 0) + (Number(r.carry_forward_qty) || 0), 0)
  const ccer = ccerRows.value.reduce((s, r) => s + (Number(r.qty) || 0), 0)
  return { emissions: em, cea, ccer, gap: lastRun.value?.accounting_snapshot?.compliance_gap ?? null }
})
const gapClass = computed(() => {
  const g = stats.value.gap
  if (g === null) return ''
  return g > 0 ? 'gap-pos' : 'gap-neg'
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
          <span>控排企业（{{ enterprises.length }}）</span>
          <button class="mini" @click="showEntForm = !showEntForm">{{ showEntForm ? '收起' : '+ 新建' }}</button>
        </div>
        <div v-if="showEntForm" class="ent-form">
          <input v-model="entForm.name" placeholder="企业名称 *" />
          <input v-model="entForm.uscc" placeholder="统一社会信用代码" />
          <select v-model="entForm.industry">
            <option v-for="i in meta.industries" :key="i.value" :value="i.value">{{ i.label }}</option>
          </select>
          <div class="row2">
            <input v-model.number="entForm.market_start_year" type="number" placeholder="纳入年度" />
            <select v-model="entForm.risk_profile">
              <option v-for="r in meta.risk_profiles" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
          </div>
          <div class="row2">
            <input v-model.number="entForm.annual_budget_cap" type="number" placeholder="年度预算上限(元)" />
            <input v-model.number="entForm.single_trade_limit" type="number" placeholder="单笔限额(元)" />
          </div>
          <button class="btn primary block" @click="createEnterprise">创建企业</button>
        </div>
        <ul>
          <li
            v-for="e in enterprises"
            :key="e.id"
            :class="{ active: e.id === selectedId }"
            @click="selectedId = e.id; loadSelected()"
          >
            <div class="li-title">{{ e.name }}</div>
            <div class="li-meta">{{ industryLabel(e.industry) }} · {{ e.market_start_year }} 纳入</div>
          </li>
          <li v-if="!enterprises.length" class="empty">暂无企业，点击上方「+ 新建」</li>
        </ul>
      </aside>

      <!-- 右侧面板 -->
      <section class="detail">
        <div v-if="!selected" class="placeholder">
          <p>请选择或新建一个控排企业</p>
        </div>
        <template v-else>
          <div class="detail-head">
            <div>
              <h3>{{ selected.name }}</h3>
              <div class="meta-line">
                {{ industryLabel(selected.industry) }} · {{ riskLabel(selected.risk_profile) }} ·
                {{ selected.market_start_year }} 年纳入 · 预算 {{ Number(selected.annual_budget_cap || 0).toLocaleString() }} 元
              </div>
            </div>
            <div class="detail-actions">
              <select v-model="runYear" class="year-select" title="选择策略运行年度">
                <option v-for="y in [2024, 2025, 2026, 2027]" :key="y" :value="y">{{ y }} 年度</option>
              </select>
              <button class="btn primary" :disabled="running || !selectedId" @click="runStrategy">
                <span v-if="running" class="spinner"></span>
                {{ running ? '策略运行中…' : '运行履约策略' }}
              </button>
              <button class="btn" :disabled="!selectedId" @click="downloadTemplate">模板下载</button>
              <label class="btn file">
                台账导入
                <input type="file" accept=".xlsx,.xls" style="display:none" @change="importExcel" />
              </label>
              <button class="btn danger" :disabled="!selectedId" @click="deleteEnterprise">删除企业</button>
            </div>
          </div>

          <div class="stats-bar">
            <div class="stat"><span class="k">排放累计(万吨)</span><span class="v">{{ stats.emissions.toFixed(1) }}</span></div>
            <div class="stat"><span class="k">CEA 可用(万吨)</span><span class="v">{{ stats.cea.toFixed(1) }}</span></div>
            <div class="stat"><span class="k">CCER 存量(万吨)</span><span class="v">{{ stats.ccer.toFixed(1) }}</span></div>
            <div class="stat"><span class="k">履约缺口(万吨)</span><span class="v" :class="gapClass">{{ stats.gap === null ? '—' : stats.gap.toFixed(1) }}</span></div>
          </div>

          <div class="tabs">
            <button :class="{ active: tab === 'emissions' }" @click="tab = 'emissions'">排放台账</button>
            <button :class="{ active: tab === 'forecasts' }" @click="tab = 'forecasts'">排放预测</button>
            <button :class="{ active: tab === 'cea' }" @click="tab = 'cea'">CEA</button>
            <button :class="{ active: tab === 'ccer' }" @click="tab = 'ccer'">CCER</button>
            <button :class="{ active: tab === 'green' }" @click="tab = 'green'">绿电/绿证</button>
            <button :class="{ active: tab === 'strategy' }" @click="tab = 'strategy'">策略引擎</button>
            <button :class="{ active: tab === 'alerts' }" @click="tab = 'alerts'">预警<span v-if="alerts.filter(a => !a.acked).length" class="badge">{{ alerts.filter(a => !a.acked).length }}</span></button>
          </div>

          <!-- 排放台账 -->
          <div v-show="tab === 'emissions'" class="tab-body">
            <div class="form-grid">
              <input v-model.number="emForm.year" type="number" placeholder="年份" />
              <input v-model.number="emForm.verified_total" type="number" placeholder="核查排放(万吨)" />
              <input v-model.number="emForm.scope1_combustion" type="number" placeholder="范畴1-燃料燃烧" />
              <input v-model.number="emForm.scope1_process" type="number" placeholder="范畴1-工业过程" />
              <input v-model.number="emForm.scope2_power" type="number" placeholder="范畴2-净购电" />
              <input v-model.number="emForm.purchased_mwh" type="number" placeholder="净购入电量(万MWh)" />
              <input v-model.number="emForm.ccer_used" type="number" placeholder="当年CCER使用量" />
              <button class="btn primary" @click="upsertEmission">保存排放</button>
            </div>
            <table>
              <thead><tr><th>年份</th><th>核查排放</th><th>范畴1燃料</th><th>范畴1过程</th><th>范畴2电力</th><th>CCER已用</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in emissions" :key="r.id">
                  <td>{{ r.year }}</td><td>{{ Number(r.verified_total).toFixed(1) }}</td>
                  <td>{{ Number(r.scope1_combustion || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.scope1_process || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.scope2_power || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.ccer_used || 0).toFixed(1) }}</td>
                  <td><button class="link" @click="delEmission(r)">删</button></td>
                </tr>
                <tr v-if="!emissions.length" class="empty-row"><td colspan="7">暂无排放记录</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 排放预测 -->
          <div v-show="tab === 'forecasts'" class="tab-body">
            <div class="form-grid">
              <input v-model.number="fcForm.year" type="number" placeholder="预测年份" />
              <input v-model.number="fcForm.forecast_total" type="number" placeholder="预测排放(万吨)" />
              <input v-model="fcForm.capacity_plan" placeholder="产能计划" />
              <input v-model="fcForm.production_plan" placeholder="生产计划" />
              <button class="btn primary" @click="upsertForecast">保存预测</button>
            </div>
            <table>
              <thead><tr><th>年份</th><th>预测排放</th><th>产能计划</th><th>生产计划</th></tr></thead>
              <tbody>
                <tr v-for="r in forecasts" :key="r.id">
                  <td>{{ r.year }}</td><td>{{ Number(r.forecast_total).toFixed(1) }}</td>
                  <td>{{ r.capacity_plan || '—' }}</td><td>{{ r.production_plan || '—' }}</td>
                </tr>
                <tr v-if="!forecasts.length" class="empty-row"><td colspan="4">暂无预测记录</td></tr>
              </tbody>
            </table>
          </div>

          <!-- CEA -->
          <div v-show="tab === 'cea'" class="tab-body">
            <div class="form-grid">
              <input v-model.number="ceaForm.vintage_year" type="number" placeholder="配额年份" />
              <input v-model.number="ceaForm.free_quota" type="number" placeholder="免费配额(万吨)" />
              <input v-model.number="ceaForm.carry_forward_qty" type="number" placeholder="结转量(万吨)" />
              <input v-model.number="ceaForm.estimated_free_quota" type="number" placeholder="预分配配额(万吨)" />
              <input v-model.number="ceaForm.net_sell_qty" type="number" placeholder="净卖出(万吨)" />
              <input v-model.number="ceaForm.avg_cost" type="number" placeholder="平均成本(元/吨)" />
              <button class="btn primary" @click="upsertCea">保存 CEA</button>
            </div>
            <table>
              <thead><tr><th>配额年份</th><th>免费配额</th><th>结转量</th><th>预分配</th><th>净卖出</th><th>成本</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in ceaRows" :key="r.id">
                  <td>{{ r.vintage_year }}</td><td>{{ Number(r.free_quota).toFixed(1) }}</td>
                  <td>{{ Number(r.carry_forward_qty || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.estimated_free_quota || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.net_sell_qty || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.avg_cost || 0).toFixed(1) }}</td>
                  <td><button class="link" @click="delCea(r)">删</button></td>
                </tr>
                <tr v-if="!ceaRows.length" class="empty-row"><td colspan="7">暂无 CEA 持仓</td></tr>
              </tbody>
            </table>
            <div class="form-grid sub">
              <select v-model="tradeKind"><option value="cea">CEA 交易</option><option value="ccer">CCER 交易</option></select>
              <select v-model="tradeForm.side"><option value="buy">买入</option><option value="sell">卖出</option></select>
              <input v-model.number="tradeForm.qty" type="number" placeholder="数量(万吨)" />
              <input v-model.number="tradeForm.price" type="number" placeholder="单价(元/吨)" />
              <input v-model="tradeForm.note" placeholder="备注" />
              <button class="btn primary" @click="addTrade">登记交易</button>
            </div>
          </div>

          <!-- CCER -->
          <div v-show="tab === 'ccer'" class="tab-body">
            <div class="form-grid">
              <select v-model="ccerForm.project_type">
                <option value="forest">林业碳汇</option><option value="renewable">可再生能源</option>
                <option value="methane">甲烷利用</option><option value="general">其他</option>
              </select>
              <input v-model.number="ccerForm.issue_year" type="number" placeholder="签发年份" />
              <input v-model="ccerForm.expire_at" type="date" placeholder="到期日" />
              <input v-model.number="ccerForm.qty" type="number" placeholder="数量(万吨)" />
              <input v-model.number="ccerForm.cost" type="number" placeholder="成本(元/吨)" />
              <input v-model.number="ccerForm.eligible_qty" type="number" placeholder="可抵扣量(万吨)" />
              <label class="check"><input v-model="ccerForm.linked_green_cert" type="checkbox" /> 已关联绿证</label>
              <button class="btn primary" @click="upsertCcer">保存 CCER</button>
            </div>
            <table>
              <thead><tr><th>项目类型</th><th>签发年</th><th>到期日</th><th>数量</th><th>成本</th><th>可抵扣</th><th>绿证</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in ccerRows" :key="r.id">
                  <td>{{ r.project_type }}</td><td>{{ r.issue_year }}</td><td>{{ r.expire_at || '—' }}</td>
                  <td>{{ Number(r.qty).toFixed(1) }}</td><td>{{ Number(r.cost || 0).toFixed(1) }}</td>
                  <td>{{ r.eligible_qty === null || r.eligible_qty === undefined ? '—' : Number(r.eligible_qty).toFixed(1) }}</td>
                  <td>{{ r.linked_green_cert ? '是' : '—' }}</td>
                  <td><button class="link" @click="delCcer(r)">删</button></td>
                </tr>
                <tr v-if="!ccerRows.length" class="empty-row"><td colspan="8">暂无 CCER 持仓</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 绿电/绿证 -->
          <div v-show="tab === 'green'" class="tab-body">
            <div class="form-grid">
              <input v-model.number="gpForm.year" type="number" placeholder="年份" />
              <input v-model.number="gpForm.market_green_mwh" type="number" placeholder="市场绿电(万MWh)" />
              <input v-model.number="gpForm.self_gen_mwh" type="number" placeholder="自发自用(万MWh)" />
              <input v-model.number="gpForm.premium_per_mwh" type="number" placeholder="绿电溢价(元/MWh)" />
              <input v-model="gpForm.contract_ref" placeholder="合同编号" />
              <button class="btn primary" @click="upsertGp">保存绿电</button>
            </div>
            <table>
              <thead><tr><th>年份</th><th>市场绿电</th><th>自发自用</th><th>溢价</th><th>合同</th></tr></thead>
              <tbody>
                <tr v-for="r in greenPower" :key="r.id">
                  <td>{{ r.year }}</td><td>{{ Number(r.market_green_mwh || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.self_gen_mwh || 0).toFixed(1) }}</td>
                  <td>{{ Number(r.premium_per_mwh || 0).toFixed(1) }}</td><td>{{ r.contract_ref || '—' }}</td>
                </tr>
                <tr v-if="!greenPower.length" class="empty-row"><td colspan="5">暂无绿电记录</td></tr>
              </tbody>
            </table>
            <div class="form-grid">
              <input v-model.number="gcForm.year" type="number" placeholder="年份" />
              <input v-model.number="gcForm.qty" type="number" placeholder="数量(万张)" />
              <input v-model.number="gcForm.unit_price" type="number" placeholder="单价(元/张)" />
              <label class="check"><input v-model="gcForm.retired" type="checkbox" /> 已注销</label>
              <button class="btn primary" @click="upsertGc">保存绿证</button>
            </div>
            <table>
              <thead><tr><th>年份</th><th>数量</th><th>单价</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="r in greenCerts" :key="r.id">
                  <td>{{ r.year }}</td><td>{{ Number(r.qty).toFixed(1) }}</td>
                  <td>{{ Number(r.unit_price || 0).toFixed(1) }}</td><td>{{ r.retired ? '已注销' : '持有' }}</td>
                </tr>
                <tr v-if="!greenCerts.length" class="empty-row"><td colspan="4">暂无绿证记录</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 策略引擎 -->
          <div v-show="tab === 'strategy'" class="tab-body">
            <div class="run-head">
              <div>
                <strong>{{ runYear }} 年度策略</strong>
                <span class="hint">口径：保守 / 平衡 / 进取 三档 + 价格窗口 + 结转测算</span>
              </div>
              <button class="btn primary" :disabled="running" @click="runStrategy">
                <span v-if="running" class="spinner"></span>重新运行
              </button>
            </div>
            <div v-if="lastRun" class="run-result">
              <div class="run-meta">
                <span class="chip">窗口：{{ lastRun.market_tags?.time_window || '—' }}</span>
                <span class="chip">价格带：{{ lastRun.market_tags?.price_band || '—' }}</span>
                <span class="chip">动作：{{ lastRun.market_tags?.action_tag || '—' }}</span>
                <span class="chip">CCER 上限：{{ lastRun.accounting_snapshot?.ccer_cap ?? '—' }}</span>
                <span class="chip" :class="(lastRun.accounting_snapshot?.compliance_gap || 0) > 0 ? 'pos' : 'neg'">
                  缺口：{{ Number(lastRun.accounting_snapshot?.compliance_gap || 0).toFixed(1) }} 万吨
                </span>
              </div>
              <div class="plans">
                <div v-for="(label, key) in planLabels" :key="key" class="plan" :class="key">
                  <h4>{{ label }}方案</h4>
                  <div class="plan-nums">
                    <span>总成本 <b>{{ Number((lastRun.plans || []).find(p => p.key === key)?.total_cost || 0).toLocaleString() }}</b> 元</span>
                    <span>净节约 <b class="ok">{{ Number((lastRun.plans || []).find(p => p.key === key)?.net_saving || 0).toLocaleString() }}</b> 元</span>
                  </div>
                  <ul>
                    <li v-for="a in ((lastRun.plans || []).find(p => p.key === key)?.actions || [])" :key="a.action + a.window">
                      {{ actionLabels[a.action] || a.action }}：
                      <b>{{ Number(a.qty).toFixed(1) }} 万吨</b> @ {{ Number(a.unit_price).toFixed(1) }} 元/吨
                      <span class="w">({{ a.window }})</span>
                    </li>
                    <li v-if="!((lastRun.plans || []).find(p => p.key === key)?.actions || []).length" class="dim">—</li>
                  </ul>
                </div>
              </div>
            </div>
            <div v-else-if="runs.length" class="run-history">
              <p class="hint">最近一次运行：</p>
              <table>
                <thead><tr><th>运行时间</th><th>年度</th><th>缺口(万吨)</th><th>窗口</th><th>价格带</th><th>计划数</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="r in runs.slice(0, 5)" :key="r.id">
                    <td>{{ r.created_at }}</td><td>{{ r.compliance_year }}</td>
                    <td>{{ Number(r.accounting_snapshot?.compliance_gap || 0).toFixed(1) }}</td>
                    <td>{{ r.market_tags?.time_window || '—' }}</td>
                    <td>{{ r.market_tags?.price_band || '—' }}</td>
                    <td>{{ (r.plans || []).length }}</td>
                    <td><button class="link" @click="api.downloadStrategyRun(selectedId, r.id)">下载</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-box">
              <p>尚未运行策略</p>
              <button class="btn primary" @click="runStrategy">立即运行 {{ runYear }} 年度策略</button>
            </div>
          </div>

          <!-- 预警 -->
          <div v-show="tab === 'alerts'" class="tab-body">
            <table>
              <thead><tr><th>级别</th><th>类型</th><th>内容</th><th>触发时间</th><th>到期</th><th></th></tr></thead>
              <tbody>
                <tr v-for="a in alerts" :key="a.id" :class="a.level">
                  <td>{{ a.level }}</td><td>{{ a.alert_type }}</td>
                  <td class="msg">{{ a.message }}</td>
                  <td>{{ a.created_at }}</td><td>{{ a.due_at || '—' }}</td>
                  <td>
                    <button v-if="!a.acked" class="link" @click="ackAlert(a)">已处理</button>
                    <span v-else class="dim">已确认</span>
                  </td>
                </tr>
                <tr v-if="!alerts.length" class="empty-row"><td colspan="6">暂无预警</td></tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
    </div>
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
  height: 24px;
}
.btn {
  padding: 3px 12px;
  border-radius: 5px;
  border: 1px solid var(--accent-l);
  background: var(--accent-l);
  color: var(--accent);
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: border-color .15s, background .15s, color .15s;
}
.btn:hover { border-color: var(--accent); color: var(--accent-d); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.btn.primary:hover { background: var(--accent-d); border-color: var(--accent-d); color: #fff; }
.btn.danger { background: rgba(209, 75, 75, 0.1); border-color: rgba(209, 75, 75, 0.3); color: var(--red); }
.btn.danger:hover { border-color: var(--red); background: rgba(209, 75, 75, 0.18); color: var(--red); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.file { position: relative; }
.spinner {
  width: 11px; height: 11px; border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff; border-radius: 50%; animation: spin 0.8s linear infinite;
}
.btn:not(.primary) .spinner { border-color: var(--muted); border-top-color: var(--text); }
@keyframes spin { to { transform: rotate(360deg); } }
.flash {
  margin: 8px 14px 0; padding: 6px 10px; border-radius: 4px; font-size: 12px;
}
.flash.ok { background: rgba(46, 158, 99, 0.1); color: var(--green); border: 1px solid rgba(46, 158, 99, 0.35); }
.flash.err { background: rgba(209, 75, 75, 0.1); color: var(--red); border: 1px solid rgba(209, 75, 75, 0.35); }
.layout { flex: 1; display: flex; min-height: 0; }
/* 左侧企业列表：VS Code 资源管理器风格 */
.ent-list {
  width: 240px; border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow-y: auto; background: var(--panel-2);
}
.ent-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; font-size: 11px; color: var(--muted); font-weight: 600;
  border-bottom: 1px solid var(--border); background: var(--panel-2);
}
.mini {
  background: var(--accent-l); border: 1px solid var(--accent-l); color: var(--accent);
  font-size: 10.5px; padding: 2px 10px; border-radius: 5px; cursor: pointer; height: 22px;
  transition: border-color .15s;
}
.mini:hover { border-color: var(--accent); }
.ent-form { padding: 10px 12px; display: grid; gap: 6px; border-bottom: 1px solid var(--border); }
.ent-form input, .ent-form select, .form-grid input, .form-grid select {
  padding: 4px 8px; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 5px; color: var(--text); font-size: 11px; outline: none;
}
.ent-form input:focus, .ent-form select:focus, .form-grid input:focus, .form-grid select:focus {
  border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-l);
}
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.block { width: 100%; }
.ent-list ul { list-style: none; margin: 0; padding: 4px 6px; }
.ent-list li { position: relative; padding: 8px 10px; border-radius: 4px; cursor: pointer; border: 1px solid transparent; }
.ent-list li:hover { background: var(--panel-3); }
.ent-list li.active { background: var(--sel); }
.ent-list li.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent);
}
.li-title { font-size: 12.5px; font-weight: 600; color: var(--text); }
.li-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
.ent-list .empty { color: var(--muted); font-size: 12px; text-align: center; cursor: default; }
.detail {
  flex: 1; display: flex; flex-direction: column; min-height: 0; overflow-y: auto;
  padding: 14px 16px; background: var(--panel-2);
}
.placeholder { flex: 1; display: grid; place-items: center; color: var(--faint); font-size: 14px; }
.detail-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.detail-head h3 { margin: 0 0 4px; font-size: 16px; font-weight: 600; color: var(--text); }
.meta-line { font-size: 12px; color: var(--muted); }
.detail-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.stats-bar { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.stat {
  padding: 8px 12px; border-radius: 6px; background: var(--panel-2);
  border: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px;
}
.stat .k { font-size: 10px; color: var(--muted); letter-spacing: .3px; }
.stat .v {
  font-size: 16px; font-weight: 600; color: var(--accent2);
  font-family: var(--mono); font-variant-numeric: tabular-nums;
}
.stat .v.gap-pos { color: var(--red); }
.stat .v.gap-neg { color: var(--green); }
/* 二级页签：VS Code tab 顶部指示条风格 */
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 12px; flex-wrap: wrap; }
.tabs button {
  position: relative; padding: 7px 12px; background: transparent; border: none;
  color: var(--muted); font-size: 12px; cursor: pointer; border-radius: 0;
}
.tabs button::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: transparent;
}
.tabs button:hover { color: var(--text); background: var(--panel-2); }
.tabs button.active { color: var(--accent-d); font-weight: 600; background: var(--panel); }
.tabs button.active::before { background: var(--accent); }
.badge {
  display: inline-block; min-width: 16px; height: 16px; padding: 0 4px; margin-left: 5px;
  background: var(--red); color: #fff; border-radius: 999px; font-size: 10px; line-height: 16px; text-align: center;
}
.tab-body { animation: fade 0.2s ease; }
@keyframes fade { from { opacity: 0 } to { opacity: 1 } }
.form-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px; margin-bottom: 14px; align-items: end;
}
.form-grid.sub { margin-top: 18px; border-top: 1px dashed var(--border); padding-top: 12px; }
.form-grid .btn { grid-column: span 1; height: 24px; }
.check {
  display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted);
  align-self: center; padding: 0; min-height: 24px;
}
.check input { width: auto; height: auto; margin: 0; flex-shrink: 0; }
/* 表格：参照 cbx-table（紧凑 10.5px + 表头灰底 + 圆角边框容器） */
table {
  width: 100%; border-collapse: collapse; font-size: 10.5px;
  border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); }
tbody tr:last-child td { border-bottom: none; }
th { color: var(--muted); font-weight: 500; font-size: 10px; background: var(--panel-2); letter-spacing: .3px; }
tbody tr:hover td { background: var(--panel-2); }
.empty-row td { text-align: center; color: var(--faint); padding: 22px; }
.link { background: none; border: none; color: var(--accent); font-size: 12px; cursor: pointer; padding: 2px 6px; }
.link:hover { text-decoration: underline; }
.dim { color: var(--faint); }
.run-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.run-head strong { font-size: 14px; color: var(--text); }
.hint { font-size: 11px; color: var(--muted); margin-left: 8px; }
.run-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.chip {
  padding: 2px 10px; border-radius: 999px; background: var(--panel-2);
  border: 1px solid var(--border); font-size: 10px; color: var(--muted);
}
.chip.pos { color: var(--red); border-color: rgba(209, 75, 75, 0.4); }
.chip.neg { color: var(--green); border-color: rgba(46, 158, 99, 0.4); }
.plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.plan { padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); }
.plan h4 { margin: 0 0 10px; font-size: 13px; color: var(--text); }
.plan.conservative { border-top: 3px solid #4a86d6; }
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
</style>
