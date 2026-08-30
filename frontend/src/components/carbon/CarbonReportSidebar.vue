<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { carbonAssistantApi } from '../../api/carbonAssistant.js'
import { carbonComplianceApi } from '../../api/carbonCompliance.js'
import { renderMarkdown, parseToc } from '../../utils/markdown.js'
import { t } from '../../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(props.modelValue)
watch(() => props.modelValue, v => { open.value = v })
watch(open, v => { emit('update:modelValue', v) })

// ---------- 表单 ----------
const typeLabels = {
  market_brief: '碳交易简报',
  policy_digest: '政策摘要',
  compliance_analysis: '履约综合分析',
}
const methodLabels = {
  linear: '线性回归（最小二乘）',
  moving_average: '移动平均（水平外推）',
  exponential: '指数平滑 SES（水平外推）',
}
const typeOptions = [
  { key: 'compliance_analysis', label: '履约综合分析', desc: '持仓、缺口、策略、预测、减排路径全流程分析' },
  { key: 'market_brief', label: '碳交易简报', desc: '聚焦 CEA/CCER 价格、成交与近期交易信号' },
  { key: 'policy_digest', label: '政策摘要', desc: '梳理近期政策要点与对企业履约交易的影响' },
]
const methodOptions = [
  { key: 'linear', label: '线性回归', desc: '按历史趋势外推，含置信区间' },
  { key: 'moving_average', label: '移动平均', desc: '最近 20 日移动平均水平外推' },
  { key: 'exponential', label: '指数平滑', desc: 'SES 平滑后水平外推' },
]

const reportType = ref('compliance_analysis')
const forecastMethod = ref('linear')
const title = ref(t('碳资产管理综合分析报告'))
const period = ref('2026年度')
const focus = ref(['compliance', 'trading'])
const extra = ref('')
// 履约综合分析专属：目标企业 + 履约年份
const enterprises = ref([])
const enterpriseId = ref('')
const complianceYear = ref(2026)
async function loadEnterprises() {
  try {
    enterprises.value = await carbonComplianceApi.listEnterprises()
    if (enterprises.value.length && !enterprises.value.find(e => e.id === enterpriseId.value)) {
      enterpriseId.value = enterprises.value[0].id
    }
  } catch (e) {
    console.warn('企业列表加载失败', e)
  }
}
function matchYear() {
  const m = String(period.value).match(/20\d{2}/)
  if (m) complianceYear.value = Number(m[0])
}

const focusOptions = [
  { key: 'compliance', label: '履约合规' },
  { key: 'trading', label: '交易策略' },
  { key: 'forecast', label: '价格预测' },
  { key: 'policy', label: '政策研判' },
  { key: 'reduction', label: '减排路径' },
]

// 切换报告类型/周期时同步默认标题（仅当用户未自定义标题时）
let prevDefaultTitle = '2026年度 碳资产管理综合分析'
function syncDefaultTitle() {
  const prefix = { market_brief: '碳交易市场简报', policy_digest: '双碳政策动态摘要', compliance_analysis: '碳资产管理综合分析' }[reportType.value]
  const def = `${period.value} ${prefix}`
  if (!title.value.trim() || title.value === prevDefaultTitle) title.value = def
  prevDefaultTitle = def
}
watch([reportType, period], syncDefaultTitle)
watch(period, matchYear)
// 履约综合分析必须选择企业，否则提示
watch(reportType, (v) => {
  if (v === 'compliance_analysis' && !enterprises.value.length) loadEnterprises()
})
function toggleFocus(key) {
  const idx = focus.value.indexOf(key)
  if (idx >= 0) focus.value.splice(idx, 1)
  else focus.value.push(key)
}

// ---------- 任务跟踪 ----------
const submitting = ref(false)
const statusMsg = ref('')
const trackingTask = ref(null)
let pollTimer = null

async function startAnalysis() {
  if (submitting.value) return
  if (reportType.value === 'compliance_analysis' && !enterpriseId.value) {
    statusMsg.value = t('履约综合分析需要先选择控排企业')
    return
  }
  submitting.value = true
  statusMsg.value = ''
  try {
    const res = await carbonAssistantApi.submitReport({
      title: title.value,
      period: period.value,
      report_type: reportType.value,
      forecast_method: forecastMethod.value,
      focus: focus.value,
      extra: extra.value,
      enterprise_id: reportType.value === 'compliance_analysis' ? enterpriseId.value : '',
      compliance_year: reportType.value === 'compliance_analysis' ? complianceYear.value : null,
    })
    trackingTask.value = res
    statusMsg.value = t('任务已提交（{task_id}），正在生成…', { task_id: res.task_id })
    pollTask(res.task_id)
  } catch (e) {
    statusMsg.value = t('提交失败：') + e.message
    submitting.value = false
  }
}

function pollTask(taskId) {
  clearPoll()
  pollTimer = setInterval(async () => {
    try {
      const t = await carbonAssistantApi.getTask(taskId)
      trackingTask.value = t
      if (['completed', 'failed', 'cancelled'].includes(t.status)) {
        clearPoll()
        submitting.value = false
        if (t.status === 'completed' && t.report_id) {
          statusMsg.value = t('报告生成完成')
          await loadReports()
          await showReport(t.report_id)
        } else if (t.status === 'failed') {
          statusMsg.value = t('生成失败：') + (t.message || t('未知错误'))
        } else {
          statusMsg.value = t('任务已取消')
        }
      }
    } catch (e) {
      clearPoll()
      submitting.value = false
      statusMsg.value = t('任务查询失败：') + e.message
    }
  }, 1500)
}

async function cancelRunning() {
  if (!trackingTask.value) return
  try {
    await carbonAssistantApi.cancelTask(trackingTask.value.task_id)
    statusMsg.value = t('正在取消任务…')
  } catch (e) {
    statusMsg.value = t('取消失败：') + e.message
  }
}

function clearPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ---------- 历史报告：搜索 / 筛选 / 分页 ----------
const reports = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 8
const keyword = ref('')
const typeFilter = ref('')

async function loadReports() {
  try {
    const data = await carbonAssistantApi.listReports({
      keyword: keyword.value,
      report_type: typeFilter.value,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    reports.value = data.reports || []
    total.value = data.total || 0
  } catch (e) {
    console.error('加载报告列表失败', e)
  }
}

function search() { page.value = 1; loadReports() }
function prevPage() { if (page.value > 1) { page.value -= 1; loadReports() } }
function nextPage() { if (page.value * pageSize < total.value) { page.value += 1; loadReports() } }

// ---------- 预览 / 摘要 ----------
const selected = ref(null)
const preview = ref('')
const summary = ref('')

async function showReport(id) {
  selected.value = id
  try {
    const data = await carbonAssistantApi.getReport(id)
    const md = data.markdown || data.content || t('无内容')
    preview.value = md
    summary.value = extractSummary(md)
  } catch (e) {
    preview.value = t('读取报告失败：') + e.message
    summary.value = ''
  }
}

// 报告正文渲染为 HTML（vscode 风格 markdown，标题带锚点供目录跳转）
const previewHtml = computed(() => renderMarkdown(preview.value, { headingIds: true }))
// 标题目录（大纲）
const toc = computed(() => parseToc(preview.value))
function scrollToHeading(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 解析「先看结论 / 执行摘要」章节的第一段作为结论卡片
function extractSummary(md) {
  const lines = String(md || '').split('\n')
  const heads = ['先看结论', '执行摘要', '摘要']
  let collecting = false
  const buf = []
  for (const line of lines) {
    const m = line.match(/^#{2,4}\s*(.*)$/)
    if (m) {
      const t = m[1].replace(/^\d+[\.、]?\s*/, '').trim()
      if (collecting) break
      if (heads.some(h => t.includes(h))) { collecting = true; continue }
    }
    if (collecting) {
      const s = line.replace(/^[-*>]\s*/, '').trim()
      if (s) buf.push(s)
      if (buf.length >= 3) break
    }
  }
  const text = buf.join(' ').replace(/\s+/g, ' ')
  return text ? text.slice(0, 260) : ''
}

async function removeReport(id) {
  try {
    await carbonAssistantApi.deleteReport(id)
    if (selected.value === id) { selected.value = null; preview.value = ''; summary.value = '' }
    await loadReports()
  } catch (e) {
    statusMsg.value = t('删除失败：') + e.message
  }
}

function downloadReport(id, titleText) {
  const a = document.createElement('a')
  a.href = `/api/carbon-assistant/reports/${id}/download`
  a.download = `${titleText || t('碳资产报告')}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function viewHtml(id) {
  window.open(carbonAssistantApi.viewReportUrl(id), '_blank')
}

onMounted(() => { loadReports(); loadEnterprises() })
onBeforeUnmount(clearPoll)
</script>

<template>
  <Transition name="slide">
    <div v-if="open" class="carbon-report-sidebar" @click.stop>
      <div class="header">
        <h3>{{ t('碳资产报告中心') }}</h3>
        <button class="x-btn lg" @click="open = false" :aria-label="t('关闭')">×</button>
      </div>

      <div class="body">
        <!-- 生成新报告 -->
        <section class="section">
          <h4>{{ t('生成新报告') }}</h4>

          <div class="field">
            <span>{{ t('报告类型') }}</span>
            <div class="opt-cards">
              <button
                v-for="opt in typeOptions"
                :key="opt.key"
                :class="['opt-card', { active: reportType === opt.key }]"
                @click="reportType = opt.key"
              >
                <div class="opt-name">{{ t(opt.label) }}</div>
                <div class="opt-desc">{{ t(opt.desc) }}</div>
              </button>
            </div>
          </div>

          <div class="field">
            <span>{{ t('价格预测方法') }}</span>
            <div class="opt-cards inline">
              <button
                v-for="opt in methodOptions"
                :key="opt.key"
                :class="['opt-card', 'mini', { active: forecastMethod === opt.key }]"
                :title="t(opt.desc)"
                @click="forecastMethod = opt.key"
              >{{ t(opt.label) }}</button>
            </div>
          </div>

          <label class="field">
            <span>{{ t('报告标题') }}</span>
            <input v-model="title" type="text" :placeholder="t('例如：2026年度碳资产管理综合分析报告')" />
          </label>
          <label class="field">
            <span>{{ t('核算周期') }}</span>
            <input v-model="period" type="text" :placeholder="t('例如：2026年度')" />
          </label>
          <div v-if="reportType === 'compliance_analysis'" class="field">
            <span>{{ t('控排企业') }}（{{ t('履约综合分析必选') }}）</span>
            <select v-model="enterpriseId">
              <option value="" disabled>{{ t('请选择企业') }}</option>
              <option v-for="e in enterprises" :key="e.id" :value="e.id">{{ e.name }}</option>
            </select>
            <div class="sub-hint">{{ t('履约年份按核算周期中的年份自动识别') }}（{{ complianceYear }} {{ t('年') }}）</div>
          </div>
          <div class="field">
            <span>{{ t('分析重点') }}</span>
            <div class="tags">
              <button
                v-for="opt in focusOptions"
                :key="opt.key"
                :class="['tag', { active: focus.includes(opt.key) }]"
                @click="toggleFocus(opt.key)"
              >{{ t(opt.label) }}</button>
            </div>
          </div>
          <label class="field">
            <span>{{ t('补充说明') }}</span>
            <textarea v-model="extra" rows="3" :placeholder="t('补充企业背景、减排目标、CCER计划等…')"></textarea>
          </label>

          <button class="submit" :disabled="submitting" @click="startAnalysis">
            <span v-if="submitting" class="spinner"></span>
            {{ submitting ? t('生成中…') : t('生成碳资产报告') }}
          </button>
          <div v-if="statusMsg" class="status">{{ statusMsg }}</div>
        </section>

        <!-- 运行中任务 -->
        <section v-if="trackingTask" class="section">
          <h4>{{ t('运行中任务') }}</h4>
          <div class="task-card" :class="trackingTask.status">
            <div class="task-head">
              <span class="task-title">{{ trackingTask.title }}</span>
              <span class="task-state" :class="trackingTask.status">
                {{ { pending: t('排队中'), running: t('生成中'), completed: t('完成'), failed: t('失败'), cancelled: t('已取消') }[trackingTask.status] || trackingTask.status }}
              </span>
            </div>
            <div class="progress">
              <div class="progress-bar" :style="{ width: (trackingTask.progress || 0) + '%' }"></div>
            </div>
            <div class="task-foot">
              <span class="task-msg">{{ trackingTask.message }}</span>
              <span class="task-pct">{{ trackingTask.progress || 0 }}%</span>
              <button
                v-if="['pending', 'running'].includes(trackingTask.status)"
                class="cancel"
                @click="cancelRunning"
              >{{ t('取消') }}</button>
            </div>
          </div>
        </section>

        <!-- 历史报告 -->
        <section class="section">
          <h4>{{ t('历史报告') }}（{{ total }}）</h4>
          <div class="filters">
            <input
              v-model="keyword"
              type="text"
              class="search"
              :placeholder="t('搜索标题 / 场景…')"
              @keyup.enter="search"
            />
            <select v-model="typeFilter" @change="search">
              <option value="">{{ t('全部类型') }}</option>
              <option v-for="(label, key) in typeLabels" :key="key" :value="key">{{ t(label) }}</option>
            </select>
            <button class="mini-btn" @click="search">{{ t('搜索') }}</button>
          </div>

          <ul class="report-list">
            <li v-for="r in reports" :key="r.id" :class="{ active: selected === r.id }">
              <div class="info" @click="showReport(r.id)">
                <div class="title">
                  <span class="type-tag" :class="r.report_type">{{ typeLabels[r.report_type] ? t(typeLabels[r.report_type]) : t('报告') }}</span>
                  {{ r.title }}
                </div>
                <div class="meta">{{ r.created_at }} · {{ r.length }} {{ t('字') }}</div>
              </div>
              <div class="actions">
                <button @click="viewHtml(r.id)" :title="t('HTML 阅读页查看')">📖</button>
                <button @click="downloadReport(r.id, r.title)" :title="t('下载 Markdown')">⬇</button>
                <button @click="removeReport(r.id)" :title="t('删除')">🗑</button>
              </div>
            </li>
            <li v-if="!reports.length" class="empty">{{ t('暂无报告') }}</li>
          </ul>

          <div v-if="total > pageSize" class="pager">
            <button :disabled="page <= 1" @click="prevPage">{{ t('上一页') }}</button>
            <span>{{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }}</span>
            <button :disabled="page * pageSize >= total" @click="nextPage">{{ t('下一页') }}</button>
          </div>
        </section>

        <!-- 结论摘要 + 预览 -->
        <section v-if="summary" class="section">
          <h4>{{ t('先看结论') }}</h4>
          <div class="summary">{{ summary }}</div>
        </section>

        <section v-if="preview" class="section preview">
          <h4>{{ t('报告预览') }}</h4>
          <!-- 目录（大纲）：vscode 风格 outline，点击滚动到对应章节 -->
          <nav v-if="toc.length" class="report-toc">
            <div class="toc-title">{{ t('目录') }}</div>
            <button v-for="item in toc" :key="item.id" class="toc-item" :class="'lvl' + item.level" @click="scrollToHeading(item.id)">
              {{ item.text }}
            </button>
          </nav>
          <div class="report-md" v-html="previewHtml"></div>
        </section>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ===== VS Code 风格：扁平化，全部复用系统 CSS 变量（浅色工业风 / sim-dark 自动适配） ===== */
.carbon-report-sidebar {
  position: absolute;
  top: 0;
  right: 0;
  width: 440px;
  max-width: 92vw;
  height: 100%;
  background: var(--panel);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  color: var(--text);
  /* 抽屉覆盖顶层：高于视图 Tab 栏(z-index:70)与内容区 */
  z-index: 80;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}
.header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
}
.section { margin-bottom: 20px; }
.section h4 {
  margin: 0 0 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--muted);
  border-left: 3px solid var(--accent);
  padding-left: 8px;
}
.field {
  display: block;
  margin-bottom: 10px;
}
.field > span {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 5px;
}
.field input,
.field textarea,
.filters input,
.filters select {
  width: 100%;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--text);
  font-size: 12px;
  outline: none;
}
.field input:focus,
.field textarea:focus,
.filters input:focus {
  border-color: var(--accent-d);
  box-shadow: 0 0 0 1px var(--accent-l);
}
.field select {
  width: 100%;
  min-width: 130px;
}
.sub-hint {
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}
/* 类型 / 方法选择卡片 */
.opt-cards {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.opt-cards.inline {
  flex-direction: row;
  flex-wrap: wrap;
}
.opt-card {
  text-align: left;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-2);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
}
.opt-card:hover { border-color: var(--accent-d); }
.opt-card.active {
  background: var(--accent-l);
  border-color: var(--accent-d);
  color: var(--accent-d);
}
.opt-card .opt-name { font-size: 12px; font-weight: 600; }
.opt-card .opt-desc { font-size: 11px; color: var(--muted); margin-top: 2px; }
.opt-card.mini { padding: 4px 10px; font-size: 12px; }
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 2px;
  background: var(--panel-2);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.tag.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent-d);
}
.submit {
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.submit:hover { background: var(--accent-d); }
.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.status {
  margin-top: 8px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}
/* 运行中任务卡片 */
.task-card {
  padding: 10px 12px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-title {
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-state {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 2px;
  background: var(--panel-3);
  color: var(--muted);
  flex-shrink: 0;
}
.task-state.running { background: var(--accent-l); color: var(--accent-d); }
.task-state.completed { background: rgba(46, 139, 87, 0.14); color: var(--green); }
.task-state.failed { background: rgba(188, 59, 48, 0.14); color: var(--red); }
.task-state.cancelled { background: var(--panel-3); color: var(--muted); }
.progress {
  height: 4px;
  margin: 8px 0 6px;
  background: var(--line);
  border-radius: 2px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.4s ease;
}
.task-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
}
.task-msg { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-pct { color: var(--accent-d); font-weight: 600; }
.cancel {
  padding: 2px 10px;
  border: 1px solid rgba(188, 59, 48, 0.5);
  border-radius: 4px;
  background: transparent;
  color: var(--red);
  font-size: 11px;
  cursor: pointer;
}
.cancel:hover { background: rgba(188, 59, 48, 0.12); }
/* 筛选 */
.filters {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
.filters .search { flex: 1; font-size: 12px; }
.filters select { font-size: 12px; }
.mini-btn {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}
.mini-btn:hover { border-color: var(--accent-d); color: var(--accent-d); }
/* 报告列表 */
.report-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.report-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  margin-bottom: 6px;
  background: var(--panel-2);
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}
.report-list li.active { border-color: var(--accent-d); background: var(--accent-l); }
.report-list li:hover:not(.active) { border-color: var(--border); background: var(--panel-3); }
.report-list .info {
  flex: 1;
  min-width: 0;
}
.report-list .title {
  font-size: 12.5px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.type-tag {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  margin-right: 6px;
  background: var(--accent-l);
  color: var(--accent-d);
  vertical-align: 1px;
}
.type-tag.market_brief { background: rgba(201, 154, 46, 0.15); color: #9a731f; }
.type-tag.policy_digest { background: rgba(95, 130, 148, 0.16); color: var(--accent2); }
.report-list .meta {
  font-size: 11px;
  color: var(--muted);
  margin-top: 3px;
}
.report-list .actions button {
  background: transparent;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  padding: 3px;
  border-radius: 3px;
}
.report-list .actions button:hover { color: var(--accent-d); background: var(--panel-3); }
.empty {
  color: var(--muted);
  font-size: 12px;
  text-align: center;
  cursor: default !important;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}
.pager button {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}
.pager button:disabled { opacity: 0.4; cursor: not-allowed; }
/* 结论摘要 */
.summary {
  padding: 10px 12px;
  background: var(--accent-l);
  border: 1px solid rgba(0, 94, 148, 0.35);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.7;
}
/* 目录（大纲） */
.report-toc {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 6px;
  margin-bottom: 10px;
  max-height: 240px;
  overflow: auto;
}
.toc-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--muted);
  padding: 0 8px 6px;
  text-transform: uppercase;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
}
.toc-item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.9;
  padding: 1px 8px;
  cursor: pointer;
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.toc-item:hover {
  color: var(--accent-d);
  background: var(--panel-3);
}
.toc-item.lvl1 { padding-left: 8px; font-weight: 600; color: var(--text); }
.toc-item.lvl2 { padding-left: 20px; }
.toc-item.lvl3 { padding-left: 32px; font-size: 11.5px; }
.toc-item.lvl4 { padding-left: 44px; font-size: 11.5px; }
.preview .report-md {
  max-height: 420px;
  overflow: auto;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px 14px;
}
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>

<style>
/* ===== 报告正文 markdown 排版（v-html 内容无 scoped 属性，需全局样式）=====
   VS Code Markdown 预览风格：标题层级、表格、列表、引用、代码块 */
.carbon-report-sidebar .report-md {
  color: var(--text);
  font-size: 12.5px;
  line-height: 1.75;
  word-break: break-word;
}
.carbon-report-sidebar .report-md h1,
.carbon-report-sidebar .report-md h2,
.carbon-report-sidebar .report-md h3,
.carbon-report-sidebar .report-md h4 {
  color: var(--text);
  font-weight: 600;
  line-height: 1.4;
  margin: 14px 0 6px;
}
.carbon-report-sidebar .report-md h1 {
  font-size: 17px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 6px;
  margin-top: 0;
}
.carbon-report-sidebar .report-md h2 {
  font-size: 15px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 4px;
}
.carbon-report-sidebar .report-md h3 { font-size: 13.5px; }
.carbon-report-sidebar .report-md h4 { font-size: 12.5px; }
.carbon-report-sidebar .report-md p { margin: 7px 0; }
.carbon-report-sidebar .report-md strong { font-weight: 600; color: var(--text); }
.carbon-report-sidebar .report-md em { color: var(--accent2); }
.carbon-report-sidebar .report-md ul,
.carbon-report-sidebar .report-md ol {
  margin: 6px 0;
  padding-left: 22px;
}
.carbon-report-sidebar .report-md li { margin: 3px 0; }
.carbon-report-sidebar .report-md blockquote {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--accent);
  background: var(--accent-l);
  color: var(--text);
  border-radius: 0 4px 4px 0;
}
.carbon-report-sidebar .report-md code {
  font-family: var(--mono);
  font-size: 11.5px;
  background: var(--panel-3);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--accent2);
}
.carbon-report-sidebar .report-md pre.rp-code {
  background: var(--panel-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 10px 12px;
  overflow: auto;
  font-size: 11.5px;
  line-height: 1.6;
  margin: 8px 0;
}
.carbon-report-sidebar .report-md pre.rp-code code {
  background: transparent;
  padding: 0;
  color: var(--text);
  font-size: 11.5px;
}
.carbon-report-sidebar .report-md table {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
  font-size: 12px;
}
.carbon-report-sidebar .report-md th,
.carbon-report-sidebar .report-md td {
  border: 1px solid var(--border);
  padding: 5px 9px;
  text-align: left;
}
.carbon-report-sidebar .report-md thead th {
  background: var(--panel-2);
  color: var(--muted);
  font-weight: 600;
  white-space: nowrap;
}
.carbon-report-sidebar .report-md tr:nth-child(even) td { background: var(--panel-2); }
.carbon-report-sidebar .report-md hr {
  border: none;
  border-top: 1px solid var(--line);
  margin: 12px 0;
}
.carbon-report-sidebar .report-md a {
  color: var(--accent-d);
  text-decoration: none;
}
.carbon-report-sidebar .report-md a:hover { text-decoration: underline; }
.carbon-report-sidebar .report-md h1[id],
.carbon-report-sidebar .report-md h2[id],
.carbon-report-sidebar .report-md h3[id],
.carbon-report-sidebar .report-md h4[id] { scroll-margin-top: 8px; }
</style>
