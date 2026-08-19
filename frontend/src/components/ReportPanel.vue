<template>
  <div class="report-panel">
    <div class="rp-tabs">
      <button :class="{ active: tab === 'view' }" @click="switchTab('view')">当前报告</button>
      <button :class="{ active: tab === 'history' }" @click="switchTab('history')">历史记录</button>
    </div>

    <!-- 当前报告视图 -->
    <div v-if="tab === 'view'" class="rp-body">
      <div v-if="!payload" class="rp-empty">
        尚未发起报告生成。<br />请先运行仿真 / 应用策略，再点击工具条「数据 → 报告 → 导出报告」。
      </div>

      <!-- 参数配置：进入面板先配置，点击「生成报告」才开始 -->
      <div v-else-if="phase === 'config'" class="rp-config">
        <div class="rp-config-title">报告参数配置</div>
        <div class="rp-config-hint">配置生成参数后点击「生成报告」开始生成，可选择 AI 分析深度与报告范围。</div>

        <label class="rp-field">
          <span class="rp-field-label">报告标题</span>
          <input v-model="cfg.title" type="text" class="rp-input" placeholder="自定义报告标题" />
        </label>

        <div class="rp-field">
          <span class="rp-field-label">生成引擎</span>
          <div class="rp-opt-group">
            <label
              v-for="opt in engineOpts"
              :key="opt.id"
              class="rp-opt"
              :class="{ active: cfg.engine === opt.id }"
            >
              <input v-model="cfg.engine" type="radio" :value="opt.id" />
              <span class="rp-opt-dot"></span>
              <span class="rp-opt-text">
                <b>{{ opt.label }}</b>
                <i>{{ opt.desc }}</i>
              </span>
            </label>
          </div>
        </div>

        <label class="rp-field">
          <span class="rp-field-label">分析深度</span>
          <select v-model="cfg.depth" class="rp-select">
            <option value="brief">精简（每段 80~150 字）</option>
            <option value="standard">标准（每段 150~300 字）</option>
            <option value="deep">深入（每段 300~500 字）</option>
          </select>
        </label>

        <label class="rp-check">
          <input v-model="cfg.withAppendix" type="checkbox" />
          <span class="rp-check-box"></span>
          <span class="rp-check-text">包含「附录：全流程明细」表格</span>
        </label>

        <button class="rp-btn primary rp-gen-btn" @click="startGenerate">生成报告</button>
      </div>

      <!-- 生成中：实时进度 -->
      <div v-else-if="phase === 'generating'" class="rp-progress">
        <div class="rp-progress-box">
          <div class="rp-progress-bar">
            <div class="rp-progress-fill" :style="{ width: progress + '%' }"></div>
          </div>
          <div class="rp-progress-meta">
            <span class="rp-progress-pct">{{ progress }}%</span>
            <span class="rp-progress-stage">{{ stageText }}</span>
          </div>
        </div>
        <p class="rp-progress-hint">正在生成报告，请稍候…（AI 分析阶段可能需要 1~3 分钟）</p>
      </div>

      <!-- 生成失败 -->
      <div v-else-if="phase === 'error'" class="rp-center rp-error">
        <p>报告生成失败</p>
        <p class="rp-err-msg">{{ error }}</p>
        <button class="rp-btn primary" @click="backToConfig">返回配置</button>
      </div>

      <!-- 报告展示 -->
      <template v-else-if="report && phase === 'done'">
        <div class="rp-toolbar">
          <span class="rp-badge" :class="report.engine">
            {{ report.engine === 'llm' ? 'AI 生成' : '本地模板' }}
          </span>
          <a class="rp-link" :href="report.url" target="_blank" rel="noopener">
            新页面查看 ↗
          </a>
          <button class="rp-btn" title="下载 Markdown 文件" @click="download">下载</button>
          <button class="rp-btn" title="复制 Markdown 全文" @click="copy">复制</button>
        </div>
        <div class="rp-meta-line">
          <span>{{ report.title }}</span>
          <span v-if="report.created_at">{{ report.created_at }}</span>
        </div>
        <div class="rp-scroll" v-html="html"></div>
        <div class="rp-foot">
          <button class="rp-btn" @click="backToConfig">重新生成</button>
        </div>
      </template>
    </div>

    <!-- 历史记录视图 -->
    <div v-else class="rp-body">
      <div v-if="histLoading" class="rp-center"><span class="rp-spinner"></span><p>加载历史报告…</p></div>
      <div v-else-if="!hist.length" class="rp-empty">暂无历史报告。</div>
      <ul v-else class="rp-hist">
        <li v-for="h in hist" :key="h.id" class="rp-hist-item">
          <div class="rp-hist-title">{{ h.title }}</div>
          <div class="rp-hist-meta">
            <span class="rp-badge" :class="h.engine">{{ h.engine === 'llm' ? 'AI' : '模板' }}</span>
            <span>{{ h.created_at }}</span>
            <span>{{ h.length }} 字</span>
          </div>
          <div class="rp-hist-actions">
            <button class="rp-btn primary" @click="openHistory(h.id)">查看</button>
            <a class="rp-link" :href="h.url" target="_blank" rel="noopener">新页打开 ↗</a>
            <button class="rp-btn danger" title="删除此条历史" @click="delHistory(h.id)">删除</button>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { renderMarkdown } from '../utils/markdown'

const store = useSimStore()
const tab = ref('view')
const payload = computed(() => store.reportPayload)
const report = ref(null)
const phase = ref('config') // config | generating | done | error
const progress = ref(0)
const stage = ref('')
const error = ref('')
const hist = ref([])
const histLoading = ref(false)
let pollTimer = null

// —— 生成参数配置 ——
const cfg = ref({ title: '', engine: 'auto', depth: 'standard', withAppendix: true })
const engineOpts = [
  { id: 'auto', label: '自动', desc: '有 AI 则 AI，否则模板' },
  { id: 'llm', label: 'AI 生成', desc: '强制大语言模型撰写' },
  { id: 'template', label: '本地模板', desc: '确定性文案，生成最快' },
]

const STAGE_TEXT = {
  queued: '任务排队中',
  ctx: '组装仿真数据',
  llm_summary: 'AI 撰写执行摘要',
  llm_baseline_insight: 'AI 分析基线数据',
  llm_strategy_eval: 'AI 评估策略效果',
  llm_suggestions: 'AI 撰写优化建议',
  template: '生成模板分析',
  render: '渲染报告',
  save: '保存报告',
  done: '完成',
}
const stageText = computed(() => STAGE_TEXT[stage.value] || stage.value || '')

const html = computed(() => (report.value ? renderMarkdown(report.value.markdown) : ''))

// —— 命令行窗口进度条：就地更新最后一条进度行，避免刷屏 ——
let progressLineIdx = -1
function pushProgressLine() {
  const pct = Math.max(0, Math.min(100, Math.round(progress.value)))
  const st = stageText.value || '…'
  const filled = Math.round(pct / 10)
  const bar = '█'.repeat(filled) + '░'.repeat(10 - filled)
  const line = `[报告生成] ${bar} ${pct}% · ${st}`
  if (progressLineIdx >= 0 && store.cmdLog[progressLineIdx]) {
    store.cmdLog.splice(progressLineIdx, 1, { t: line, k: 'out' })
  } else {
    store.cmdLog.push({ t: line, k: 'out' })
    progressLineIdx = store.cmdLog.length - 1
  }
}
function finishProgressLine(t, k = 'out') {
  if (progressLineIdx >= 0 && store.cmdLog[progressLineIdx]) {
    store.cmdLog.splice(progressLineIdx, 1, { t, k })
  } else {
    store.cmdLog.push({ t, k })
  }
  progressLineIdx = -1
}

function defaultTitle() {
  const parts = [payload.value?.strategy_name, payload.value?.scenario].filter(Boolean)
  return parts.join(' · ') || '节能减碳分析报告'
}

// 每次点击「导出报告」（reportNonce 递增）：进入面板 → 参数配置（不自动生成）
watch(
  () => store.reportNonce,
  () => {
    if (!payload.value) return
    report.value = null
    error.value = ''
    tab.value = 'view'
    phase.value = 'config'
    cfg.value.title = defaultTitle()
    progress.value = 0
    stage.value = ''
    progressLineIdx = -1
    stopPoll()
  },
  { immediate: true },
)

async function startGenerate() {
  if (!payload.value || phase.value === 'generating') return
  phase.value = 'generating'
  progress.value = 0
  stage.value = 'queued'
  error.value = ''
  try {
    const res = await api.generateReport({
      ...payload.value,
      title: cfg.value.title.trim(),
      engine: cfg.value.engine,
      depth: cfg.value.depth,
      with_appendix: cfg.value.withAppendix,
    })
    if (!res || res.ok === false) throw new Error((res && res.error) || '任务创建失败')
    store.pushCmd(`报告生成任务已提交：${cfg.value.title.trim() || defaultTitle()}（引擎 ${cfg.value.engine} · 深度 ${cfg.value.depth}）。`, 'out')
    pollTask(res.task_id)
  } catch (e) {
    error.value = e.message || String(e)
    phase.value = 'error'
    finishProgressLine(`报告生成失败：${error.value}`, 'err')
  }
}

// 轮询任务进度（真实百分比 + 阶段文案）
function pollTask(taskId) {
  stopPoll()
  const tick = async () => {
    try {
      const t = await api.getReportTask(taskId)
      if (!t || t.ok === false) {
        error.value = (t && t.error) || '任务查询失败'
        phase.value = 'error'
        finishProgressLine(`报告生成失败：${error.value}`, 'err')
        return
      }
      progress.value = t.progress || 0
      stage.value = t.stage || ''
      pushProgressLine()
      if (t.done) {
        if (t.ok) {
          report.value = t.result
          phase.value = 'done'
          finishProgressLine(`报告生成完成：${report.value.title || '未命名'}（${report.value.length ?? ''} 字），可在右侧报告面板查看、下载或新页打开。`, 'guide')
        } else {
          error.value = t.error || '报告生成失败'
          phase.value = 'error'
          finishProgressLine(`报告生成失败：${error.value}`, 'err')
        }
        return
      }
      pollTimer = setTimeout(tick, 800)
    } catch (e) {
      error.value = String(e.message || e)
      phase.value = 'error'
      finishProgressLine(`报告生成失败：${error.value}`, 'err')
    }
  }
  tick()
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}
onBeforeUnmount(stopPoll)

function backToConfig() {
  phase.value = 'config'
}

async function loadHistory() {
  histLoading.value = true
  try {
    const res = await api.listReports()
    hist.value = (res && res.reports) || []
  } catch (e) {
    hist.value = []
  } finally {
    histLoading.value = false
  }
}

function switchTab(t) {
  tab.value = t
  if (t === 'history') loadHistory()
}

async function openHistory(id) {
  try {
    const res = await api.getReport(id)
    if (!res || res.ok === false) {
      error.value = (res && res.error) || '加载失败'
      return
    }
    report.value = res
    phase.value = 'done'
    tab.value = 'view'
  } catch (e) {
    error.value = String(e.message || e)
    tab.value = 'view'
  }
}

async function delHistory(id) {
  if (!window.confirm('确定删除这条历史报告？')) return
  try {
    await api.deleteReport(id)
  } catch (e) {
    // 忽略删除错误，直接刷新列表
  }
  await loadHistory()
}

function download() {
  if (!report.value) return
  const blob = new Blob([report.value.markdown], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = (report.value.title || '节能减碳分析报告') + '.md'
  a.click()
  URL.revokeObjectURL(a.href)
}

async function copy() {
  if (!report.value) return
  try {
    await navigator.clipboard.writeText(report.value.markdown)
    store.toast = '报告 Markdown 已复制到剪贴板'
  } catch (e) {
    store.toast = '复制失败，请手动选择复制'
  }
}
</script>

<style scoped>
.report-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.rp-tabs { display: flex; gap: 4px; padding: 8px 10px 0; }
.rp-tabs button {
  flex: 1; padding: 5px 0; font-size: 11px; border: 1px solid var(--line);
  border-radius: 3px; background: transparent; color: var(--muted); cursor: pointer;
}
.rp-tabs button.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.rp-body { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 8px 10px 12px; }
.rp-empty { margin: 24px 6px; text-align: center; color: var(--muted); font-size: 11px; line-height: 1.8; }
.rp-center { margin: 32px 6px; text-align: center; color: var(--muted); font-size: 11px; line-height: 1.8; }
.rp-spinner {
  display: inline-block; width: 22px; height: 22px; border: 2px solid var(--line);
  border-top-color: var(--accent); border-radius: 50%; animation: rp-spin 0.8s linear infinite;
}
@keyframes rp-spin { to { transform: rotate(360deg); } }
.rp-error p { color: var(--red); }
.rp-err-msg { font-size: 11px; word-break: break-all; margin: 4px 0 10px; }
.rp-btn {
  padding: 4px 10px; font-size: 11px; border: 1px solid var(--line); border-radius: 3px;
  background: #fff; color: var(--text); cursor: pointer;
}
.rp-btn:hover { border-color: var(--accent2); color: var(--accent2); }
.rp-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.rp-btn.primary:hover { opacity: 0.88; color: #fff; }
.rp-btn.danger { color: var(--red); border-color: var(--red); }
.rp-btn.danger:hover { background: var(--red); color: #fff; }
.rp-toolbar { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.rp-badge { font-size: 10px; padding: 2px 8px; border-radius: 3px; font-weight: 600; white-space: nowrap; }
.rp-badge.llm { background: #e3f2fd; color: #0a58ca; border: 1px solid #0d6efd; }
.rp-badge.template { background: #f0f0f0; color: var(--muted); border: 1px solid var(--line); }
.rp-link { font-size: 11px; color: var(--accent); text-decoration: none; margin-left: auto; }
.rp-link:hover { text-decoration: underline; }
.rp-meta-line { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0 4px; font-size: 10px; color: var(--muted); }
.rp-meta-line span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rp-scroll { flex: 1; min-height: 0; overflow: auto; padding: 4px 2px; }
.rp-foot { padding-top: 8px; text-align: center; }

/* —— 参数配置 —— */
.rp-config { flex: 1; min-height: 0; overflow: auto; padding: 4px 2px; }
.rp-config-title { font-size: 12px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.rp-config-hint { font-size: 11px; color: var(--muted); line-height: 1.6; margin-bottom: 12px; }
.rp-field { display: block; margin-bottom: 12px; }
.rp-field-label { display: block; font-size: 11px; font-weight: 600; color: var(--text); margin-bottom: 5px; }
.rp-input {
  width: 100%; box-sizing: border-box; padding: 4px 8px; font-size: 11px;
  border: 1px solid var(--line); border-radius: 3px; background: var(--panel); color: var(--text); outline: none;
}
.rp-input:focus { border-color: var(--accent); }
.rp-select {
  width: 100%; box-sizing: border-box; padding: 4px 8px; font-size: 11px;
  border: 1px solid var(--line); border-radius: 3px; background: var(--panel); color: var(--text); outline: none;
}
.rp-select:focus { border-color: var(--accent); }
.rp-opt-group { display: flex; flex-direction: column; gap: 6px; }
.rp-opt {
  position: relative; display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border: 1px solid var(--line); border-radius: 3px; cursor: pointer;
  background: var(--panel); color: var(--text);
}
.rp-opt:hover { border-color: var(--accent2); }
.rp-opt.active { border-color: var(--accent); background: var(--accent-l); }
.rp-opt input { position: absolute; opacity: 0; width: 0; height: 0; }
.rp-opt-dot {
  width: 13px; height: 13px; border-radius: 50%; flex: none; box-sizing: border-box;
  border: 2px solid var(--faint); background: var(--panel); position: relative;
}
.rp-opt.active .rp-opt-dot { border-color: var(--accent); }
.rp-opt.active .rp-opt-dot::after {
  content: ''; position: absolute; inset: 2px; border-radius: 50%; background: var(--accent);
}
.rp-opt-text { display: flex; flex-direction: column; line-height: 1.5; }
.rp-opt-text b { font-weight: 600; color: var(--text); font-size: 11px; }
.rp-opt-text i { font-style: normal; color: var(--muted); font-size: 10px; }
.rp-check { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--text); margin-bottom: 14px; cursor: pointer; }
.rp-check input { position: absolute; opacity: 0; width: 0; height: 0; }
.rp-check-box {
  width: 14px; height: 14px; border-radius: 3px; flex: none; box-sizing: border-box; position: relative;
  border: 1.5px solid var(--faint); background: var(--panel);
}
.rp-check input:checked + .rp-check-box { border-color: var(--accent); background: var(--accent); }
.rp-check input:checked + .rp-check-box::after {
  content: ''; position: absolute; left: 4px; top: 1px; width: 3px; height: 7px;
  border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg);
}
.rp-check-text { color: var(--text); }
.rp-gen-btn { width: 100%; padding: 8px 0; font-size: 11px; font-weight: 600; }

/* —— 生成进度 —— */
.rp-progress { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 6px; }
.rp-progress-box { border: 1px solid var(--line); border-radius: 3px; padding: 14px 12px; background: var(--panel); }
.rp-progress-bar { height: 10px; border-radius: 3px; background: rgba(0, 0, 0, 0.08); overflow: hidden; }
.rp-progress-fill {
  height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent), var(--accent2));
  transition: width 0.4s ease;
}
.rp-progress-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.rp-progress-pct { font-size: 18px; font-weight: 700; color: var(--accent); }
.rp-progress-stage { font-size: 11px; color: var(--muted); }
.rp-progress-hint { margin-top: 14px; text-align: center; font-size: 11px; color: var(--muted); }

.rp-hist { list-style: none; margin: 0; padding: 0; overflow: auto; flex: 1; min-height: 0; }
.rp-hist-item { border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; margin-bottom: 6px; }
.rp-hist-title { font-size: 11px; font-weight: 600; margin-bottom: 4px; }
.rp-hist-meta { display: flex; align-items: center; gap: 8px; font-size: 10px; color: var(--muted); margin-bottom: 8px; }
.rp-hist-actions { display: flex; align-items: center; gap: 6px; }
.rp-hist-actions .rp-link { margin-left: auto; }
</style>

<style>
/* 报告 Markdown 渲染样式（非 scoped：作用于 v-html 内容） */
.report-panel .rp-scroll { line-height: 1.7; font-size: 12px; color: var(--text); }
.report-panel .rp-scroll h1 { font-size: 15px; margin: 10px 0 6px; padding-bottom: 4px; border-bottom: 2px solid var(--accent); }
.report-panel .rp-scroll h2 { font-size: 13px; margin: 12px 0 6px; color: var(--accent2); }
.report-panel .rp-scroll h3 { font-size: 11.5px; margin: 10px 0 4px; }
.report-panel .rp-scroll h4 { font-size: 11.5px; margin: 8px 0 4px; }
.report-panel .rp-scroll p { margin: 6px 0; }
.report-panel .rp-scroll table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 11px; display: block; overflow-x: auto; white-space: nowrap; }
.report-panel .rp-scroll th, .report-panel .rp-scroll td { border: 1px solid var(--line); padding: 4px 8px; text-align: left; }
.report-panel .rp-scroll th { background: var(--panel-2); font-weight: 600; }
.report-panel .rp-scroll blockquote { margin: 6px 0; padding: 6px 10px; border-left: 3px solid var(--accent); background: rgba(13, 110, 253, 0.06); color: var(--muted); border-radius: 0 6px 6px 0; }
.report-panel .rp-scroll code { background: var(--panel-2); padding: 1px 4px; border-radius: 3px; font-size: 10.5px; }
.report-panel .rp-scroll pre.rp-code { background: #1e2530; color: #d8e0ea; padding: 10px; border-radius: 3px; overflow: auto; font-size: 10.5px; }
.report-panel .rp-scroll pre.rp-code code { background: transparent; color: inherit; padding: 0; }
.report-panel .rp-scroll ul, .report-panel .rp-scroll ol { margin: 6px 0; padding-left: 20px; }
.report-panel .rp-scroll li { margin: 3px 0; }
.report-panel .rp-scroll hr { border: none; border-top: 1px solid var(--line); margin: 10px 0; }
</style>
