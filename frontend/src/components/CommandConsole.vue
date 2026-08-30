<template>
  <!-- ============ 命令行窗口（底部面板：日志区 + 输入行） ============ -->
  <section class="cmdwin">
    <div class="cmd-rsz" :class="{ dragging: resizing }" @mousedown.prevent="startResize"></div>
    <!-- 页签栏：非仿真 输出/命令；仿真 输出/命令/仿真对比 -->
    <div class="cmd-tabs">
      <button v-for="tab in tabs" :key="tab.id" class="cmd-tab" :class="{ on: activeTab === tab.id }" @click="activeTab = tab.id">{{ t(tab.label) }}</button>
    </div>
    <div ref="logEl" class="cmd-log">
      <!-- 输出 / 命令：日志流（按页签过滤） -->
      <template v-if="activeTab !== 'compare'">
        <div v-for="(l, i) in shownLog" :key="i" class="ln" :class="l.k">{{ l.t }}</div>
      </template>
      <!-- 仿真对比：调整前后碳排放 / 能源量化对比（before=仿真前基线 after=当前实时结果） -->
      <template v-else>
        <div v-if="!store.simBaseline" class="sim-compare-empty">{{ t('进入仿真模式后，调整参数 / 设备设定 / 策略，此处实时展示调整前后的碳排放与能源变化。') }}</div>
        <template v-else>
          <div v-if="compareRows.length" class="sim-cmp-cols">
            <div class="sim-cmp-col" v-for="g in compareRows" :key="g.key">
              <div class="sim-cmp-gname">{{ t(g.name) }}</div>
              <div class="sim-cmp-row" v-for="r in g.rows" :key="r.key" :title="t(r.name)">
                <span class="sim-cmp-name">{{ t(r.name) }}</span>
                <span class="sim-cmp-fv"><i>{{ r.beforeText }}</i><em>→</em><b>{{ r.afterText }}</b><small>{{ r.u }}</small></span>
                <span class="sim-cmp-delta" :class="r.cls">{{ r.arrow }} {{ r.deltaText }}</span>
              </div>
            </div>
          </div>
          <div v-else class="sim-compare-empty">{{ t('尚未执行前后对比：点击左侧「策略」，在属性面板使用「策略仿真」测试。') }}</div>
          <!-- 本次调整明细（与变更记录同源，实时合并） -->
          <div v-if="store.simChanges.length" class="sim-cmp-changes">
            <div class="sim-cmp-changes-t">{{ t('本次调整') }}</div>
            <div v-for="c in store.simChanges" :key="c.id" class="sim-citem">
              <span class="sim-ctag" :class="'sc-' + c.type">{{ t(SIM_TYPE_TEXT[c.type]) || c.type }}</span>
              <span class="sim-clabel">{{ c.label }}</span>
              <span v-if="c.detail" class="sim-cdetail">{{ c.detail }}</span>
            </div>
          </div>
        </template>
      </template>
    </div>
    <div class="cmd-input-row">
      <span class="pmt">&gt;</span>
      <input ref="cmdInput" v-model="cmdText" class="cmd-input" spellcheck="false" autocomplete="off"
             :placeholder="store.simMode ? t('仿真模式：输入自然语言指令（如“焦比降低10%”），/help 查看命令') : t('输入命令或直接提问（/help 查看）')" @keydown.enter="runCmd" @keydown.up="histUp" @keydown.down="histDown" />
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const props = defineProps({
  // 孪生控制命令需要的外部动作（由 App 提供，避免命令窗口直接操作页面布局）
  actions: { type: Object, required: true },
  // 拖拽调整高度（由 App 通过 usePanelSizes 提供）
  resizing: { type: Boolean, default: false },
  startResize: { type: Function, required: true },
})

const store = useSimStore()
// 仿真变更类型文案（「仿真对比」页签，与右上角对比面板同源）
const SIM_TYPE_TEXT = { param: t('参数'), factor: t('因子'), setpoint: t('设备'), strategy: t('策略') }
// 页签分流：输出（系统自动输出 out/sys/sim/tip/warn） / 命令（用户交互 cmd/bot/err/guide）
const INTERACT_K = ['cmd', 'bot', 'err', 'guide']
const outputLog = computed(() => store.cmdLog.filter((l) => !INTERACT_K.includes(l.k)))
const interactLog = computed(() => store.cmdLog.filter((l) => INTERACT_K.includes(l.k)))
const activeTab = ref('output')
const tabs = computed(() => (store.simMode
  ? [{ id: 'output', label: t('输出') }, { id: 'interact', label: t('命令') }, { id: 'compare', label: t('仿真对比') }]
  : [{ id: 'output', label: t('输出') }, { id: 'interact', label: t('命令') }]))
const shownLog = computed(() => (activeTab.value === 'output' ? outputLog.value : interactLog.value))

// ---- 「仿真对比」页签：调整前后碳排放/能源量化对比（before=simBaseline.totals after=simCurrent.totals） ----
// 兼容字段取值：前端估算结果用 energy，后端完整结果用 energy_total
function pick(o, ...keys) {
  if (!o) return null
  for (const k of keys) { const v = o[k]; if (v != null && !isNaN(v)) return v }
  return null
}
const fmtN = (n) => (n == null ? '—' : Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
const fmtPct = (p) => ((p > 0 ? '+' : '') + p.toFixed(1) + '%')
// 基线 vs 当前是否发生实质变化（未应用策略时兜底引导判断）
function hasDelta(b, c) {
  for (const k of ['co2_total', 'energy_total', 'energy', 'intensity']) {
    if (b[k] != null && c[k] != null && Math.abs(b[k] - c[k]) > 1e-9) return true
  }
  return false
}
const compareRows = computed(() => {
  const base = store.simBaseline && store.simBaseline.totals
  if (!base) return []
  const cur = (store.simCurrent && store.simCurrent.totals)
    || (store.strategy && store.strategy.totals)
    || (store.resultForView && store.resultForView.totals) || null
  if (!cur) return []
  if (!store.simCurrent && !store.strategy && !hasDelta(base, cur)) return []  // 尚无对比内容 → 显示引导

  const defs = [
    { key: 'co2', name: '碳排放', rows: [
      { key: 'co2_total', name: '总排放量', a: pick(base, 'co2_total'), b: pick(cur, 'co2_total'), u: 'tCO₂/h', dir: 'down' },
      { key: 'co2_direct', name: '直接排放(范围一)', a: pick(base, 'co2_direct'), b: pick(cur, 'co2_direct'), u: 'tCO₂/h', dir: 'down' },
      { key: 'co2_indirect', name: '间接排放(范围二)', a: pick(base, 'co2_indirect'), b: pick(cur, 'co2_indirect'), u: 'tCO₂/h', dir: 'down' },
      { key: 'intensity', name: '吨钢碳排放强度', a: pick(base, 'intensity'), b: pick(cur, 'intensity'), u: 'kgCO₂/t', dir: 'down' },
    ] },
    { key: 'energy', name: '能耗', rows: [
      { key: 'energy_total', name: '综合能耗', a: pick(base, 'energy_total', 'energy'), b: pick(cur, 'energy_total', 'energy'), u: 'GJ/h', dir: 'down' },
      { key: 'energy_intensity', name: '单位产品综合能耗', a: pick(base, 'energy_intensity'), b: pick(cur, 'energy_intensity'), u: 'kgce/t', dir: 'down' },
      { key: 'elec', name: '电耗', a: pick(base, 'elec'), b: pick(cur, 'elec'), u: 'MWh/h', dir: 'down' },
      { key: 'fuel_energy', name: '燃料能耗', a: pick(base, 'fuel_energy'), b: pick(cur, 'fuel_energy'), u: 'GJ/h', dir: 'down' },
    ] },
  ]
  return defs.map((g) => ({
    key: g.key, name: g.name,
    rows: g.rows
      .filter((r) => r.a != null && r.b != null)
      .map((r) => {
        const d = r.b - r.a
        const relPct = r.a !== 0 ? (d / r.a) * 100 : null
        const good = r.dir === 'up' ? d >= 0 : r.dir === 'down' ? d <= 0 : true
        const cls = r.dir === 'neutral' ? 'neu' : (good ? 'good' : 'bad')
        return {
          ...r,
          beforeText: fmtN(r.a), afterText: fmtN(r.b), d,
          arrow: d > 1e-9 ? '▲' : d < -1e-9 ? '▼' : '–',
          deltaText: relPct == null ? fmtN(d) : fmtPct(relPct),
          cls,
        }
      }),
  })).filter((g) => g.rows.length)
})
const cmdText = ref('')
const logEl = ref(null)
const cmdInput = ref(null)
const hist = ref([])
let histIdx = -1

function pushCmd(t, k = 'out') { store.pushCmd(t, k); scrollLog() }
function scrollLog() { nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight }) }

/* 其他组件写入 cmdLog（如顶栏动作）时自动滚动到底部 */
watch(() => [...store.cmdLog], () => scrollLog())
/* 切换页签时滚动到底部 */
watch(() => activeTab.value, () => scrollLog())
/* 退出仿真若停在「仿真对比」页签，自动切回「命令」 */
watch(() => store.simMode, (v, pv) => { if (!v && pv && activeTab.value === 'compare') activeTab.value = 'interact' })

function helpText() {
  return t('命令：help 帮助 · run/sim 运行 · stop 停止 · /sim 进入仿真模式 · reset 重置视角 · overview 全景 · view top|front|side|focus · edit 进入编排 · done 完成 · clear 清屏\n') +
         t('聊天模式（默认）：直接输入自然语言即可对话。切换：/code 代码 · /plan 规划。退出：/quit 回到聊天。\n') +
         t('仿真模式：输入自然语言指令（如“焦比降低10%”），由智能体解析、经您确认后自动应用并实时对比。')
}
/* 命令行窗口：模式 + 自然语言聊天（默认即聊天，/code /plan 切模式，/quit 退出） */
const cmdMode = ref('chat')
const cmdChatHistory = ref([])          // [[role, content], ...] 仅聊天上下文
const CMD_MODES = {
  chat: { label: t('聊天'), prompt: t('你是「本析智擎」，钢铁企业能碳智控平台智能助手，只接受钢铁企业节能减碳相关及系统相关数据的问询与策略，不闲聊。') },
  code: { label: t('代码'), prompt: t('你是一个资深程序员助手。优先给出可运行、带注释的代码，并解释关键思路；遇到报错帮助定位问题。') },
  plan: { label: t('规划'), prompt: t('你是一个项目规划助手。把用户诉求拆成有序、可执行的步骤，标注依赖与优先级，输出清单式计划。') },
}
// 原有孪生控制命令（首词命中即执行，其余一律当自然语言走聊天）
const KNOWN_CMDS = new Set(['help', 'run', 'sim', 'stop', 'reset', 'overview', 'home', 'view', 'edit', 'done', 'clear'])

async function runCmd() {
  const raw = cmdText.value.trim()
  if (!raw) return
  pushCmd(raw, 'cmd')
  hist.value.push(raw); histIdx = hist.value.length
  cmdText.value = ''
  if (store.pendingSaveStrategy) {        // 仿真模式：等待输入策略名称
    if (raw.toLowerCase() === 'cancel' || raw === '取消') {
      store.pendingSaveStrategy = false
      pushCmd(t('已取消保存策略。'), 'guide')
    } else {
      try {
        const created = await store.saveCurrentAsStrategy(raw)
        store.pendingSaveStrategy = false
        pushCmd(`${t('策略')}「${created?.name || raw}」${t('已保存，可在左侧「策略」资源管理中查看并编辑。')}`, 'guide')
      } catch (e) {
        pushCmd(`${t('保存失败')}：${e?.message || e}`, 'err')
      }
    }
    return
  }
  if (raw.startsWith('/')) { handleSlash(raw); return }
  const first = raw.split(/\s+/)[0].toLowerCase()
  if (KNOWN_CMDS.has(first)) { runTwinCommand(first, raw); return }
  if (store.simMode && cmdMode.value === 'chat') {   // 仿真模式：自然语言 → 智能体解析
    pushCmd(`${t('收到指令')}：「${raw}」。${t('可直接在仿真模式中手动调整参数，或点击左侧「策略」应用内置/自定义策略。')}`, 'guide')
    return
  }
  chatWithModel(raw)                         // 其余自然语言 → 直接对话
}

async function handleSlash(raw) {
  const c = raw.toLowerCase().trim()
  if (c === '/help' || c === '/?' || c === '/h') { pushCmd(helpText(), 'guide'); return }
  if (c === '/clear') { clearLog(); return }
  if (c === '/back') {
    if (cmdMode.value !== 'chat') { cmdMode.value = 'chat'; pushCmd(t('已回到「聊天」模式。'), 'guide') }
    else pushCmd(t('当前已在聊天模式。'), 'guide')
    return
  }
  if (c === '/sim') {
    if (store.simMode) pushCmd(t('已在仿真模式中：点击「退出仿真」或输入 stop 可退出。'), 'guide')
    else props.actions.onSimToggle()
    return
  }
  if (c === '/quit' || c === '/exit') {
    if (cmdMode.value !== 'chat') { const m = CMD_MODES[cmdMode.value].label; cmdMode.value = 'chat'; pushCmd(`${t('已退出')}「${m}」${t('模式，回到聊天模式。')}`, 'guide') }
    else pushCmd(t('已处于聊天模式，直接输入即可对话，无需退出。'), 'guide')
    return
  }
  const map = { '/code': 'code', '/plan': 'plan' }
  if (map[c]) {
    cmdMode.value = map[c]
    pushCmd(`${t('已进入')}「${CMD_MODES[map[c]].label}」${t('模式。输入 /quit 退出本模式，/back 回聊天。')}`, 'guide')
    return
  }
  pushCmd(`${t('未知指令')}："${raw}"。${t('输入 /help 查看可用命令与模式。')}`, 'err')
}

function runTwinCommand(c, raw) {
  const arg = raw.split(/\s+/).slice(1).join(' ').toLowerCase()
  switch (c) {
    case 'help': pushCmd(helpText(), 'guide'); break
    case 'run': case 'sim': props.actions.onSimToggle(); break
    case 'stop': props.actions.onSimToggle(); break
    case 'reset': props.actions.onResetView(); break
    case 'overview': case 'home': props.actions.onOverview(); break
    case 'view': props.actions.focusSel(arg || 'focus'); break
    case 'edit': store.editMode ? null : props.actions.onToggleEdit(); break
    case 'done': store.editMode ? props.actions.onToggleEdit() : pushCmd(t('当前不在编排态。'), 'guide'); break
    case 'clear': clearLog(); break
  }
}

async function chatWithModel(text) {
  const mode = cmdMode.value
  pushCmd(t('（思考中…）'), 'bot')
  const idx = store.cmdLog.length - 1
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history: cmdChatHistory.value.slice(-10), mode }),
    })
    const data = await resp.json()
    const reply = data.reply != null ? String(data.reply) : t('（无返回）')
    store.cmdLog.splice(idx, 1, { t: reply, k: data.ok === false ? 'err' : 'bot' })
    cmdChatHistory.value.push(['user', text])
    cmdChatHistory.value.push(['assistant', reply])
    if (cmdChatHistory.value.length > 22) cmdChatHistory.value = cmdChatHistory.value.slice(-22)
  } catch (e) {
    store.cmdLog.splice(idx, 1, { t: t('（对话服务不可用：请确认后端已启动并配置了 LLM）'), k: 'err' })
  }
  scrollLog()
}
function clearLog() { store.clearCmdLog() }
function histUp() { if (!hist.value.length) return; histIdx = Math.max(0, histIdx - 1); cmdText.value = hist.value[histIdx] || '' }
function histDown() { if (!hist.value.length) return; histIdx = Math.min(hist.value.length, histIdx + 1); cmdText.value = hist.value[histIdx] || '' }

defineExpose({ focusInput: () => { if (cmdInput.value) cmdInput.value.focus() } })
</script>
