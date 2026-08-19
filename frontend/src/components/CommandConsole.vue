<template>
  <!-- ============ 命令行窗口（MATLAB 风） ============ -->
  <section class="cmdwin">
    <div class="cmd-rsz" :class="{ dragging: resizing }" @mousedown.prevent="startResize" title="拖拽调整高度"></div>
    <div class="cmdwin-head" :class="{ sim: store.simMode }">
      <span class="dot"></span>
      <span class="tt">{{ store.simMode ? '命令行窗口（仿真模式）' : '命令行窗口' }}</span>
      <span v-if="store.simMode" class="mode-badge mb-sim">仿真中</span>
      <span v-else-if="cmdMode !== 'chat'" class="mode-badge" :class="'mb-' + cmdMode">{{ cmdModeLabel }}</span>
      <span class="sp"></span>
      <button class="ctool" @click="clearLog" title="清空">清空</button>
      <button class="ctool" @click="pushCmd(helpText(),'guide')" title="帮助">帮助</button>
    </div>
    <div ref="logEl" class="cmd-log">
      <div v-for="(l, i) in log" :key="i" class="ln" :class="l.k">{{ l.t }}</div>
    </div>
    <div class="cmd-input-row">
      <span class="pmt">&gt;&gt;</span>
      <input ref="cmdInput" v-model="cmdText" class="cmd-input" spellcheck="false" autocomplete="off"
             :placeholder="store.simMode ? '仿真模式：可输入自然语言指令（如“焦比降低10%”），由智能体解析并应用（规划中），或 /help 查看命令' : '直接聊天，或 /code /plan 切换模式（/help 查看）'" @keydown.enter="runCmd" @keydown.up="histUp" @keydown.down="histDown" />
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'

const props = defineProps({
  // 孪生控制命令需要的外部动作（由 App 提供，避免命令窗口直接操作页面布局）
  actions: { type: Object, required: true },
  // 拖拽调整高度（由 App 通过 usePanelSizes 提供）
  resizing: { type: Boolean, default: false },
  startResize: { type: Function, required: true },
})

const store = useSimStore()
const log = computed(() => store.cmdLog)
const cmdText = ref('')
const logEl = ref(null)
const cmdInput = ref(null)
const hist = ref([])
let histIdx = -1

function pushCmd(t, k = 'out') { store.pushCmd(t, k); scrollLog() }
function scrollLog() { nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight }) }

/* 仿真模式：进入/退出提示 + 仿真前后所做更改实时输出到命令行（与右上角对比面板同源） */
const SIM_TYPE_TEXT = { param: '参数', factor: '因子', setpoint: '设备', strategy: '策略' }
let lastSimChanges = []
watch(() => store.simMode, (v, pv) => {
  if (v && !pv) pushCmd('仿真模式已开启：以下将实时记录本次仿真前后所做的更改，退出后自动恢复', 'tip')
  if (!v && pv) pushCmd('仿真模式已退出，数字孪生环境已切换为工业，所有修改已自动恢复', 'tip')
})
watch(() => store.simChanges, (cur, prev) => {
  if (!store.simMode) { lastSimChanges = Array.isArray(cur) ? cur : []; return }
  const prevList = Array.isArray(prev) ? prev : lastSimChanges
  const list = Array.isArray(cur) ? cur : []
  lastSimChanges = list
  for (const c of list) {
    const old = prevList.find((x) => x.id === c.id)
    const tag = SIM_TYPE_TEXT[c.type] || c.type || '更改'
    if (!old) {
      pushCmd(`${tag} ${c.label}${c.detail ? '：' + c.detail : ''}`, 'sim')
    } else if (old.detail !== c.detail || old.ts !== c.ts) {
      pushCmd(`↻ ${tag} ${c.label}${c.detail ? '：' + c.detail : ''}`, 'sim')
    }
  }
})
// 其他组件写入 cmdLog（如顶栏动作）时自动滚动到底部
watch(() => [...store.cmdLog], () => scrollLog())

function helpText() {
  return '孪生命令：help · run/sim 运行 · stop 停止 · /sim 进入仿真模式 · reset 重置视角 · overview 全景 · patrol 虚拟巡视 · view top|front|side|focus · edit 进入编排 · done 完成 · clear 清屏\n' +
         '聊天模式（默认）：直接输入自然语言即可对话。切换：/code 代码 · /plan 规划。退出当前模式：/quit（回到聊天）；/back 直接回聊天。\n' +
         '仿真模式：点击「运行」或输入 /sim 进入，退出后所有修改自动恢复；仿真模式下可直接输入自然语言指令（如“焦比降低10%”），由智能体解析、经您确认后自动应用于仿真并实时对比（规划中）。'
}
/* 命令行窗口：模式 + 自然语言聊天（默认即聊天，/code /plan 切模式，/quit 退出） */
const cmdMode = ref('chat')
const cmdChatHistory = ref([])          // [[role, content], ...] 仅聊天上下文
const CMD_MODES = {
  chat: { label: '聊天', prompt: '你是一个友好的中文聊天助手，轻松自然地陪用户闲聊，口语化、简洁。' },
  code: { label: '代码', prompt: '你是一个资深程序员助手。优先给出可运行、带注释的代码，并解释关键思路；遇到报错帮助定位问题。' },
  plan: { label: '规划', prompt: '你是一个项目规划助手。把用户诉求拆成有序、可执行的步骤，标注依赖与优先级，输出清单式计划。' },
}
const cmdModeLabel = computed(() => (CMD_MODES[cmdMode.value] || CMD_MODES.chat).label)
// 原有孪生控制命令（首词命中即执行，其余一律当自然语言走聊天）
const KNOWN_CMDS = new Set(['help', 'run', 'sim', 'stop', 'reset', 'overview', 'home', 'patrol', 'view', 'edit', 'done', 'clear'])

async function runCmd() {
  const raw = cmdText.value.trim()
  if (!raw) return
  pushCmd(raw, 'cmd')
  hist.value.push(raw); histIdx = hist.value.length
  cmdText.value = ''
  if (store.pendingSaveStrategy) {        // 仿真模式：等待输入策略名称
    if (raw.toLowerCase() === 'cancel' || raw === '取消') {
      store.pendingSaveStrategy = false
      pushCmd('已取消保存策略。', 'sys')
    } else {
      try {
        const created = await store.saveCurrentAsStrategy(raw)
        store.pendingSaveStrategy = false
        pushCmd(`策略「${created?.name || raw}」已保存，可在左侧「策略」资源管理中查看并编辑。`, 'sys')
      } catch (e) {
        pushCmd(`保存失败：${e?.message || e}`, 'err')
      }
    }
    return
  }
  if (raw.startsWith('/')) { handleSlash(raw); return }
  const first = raw.split(/\s+/)[0].toLowerCase()
  if (KNOWN_CMDS.has(first)) { runTwinCommand(first, raw); return }
  if (store.simMode && cmdMode.value === 'chat') {   // 仿真模式：自然语言 → 智能体解析（规划中）
    pushCmd(`[智能体解析 · 规划中] 收到指令：「${raw}」。未来将由智能体解析为可执行操作，经您确认后自动应用于仿真并实时对比。当前可在仿真模式中手动调整参数，或点击左侧「策略」中的内置/自定义策略应用。`, 'warn')
    return
  }
  chatWithModel(raw)                         // 其余自然语言 → 直接对话
}

async function handleSlash(raw) {
  const c = raw.toLowerCase().trim()
  if (c === '/help' || c === '/?' || c === '/h') { pushCmd(helpText(), 'guide'); return }
  if (c === '/clear') { clearLog(); return }
  if (c === '/back') {
    if (cmdMode.value !== 'chat') { cmdMode.value = 'chat'; pushCmd('已回到「聊天」模式。', 'sys') }
    else pushCmd('当前已在聊天模式。', 'tip')
    return
  }
  if (c === '/sim') {
    if (store.simMode) pushCmd('已在仿真模式中：点击「退出仿真」或输入 stop 可退出。', 'tip')
    else props.actions.onSimToggle()
    return
  }
  if (c === '/quit' || c === '/exit') {
    if (cmdMode.value !== 'chat') { const m = CMD_MODES[cmdMode.value].label; cmdMode.value = 'chat'; pushCmd(`已退出「${m}」模式，回到聊天模式。`, 'sys') }
    else pushCmd('已处于聊天模式，直接输入即可对话，无需退出。', 'tip')
    return
  }
  const map = { '/code': 'code', '/plan': 'plan' }
  if (map[c]) {
    cmdMode.value = map[c]
    pushCmd(`已进入「${CMD_MODES[map[c]].label}」模式。输入 /quit 退出本模式，/back 回聊天。`, 'guide')
    return
  }
  pushCmd(`未知指令："${raw}"。输入 /help 查看可用命令与模式。`, 'err')
}

function runTwinCommand(c, raw) {
  const arg = raw.split(/\s+/).slice(1).join(' ').toLowerCase()
  switch (c) {
    case 'help': pushCmd(helpText(), 'guide'); break
    case 'run': case 'sim': props.actions.onSimToggle(); break
    case 'stop': props.actions.onSimToggle(); break
    case 'reset': props.actions.onResetView(); break
    case 'overview': case 'home': props.actions.onOverview(); break
    case 'patrol': props.actions.togglePatrol(); break
    case 'view': props.actions.focusSel(arg || 'focus'); break
    case 'edit': store.editMode ? null : props.actions.onToggleEdit(); break
    case 'done': store.editMode ? props.actions.onToggleEdit() : pushCmd('当前不在编排态。', 'tip'); break
    case 'clear': clearLog(); break
  }
}

async function chatWithModel(text) {
  const mode = cmdMode.value
  pushCmd('（思考中…）', 'bot')
  const idx = store.cmdLog.length - 1
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history: cmdChatHistory.value.slice(-10), mode }),
    })
    const data = await resp.json()
    const reply = data.reply != null ? String(data.reply) : '（无返回）'
    store.cmdLog.splice(idx, 1, { t: reply, k: data.ok === false ? 'err' : 'bot' })
    cmdChatHistory.value.push(['user', text])
    cmdChatHistory.value.push(['assistant', reply])
    if (cmdChatHistory.value.length > 22) cmdChatHistory.value = cmdChatHistory.value.slice(-22)
  } catch (e) {
    store.cmdLog.splice(idx, 1, { t: '（对话服务不可用：请确认后端已启动并配置了 LLM）', k: 'err' })
  }
  scrollLog()
}
function clearLog() { store.clearCmdLog() }
function histUp() { if (!hist.value.length) return; histIdx = Math.max(0, histIdx - 1); cmdText.value = hist.value[histIdx] || '' }
function histDown() { if (!hist.value.length) return; histIdx = Math.min(hist.value.length, histIdx + 1); cmdText.value = hist.value[histIdx] || '' }

// 全局 toast 提示 → 输出到命令行
watch(() => store.toast, (v) => {
  if (!v) return
  pushCmd(v, 'sys')
})

// 编排画布缩放变化 -> 命令行窗口显示当前放缩比例（滚轮/按钮/适配均会触发，节流避免刷屏）
let lastZoomLogT = 0
watch(() => Math.round(store.flowTf.scale * 100), (pct) => {
  const now = Date.now()
  if (now - lastZoomLogT < 400) return
  lastZoomLogT = now
  pushCmd('视图 >> 缩放：' + pct + '%', 'cmd')
})

defineExpose({ focusInput: () => { if (cmdInput.value) cmdInput.value.focus() } })
</script>
