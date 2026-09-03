<template>
  <div class="agent-view" :class="{ float: floatMode }" :style="floatMode ? floatStyle : {}">
    <!-- 历史对话面板（覆盖层） -->
    <div v-if="historyOpen" class="ai-hmask" @click.self="closeHistory">
      <div class="ai-hpanel">
        <div class="ai-hhead">
          <span class="ai-hname">{{ t('历史对话') }}</span>
          <button class="ai-hclose" :title="t('关闭')" @click="closeHistory">✕</button>
        </div>
        <div v-if="!sessions.length" class="ai-heempty">{{ t('暂无历史对话') }}</div>
        <div v-else class="ai-hlist">
          <div v-for="s in sessions" :key="s.id" class="ai-hrow" :class="{ on: s.id === sessionId }" @click="loadSession(s.id)">
            <div class="ai-hmain">
              <div class="ai-hname">{{ s.title }}</div>
              <div class="ai-hsub">{{ fmtTime(s.updated_at) }} · {{ s.message_count }} {{ t('条消息') }} · {{ t(agentName(s.agent)) }}</div>
            </div>
            <button class="ai-hdel" :title="t('删除会话')" @click.stop="removeSession(s.id)"><Icon name="trash" /></button>
          </div>
        </div>
      </div>
    </div>

    <!-- 统一标题栏：空闲/对话态共用，含历史对话 / 新对话 / 浮动(固定)；浮动弹窗为拖动区域 -->
    <div class="ai-titlebar" :class="{ draggable: floatMode }" @mousedown="onFloatDragStart">
      <div class="ai-logo"><Icon name="robot" /></div>
      <div class="ai-ttls">
        <div class="ai-title">{{ t('本析智擎') }}</div>
      </div>
      <div class="ai-titlebtns">
        <button class="at-btn" :title="t('查看历史对话')" @click="openHistory">{{ t('历史对话') }}</button>
        <button class="at-btn" :title="t('清空当前对话，开始新对话')" @click="newChat"><Icon name="trash" /> {{ t('新对话') }}</button>
        <button v-if="!floatMode" class="at-btn at-float" :title="t('以弹窗形式展示对话界面')" @click="toggleFloat">⧉ {{ t('浮动') }}</button>
        <button v-else class="at-btn at-float" :title="t('固定回右侧属性面板')" @click="toggleFloat">📌 {{ t('固定') }}</button>
      </div>
    </div>

    <!-- 空闲态：首屏大标题区 + 聊天输入框 -->
    <div v-if="messages.length === 0" class="agent-idle">
      <div class="ai-inner">
        <div class="ai-hero">
          <div class="ai-logo"><Icon name="robot" /></div>
          <div class="ai-hero-title">{{ t('本析智擎') }}</div>
          <div class="ai-hero-desc">{{ t('面向全行业的能碳智控助手：专业解答能碳指标、工艺策略与碳市场行情，支持知识库查询、设备数据、工艺仿真等能力。') }}</div>
        </div>
        <div class="agent-inputbox">
          <div class="ai-inputrow">
            <button class="ai-plus" :class="{ on: pickOpen }" :title="t('添加智能体 / 技能')" @click="togglePick($event)"></button>
            <textarea
              ref="idleInput"
              v-model="input"
              class="ai-textarea"
              rows="1"
              :placeholder="t('输入您的问题或者要求')"
              @keydown="onKeydown"
            ></textarea>
            <button class="ai-send" :disabled="thinking || !input.trim()" :title="t('发送')" @click="send"><Icon name="send" /></button>
          </div>
          <!-- 底部：当前智能体标签（点击可切换，默认通用助手时不显示） -->
          <div v-if="currentAgent.id !== 'general'" class="ai-bottomrow">
            <button class="ai-agent-tag" :title="t('切换智能体')" @click="openPick($event, 'agent')">
              <span class="ai-ae">{{ currentAgent.emoji }}</span>{{ t(currentAgent.name) }}<span class="ai-tag-arrow">▾</span>
            </button>
          </div>
        </div>
        <div class="ai-suggests">
          <button v-for="(s, i) in suggests" :key="i" class="ai-chip" @click="quickAsk(s)">{{ s }}</button>
        </div>
      </div>
    </div>

    <!-- 对话态：消息列表 + 输入框 -->
    <div v-else class="agent-chat">
      <div ref="msgList" class="ac-msgs">
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div v-if="m.role === 'assistant'" class="msg-avatar"><Icon name="robot" /></div>
          <div class="msg-wrap">
            <!-- 思考过程折叠面板：完成后默认收起，点击展开 -->
            <div v-if="m.role === 'assistant' && m.thoughts && m.thoughts.length" class="msg-thoughts">
              <button class="mt-toggle" :title="t('展开/收起思考过程')" @click="m.thoughtsOpen = !m.thoughtsOpen">
                <span class="mt-ic">🧠</span>
                <span>{{ t('思考过程') }}</span>
                <span class="mt-count">{{ m.thoughts.length }}</span>
                <span class="mt-arrow">{{ m.thoughtsOpen ? '▾' : '▸' }}</span>
              </button>
              <div v-if="m.thoughtsOpen" class="mt-body">
                <div v-for="(th, ti) in m.thoughts" :key="ti" class="mt-step">
                  <span class="mt-ic">{{ thoughtIcon(th.type) }}</span>
                  <span class="mt-text">{{ th.message }}</span>
                </div>
              </div>
            </div>
            <div class="msg-bubble">
              <div v-if="m.role !== 'user'" class="msg-meta">{{ t('本析智擎') }}</div>
              <div class="msg-content" v-html="m.html"></div>
            </div>
          </div>
        </div>
        <div v-if="waiting" class="msg-row assistant">
          <div class="msg-avatar"><Icon name="robot" /></div>
          <div class="msg-bubble thinking">
            <span class="tdot"></span><span class="tdot"></span><span class="tdot"></span>
            <span class="ttext">{{ statusText || t('本析智擎思考中…') }}</span>
          </div>
        </div>
      </div>
      <div class="ac-inputbar">
        <div class="agent-inputbox">
          <div class="ai-inputrow">
            <button class="ai-plus" :class="{ on: pickOpen }" :title="t('添加智能体 / 技能')" @click="togglePick($event)"></button>
            <textarea
              ref="chatInput"
              v-model="input"
              class="ai-textarea"
              rows="1"
              :placeholder="t('输入您的问题或者要求')"
              @keydown="onKeydown"
            ></textarea>
            <button class="ai-send" :disabled="thinking || !input.trim()" :title="t('发送')" @click="send"><Icon name="send" /></button>
          </div>
          <!-- 底部：当前智能体标签（点击可切换，默认通用助手时不显示） -->
          <div v-if="currentAgent.id !== 'general'" class="ai-bottomrow">
            <button class="ai-agent-tag" :title="t('切换智能体')" @click="openPick($event, 'agent')">
              <span class="ai-ae">{{ currentAgent.emoji }}</span>{{ t(currentAgent.name) }}<span class="ai-tag-arrow">▾</span>
            </button>
          </div>
        </div>
        <div class="ac-hint">{{ t('回答由大模型生成，仅供参考，请以实际设备数据为准') }}</div>
      </div>
    </div>

    <!-- 加号弹出菜单：智能体 / 技能 两级（fixed 定位，跟随 + 按钮/智能体标签） -->
    <div v-if="pickOpen" class="ai-pickmask" @click="closePick"></div>
    <div v-if="pickOpen" ref="pickMenu" class="ai-pickmenu" @mouseleave="closePick">
      <div class="ai-pickcol">
        <button class="ai-pickcol-item" :class="{ on: pickRoot === 'agent' }"
                @mouseenter="pickRoot = 'agent'" @click="pickRoot = 'agent'">
          {{ t('智能体') }}<span class="ai-pickarrow">›</span>
        </button>
        <button class="ai-pickcol-item" :class="{ on: pickRoot === 'skill' }"
                @mouseenter="pickRoot = 'skill'" @click="pickRoot = 'skill'">
          {{ t('技能') }}<span class="ai-pickarrow">›</span>
        </button>
      </div>
      <div class="ai-picksub">
        <template v-if="pickRoot === 'agent'">
          <button v-for="a in agents" :key="a.id" class="ai-pickopt" :class="{ on: a.id === selectedAgent }"
                  :title="t(a.description)" @click="pickAgent(a)">
            <span class="ai-ae">{{ a.emoji }}</span><span class="ai-popt-name">{{ t(a.name) }}</span>
            <em v-if="a.id === selectedAgent">✓</em>
          </button>
        </template>
        <template v-else>
          <button v-for="s in skillRows" :key="s.name" class="ai-pickopt"
                  :class="{ on: tagInInput(s.name), off: !s.allowed }"
                  :title="s.allowed ? t(s.description) : t('该技能不在当前智能体技能白名单内，请切换智能体')" @click="pickSkill(s)">
            <span class="ai-popt-name">{{ skillLabel(s.name) }}</span>
            <em v-if="tagInInput(s.name)">✓</em>
            <em v-else-if="!s.allowed" class="ai-off-tag">{{ t('需切换智能体') }}</em>
          </button>
          <div v-if="!skillRows.length" class="ai-pickempty">{{ t('暂无可用技能') }}</div>
        </template>
      </div>
    </div>

    <!-- 右下角拖拽手柄：仅浮动窗口可调整大小 -->
    <div v-if="floatMode" class="ai-resize-handle" :title="t('拖动调整浮动窗口大小')" @mousedown.prevent="onFloatResizeStart"></div>
  </div>
</template>

<script>
import { nextTick } from 'vue'
// echarts 按需引入：折线/柱状/饼图/散点 + 常用组件 + canvas 渲染
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import Icon from '../components/Icon.vue'
import { useSimStore } from '../stores/sim'
import { renderMarkdown } from '../utils/markdown'
import { t } from '../i18n'

echarts.use([
  LineChart, BarChart, PieChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, MarkLineComponent, CanvasRenderer,
])

export default {
  name: 'AgentChatView',
  components: { Icon },
  setup() { return { t } },
  data() {
    return {
      input: '',
      thinking: false, // 请求进行中（禁用发送按钮）
      waiting: false,  // 首个流式字符到达前显示「思考中…」气泡
      statusText: '',  // 当前思考/调用状态（thinking/reason/status/verify 提示）
      streamAbort: null, // 当前流式请求的中断控制器（「新对话」时中断进行中的回复）
      messages: [], // { role, content, html, thoughts: [], thoughtsOpen }
      suggests: [t('当前的设备都运转正常吗'), t('今年以来工厂一共排放了多少碳，消耗了多少能源'), t('给出各个工艺碳排放的实时占比'), t('高炉节能减碳的措施有哪些')],
      // 多智能体：智能体列表 / skills 列表 / 当前选择
      agents: [],
      skills: [],
      selectedAgent: 'general',
      selectedSkills: [],
      // 加号弹出菜单：智能体 / 技能 两级
      pickOpen: false,
      pickRoot: 'agent',
      // 历史对话
      sessions: [],
      historyOpen: false,
      sessionId: null,
      // 窗口模式：false=固定右侧属性面板（宽度由面板左侧手柄调节）；true=浮动弹窗
      floatMode: false,
      // 浮动弹窗的尺寸与位置（fixed 相对视口）
      floatRect: { w: 520, h: 640, x: 0, y: 0 },
      _skillLabels: {
        query_realtime_devices: '设备实时读数',
        query_device_history: '设备历史数据',
        run_simulation: '工艺仿真',
        get_carbon_market_quote: '碳市场行情',
        get_carbon_forecast: '碳价预测',
        get_emission_factors: '排放因子',
        query_knowledge: '知识库查询',
      },
    }
  },
  watch: {
    waiting(v) { if (v) this.scrollBottom() },
  },
  created() {
    this.store = useSimStore()
  },
  mounted() {
    // Esc 关闭加号菜单 / 历史浮层
    window.addEventListener('keydown', this._onEsc)
    // 对话内 echarts 图表实例表与 ResizeObserver（非响应式，避免 Vue 代理开销）
    this._chartInsts = new Map()
    this._chartObs = typeof ResizeObserver !== 'undefined' ? new ResizeObserver((entries) => {
      for (const en of entries) {
        const inst = this._chartInsts && this._chartInsts.get(en.target)
        if (inst && en.target.isConnected) inst.resize()
      }
    }) : null
    this.loadAgentsAndSkills()
    // 恢复浮动弹窗尺寸与位置（仅本析智擎，不受面板宽度影响）
    try {
      const raw = localStorage.getItem('agentFloatRect')
      if (raw) {
        const r = JSON.parse(raw)
        if (r && r.w > 0 && r.h > 0) {
          this.floatRect = { w: r.w, h: r.h, x: r.x || 0, y: r.y || 0 }
        }
      }
    } catch (e) { /* 忽略损坏数据 */ }
    this.$nextTick(() => { if (this.$refs.idleInput) this.$refs.idleInput.focus() })
  },
  computed: {
    // 当前选中的智能体（对话中锁定，不可切换）
    currentAgent() {
      return this.agents.find((a) => a.id === this.selectedAgent) || { id: 'general', name: '通用助手', emoji: '🤖' }
    },
    // 当前选中的智能体定义（白名单判断用）
    curAgentDef() {
      return this.agents.find((a) => a.id === this.selectedAgent) || {}
    },
    // 全部技能 + 白名单状态：技能菜单展示全部，不在白名单的标记「需切换智能体」
    skillRows() {
      const def = this.curAgentDef.default_skills || []
      return this.skills.slice().sort((a, b) => {
        const ia = def.includes(a.name) ? 0 : 1
        const ib = def.includes(b.name) ? 0 : 1
        return ia - ib || a.name.localeCompare(b.name)
      }).map((s) => ({ ...s, allowed: this.skillAllowed(s.name) }))
    },
    // 浮动弹窗样式（fixed 相对视口定位）
    floatStyle() {
      const r = this.floatRect
      return {
        width: r.w + 'px',
        height: r.h + 'px',
        left: r.x + 'px',
        top: r.y + 'px',
      }
    },
  },
  beforeDestroy() {
    this.disposeCharts()
    if (this._onEsc) {
      window.removeEventListener('keydown', this._onEsc)
      this._onEsc = null
    }
  },
  methods: {
    // Esc 关闭加号菜单 / 历史会话浮层
    _onEsc(e) {
      if (e.key !== 'Escape') return
      this.closePick()
      if (this.historyOpen) this.historyOpen = false
    },
    // —— 对话内 echarts 渲染（```echarts 代码块 → 折线图等）——
    // 流式渲染每帧都会重建 v-html DOM，用 rAF 节流统一扫描初始化
    scheduleCharts() {
      if (this._chartRaf) cancelAnimationFrame(this._chartRaf)
      this._chartRaf = requestAnimationFrame(() => {
        this._chartRaf = 0
        this.renderCharts()
      })
    },
    renderCharts() {
      if (!this._chartInsts) this._chartInsts = new Map()
      const root = this.$refs.msgList || this.$el
      if (!root) return
      // 清理已脱离文档的实例（v-html 流式重建会替换旧 DOM）
      for (const [el, inst] of Array.from(this._chartInsts.entries())) {
        if (!el.isConnected) { inst.dispose(); this._chartInsts.delete(el) }
      }
      root.querySelectorAll('.md-chart').forEach((el) => {
        if (this._chartInsts.has(el)) return
        let option = null
        try { option = JSON.parse(el.getAttribute('data-chart') || 'null') } catch (e) { option = null }
        if (!option || typeof option !== 'object' || Array.isArray(option)) {
          el.classList.add('md-chart-err')
          return
        }
        const inst = echarts.init(el)
        inst.setOption(this._normalizeChart(option))
        this._chartInsts.set(el, inst)
        if (this._chartObs) this._chartObs.observe(el)
      })
    },
    // 图表 option 兜底：未声明类型的 series 默认折线、缺失的轴/网格/提示补默认值
    _normalizeChart(opt) {
      const o = Object.assign({}, opt)
      const list = Array.isArray(o.series) ? o.series : (o.series ? [o.series] : [])
      o.series = list.filter(Boolean).map((s) => {
        const ns = Object.assign({}, s)
        if (!ns.type) ns.type = 'line'
        if (ns.type === 'line' && ns.smooth === undefined) ns.smooth = true
        return ns
      })
      if (!o.tooltip) o.tooltip = { trigger: 'axis' }
      if (!o.grid) o.grid = { left: 16, right: 16, top: 38, bottom: 26, containLabel: true }
      if (!o.xAxis) o.xAxis = { type: 'category', boundaryGap: false, data: [] }
      if (!o.yAxis) o.yAxis = { type: 'value', scale: true }
      if (!o.legend) o.legend = { top: 2, textStyle: { color: '#8a94a6' } }
      if (o.animation === undefined) o.animation = false // 流式渲染期间禁用动画避免卡顿
      return o
    },
    disposeCharts() {
      if (this._chartObs) { this._chartObs.disconnect(); this._chartObs = null }
      if (this._chartInsts) { this._chartInsts.forEach((inst) => inst.dispose()); this._chartInsts.clear() }
      if (this._chartRaf) { cancelAnimationFrame(this._chartRaf); this._chartRaf = 0 }
    },
    // —— 历史对话 ——
    async loadSessions() {
      try {
        const resp = await fetch('/api/chat/sessions')
        const data = await resp.json()
        this.sessions = (data && data.sessions) || []
      } catch (e) { this.sessions = [] }
    },
    openHistory() {
      this.historyOpen = true
      this.loadSessions()
    },
    closeHistory() { this.historyOpen = false },
    async loadSession(id) {
      try {
        const resp = await fetch('/api/chat/sessions/' + id)
        const data = await resp.json()
        if (!data || !data.ok) return
        const s = data.session
        this.messages = (s.messages || []).map((m) => (m.role === 'assistant'
          ? { role: 'assistant', content: m.content, html: renderMarkdown(m.content), thoughts: [], thoughtsOpen: false }
          : { role: 'user', content: m.content, html: renderMarkdown(m.content) }))
        this.selectedAgent = s.agent || 'general'
        this.selectedSkills = (s.skills || []).slice()
        this.sessionId = s.id
        this.historyOpen = false
        this.waiting = false
        this.thinking = false
        this.$nextTick(() => {
          this.scheduleCharts()
          this.scrollBottom()
          if (this.$refs.chatInput) this.$refs.chatInput.focus()
        })
      } catch (e) { /* 保持现状 */ }
    },
    async removeSession(id) {
      try {
        await fetch('/api/chat/sessions/' + id, { method: 'DELETE' })
      } catch (e) { /* 忽略 */ }
      if (this.sessionId === id) { this.sessionId = null }
      this.loadSessions()
    },
    async ensureSession(text, skills) {
      if (this.sessionId) return this.sessionId
      try {
        const resp = await fetch('/api/chat/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent: this.selectedAgent,
            skills: (skills || []).slice(),
            title: text.slice(0, 24),
          }),
        })
        const data = await resp.json()
        if (data && data.ok) this.sessionId = data.session.id
      } catch (e) { /* 后端不可用时静默降级（不阻断对话） */ }
      return this.sessionId
    },
    async saveMessages(sid, pairs, agent, skills) {
      if (!sid) return
      for (const [role, content] of pairs) {
        try {
          await fetch(`/api/chat/sessions/${sid}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role, content, agent, skills }),
          })
        } catch (e) { /* 忽略 */ }
      }
      this.loadSessions()
    },
    // —— 智能体 / 技能 ——
    async loadAgentsAndSkills() {
      try {
        const [ra, rs] = await Promise.all([
          fetch('/api/agents').then((r) => r.json()),
          fetch('/api/skills').then((r) => r.json()),
        ])
        this.agents = (ra && ra.agents) || []
        this.skills = (rs && rs.skills) || []
        const def = this.agents.find((a) => a.id === 'general')
        if (def) this.selectedSkills = (def.default_skills || []).slice()
      } catch (e) { /* 后端不可用时保持默认 */ }
    },
    selectAgent(a) {
      this.selectedAgent = a.id
      const def = (a.default_skills || []).slice()
      const allow = a.available_skills
      this.selectedSkills = allow ? def.filter((n) => allow.includes(n)) : def
    },
    // 技能是否在当前智能体白名单内（available_skills 未设置 = 不限）
    skillAllowed(name) {
      const allow = this.curAgentDef.available_skills
      return !allow || allow.includes(name)
    },
    // —— 加号弹出菜单：智能体 / 技能 ——
    togglePick(e) {
      if (this.pickOpen) { this.closePick(); return }
      this.openPick(e, this.pickRoot || 'agent')
    },
    openPick(e, root) {
      this._pickAnchor = (e && e.currentTarget) ? e.currentTarget.getBoundingClientRect() : null
      this.pickRoot = root || 'agent'
      this.pickOpen = true
      this.$nextTick(() => this.positionPick())
    },
    closePick() {
      this.pickOpen = false
      this._pickAnchor = null
    },
    positionPick() {
      const menu = this.$refs.pickMenu
      if (!menu) return
      const r = this._pickAnchor
      if (!r) { menu.style.left = '12px'; menu.style.top = '80px'; return }
      const mw = 336
      const mh = menu.offsetHeight || 220
      let left = r.left
      let top = r.top - mh - 8
      if (top < 8) top = r.bottom + 8
      if (left + mw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - mw - 8)
      menu.style.left = left + 'px'
      menu.style.top = top + 'px'
    },
    pickAgent(a) {
      this.selectAgent(a)
      this.closePick()
    },
    pickSkill(s) {
      // 白名单校验：技能不在当前智能体白名单内 → 提示切换智能体，不插入、保持菜单打开
      if (!s.allowed) {
        this.store.showToast(t('技能「{name}」不在智能体「{agent}」的技能白名单内，请切换智能体')
          .replace('{name}', this.skillLabel(s.name)).replace('{agent}', t(this.currentAgent.name)), 'warn')
        return
      }
      this.insertTag(s)
      this.closePick()
    },
    // 技能以 #技能名 插入输入框文本中（可重复添加多个）
    insertTag(s) {
      const label = this.skillLabel(s.name)
      if (this.tagInInput(s.name)) return
      const sep = this.input && !this.input.endsWith(' ') ? ' ' : ''
      this.input = this.input + sep + '#' + label + ' '
      this.$nextTick(() => {
        const el = this.$refs.idleInput || this.$refs.chatInput
        if (el) { el.focus(); el.setSelectionRange(this.input.length, this.input.length) }
      })
    },
    tagInInput(name) {
      return this.input.indexOf('#' + this.skillLabel(name)) >= 0
    },
    // 解析文本中的 #技能名：匹配技能名或显示名，命中后收集为技能并移出文本
    parseTaggedSkills() {
      let text = this.input
      const re = /#[^\s#，,。；;]+/g
      const found = text.match(re) || []
      const skills = []
      const matched = []
      for (const raw of found) {
        const tg = raw.slice(1)
        const hit = this.skills.find((s) => s.name === tg || this.skillLabel(s.name) === tg)
        if (hit) {
          if (skills.indexOf(hit.name) < 0) skills.push(hit.name)
          matched.push(raw)
        }
      }
      for (const raw of matched) text = text.split(raw).join('')
      return { text: text.replace(/\s{2,}/g, ' ').trim(), skills }
    },
    skillLabel(name) {
      if (name.indexOf('__') >= 0) {
        // mcp__server__tool → 显示 tool 名（第三方 MCP 技能）
        return name.split('__').pop()
      }
      return this._skillLabels[name] || name
    },
    agentName(id) {
      const a = this.agents.find((x) => x.id === id)
      return a ? a.name : id
    },
    fmtTime(str) {
      return str ? String(str).slice(5, 16) : ''
    },
    thoughtIcon(type) {
      return { thinking: '🧭', reason: '🧠', plan: '🗺️', status: '🔧', verify: '✅' }[type] || '💬'
    },
    // —— 对话 ——
    onKeydown(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send() }
    },
    quickAsk(q) { this.input = q; this.send() },
    pushAssistant(content, extra = {}) {
      this.messages.push(Object.assign({
        role: 'assistant', content, html: renderMarkdown(content), thoughts: [], thoughtsOpen: false,
      }, extra))
      this.scheduleCharts()
    },
    async send() {
      // 解析文本中的 #技能名 标记 → 提取为本次调用的技能，并从文本移除
      const parsed = this.parseTaggedSkills()
      // 白名单校验：技能不在当前智能体白名单内 → 提示并阻止发送（保留输入内容）
      const banned = parsed.skills.filter((n) => !this.skillAllowed(n))
      if (banned.length) {
        this.store.showToast(t('技能「{name}」不在智能体「{agent}」的技能白名单内，请切换智能体')
          .replace('{name}', this.skillLabel(banned[0])).replace('{agent}', t(this.currentAgent.name)), 'warn')
        return
      }
      const text = parsed.text
      if (!text || this.thinking) return
      this.input = ''
      const skills = parsed.skills
      if (skills.length) this.selectedSkills = skills.slice()
      const sid = await this.ensureSession(text, skills) // 首次发送时创建历史会话
      this.messages.push({ role: 'user', content: text, html: renderMarkdown(text) })
      this.waiting = true
      this.thinking = true
      this.scrollBottom()
      const history = this.messages.slice(0, -1).map((m) => [m.role, m.content]).slice(-20)
      const payload = {
        text,
        history,
        mode: 'chat',
        agent: this.selectedAgent,
        skills: skills.slice(),
      }
      let ok = false
      const ctrl = new AbortController()
      this.streamAbort = ctrl
      try {
        ok = await this.streamChat(payload, ctrl.signal)
      } catch (e) {
        ok = false
      }
      if (!ok) {
        // 流式接口不可用时兜底到非流式 /api/chat（思考过程已展示时填充已有消息，避免重复气泡）
        const fill = (reply) => {
          const last = this.messages[this.messages.length - 1]
          if (last && last.role === 'assistant' && last.content === '' && last.thoughts && last.thoughts.length) {
            last.content = reply
            last.html = renderMarkdown(reply)
          } else {
            this.pushAssistant(reply, { thoughts: this._pendingThoughts ? this._pendingThoughts.slice() : [] })
          }
          this.scheduleCharts()
        }
        try {
          const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: ctrl.signal,
          })
          const data = await resp.json()
          fill(data && data.reply != null ? String(data.reply) : t('（无返回内容）'))
        } catch (e2) {
          if (!(e2 && e2.name === 'AbortError')) fill(t('（对话服务不可用：请确认后端已启动并配置了 LLM）'))
        }
      }
      this.streamAbort = null
      this.waiting = false
      this.thinking = false
      // 回写历史会话（user + assistant 消息），并同步会话的智能体/技能元数据（新对话中断后不写回）
      const last = this.messages[this.messages.length - 1]
      const replyText = (last && last.role === 'assistant') ? last.content : t('（无返回内容）')
      if (sid && this.sessionId === sid) this.saveMessages(sid, [['user', text], ['assistant', replyText]], this.selectedAgent, skills)
      this.scrollBottom()
    },
    // 流式回复：SSE 逐段解析事件（thinking/reason/status/verify=思考过程 / delta=增量文本）
    async streamChat(payload, signal) {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, mode: 'chat' }),
        signal,
      })
      if (!resp.ok || !resp.body) return false
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      let acc = ''
      let started = false
      let shown = false // 是否已渲染流式消息（思考事件或首个 delta 触发）
      let thoughts = [] // 当前回复的思考过程步骤（thinking/reason/status/verify）
      // 思考过程事件到达即渲染消息（无需等首个 delta），后续步骤实时更新
      const ensureMsg = () => {
        const last = this.messages[this.messages.length - 1]
        if (!shown) {
          shown = true
          this.waiting = false // 思考过程已展示，收起「思考中…」
          this._pendingThoughts = thoughts
          // 流式期间思考过程保持展开，完成后折叠
          this.pushAssistant('', { thoughts: thoughts.slice(), thoughtsOpen: true })
        } else if (last && last.role === 'assistant') {
          last.thoughts = thoughts.slice() // 增量步骤实时更新
        }
        this.scrollBottom()
      }
      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          let nl
          while ((nl = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, nl).trim()
            buf = buf.slice(nl + 1)
            if (!line.startsWith('data:')) continue
            const payload2 = line.slice(5).trim()
            if (!payload2 || payload2 === '[DONE]') continue
            let evt
            try { evt = JSON.parse(payload2) } catch (e) { continue }
            // 思考过程事件：thinking=阶段提示，plan=调度智能体规划，reason=子智能体决策/本体命中，status=技能调用，verify=验收
            if (['thinking', 'plan', 'reason', 'status', 'verify'].includes(evt.type) && evt.message) {
              thoughts.push({ type: evt.type, message: evt.message })
              this.statusText = evt.message
              ensureMsg()
              continue
            }
            if (!evt || typeof evt.delta !== 'string' || !evt.delta) continue
            ensureMsg()
            if (!started) {
              started = true
              this.statusText = ''
            }
            acc += evt.delta
            const m = this.messages[this.messages.length - 1]
            m.content = acc
            m.html = renderMarkdown(acc)
            this.scheduleCharts()
            this.scrollBottom()
          }
        }
      } catch (e) {
        if (e && e.name === 'AbortError') {
          // 用户点「新对话」中断流式回复：静默结束，交由 newChat 清理界面
          this.thinking = false
          this.waiting = false
          this.statusText = ''
          return true
        }
        throw e
      }
      this._pendingThoughts = thoughts
      if (!started) return false
      if (!acc) {
        const m = this.messages[this.messages.length - 1]
        m.content = t('（无返回内容）')
        m.html = renderMarkdown(t('（无返回内容）'))
      }
      // 完成最终答案：思考过程折叠起来（默认收起，点击可展开）
      const last = this.messages[this.messages.length - 1]
      if (last && last.role === 'assistant' && last.thoughts) last.thoughtsOpen = false
      return true
    },
    newChat() {
      // 回复进行中：中断流式请求再清空（取消后 thinking 由 streamChat 收尾复位）
      if (this.thinking && this.streamAbort) this.streamAbort.abort()
      this.disposeCharts()
      this.messages = []
      this.input = ''
      this.sessionId = null // 下一条消息开启新会话
      this.$nextTick(() => { if (this.$refs.idleInput) this.$refs.idleInput.focus() })
    },
    scrollBottom() {
      nextTick(() => {
        const el = this.$refs.msgList
        if (el) el.scrollTop = el.scrollHeight
      })
    },
    // —— 窗口模式：固定右侧面板 / 浮动弹窗 ——
    // 固定模式铺满右侧属性面板，宽度由面板左侧手柄（inspector-rsz）调节；
    // 浮动模式为独立弹窗：标题栏拖动移动、右下角手柄调整大小，点击「固定」回面板。
    toggleFloat() {
      this.floatMode = !this.floatMode
      if (this.floatMode) {
        this._initFloatRect()
        // 浮动模式：本析智擎已弹出为独立窗口，右侧属性栏不再承载内容，收起以免空白占位
        this.store.rightOpen = false
      } else {
        // 固定模式：回到右侧属性面板，重新展开右侧栏
        this.store.rightOpen = true
      }
    },
    _initFloatRect() {
      const cur = this.floatRect
      const vw = window.innerWidth || 1440
      const vh = window.innerHeight || 900
      if (cur.w > 0 && cur.h > 0) {
        // 尺寸或位置超出视口时（右下角出界），整体收进视口避免拖不到手柄
        if (cur.x + cur.w > vw || cur.y + cur.h > vh) {
          const w = Math.min(cur.w, vw - 16)
          const h = Math.min(cur.h, vh - 128)
          this.floatRect = { ...cur, w, h, x: Math.max(0, vw - w - 40), y: 64 }
        }
        return
      }
      const parent = this.$el.parentElement
      const pw = parent ? parent.clientWidth : 440
      const w = Math.min(560, Math.max(400, pw))
      this.floatRect = {
        w,
        h: Math.min(760, Math.max(520, vh - 160)),
        x: Math.max(0, vw - w - 32),
        y: 64,
      }
    },
    onFloatDragStart(e) {
      if (e.button !== 0 || !this.floatMode) return
      const tag = e.target.closest && e.target.closest('button, a, input, textarea')
      if (tag) return
      this._fd = {
        sx: e.clientX, sy: e.clientY,
        ox: this.floatRect.x, oy: this.floatRect.y,
      }
      window.addEventListener('mousemove', this.onFloatDragMove)
      window.addEventListener('mouseup', this.onFloatDragEnd)
      e.preventDefault()
    },
    onFloatDragMove(e) {
      if (!this._fd) return
      const d = this._fd
      this.floatRect = {
        ...this.floatRect,
        x: Math.max(-this.floatRect.w + 120, Math.min(window.innerWidth - 60, d.ox + (e.clientX - d.sx))),
        y: Math.max(0, Math.min(window.innerHeight - 48, d.oy + (e.clientY - d.sy))),
      }
    },
    onFloatDragEnd() {
      if (!this._fd) return
      this._fd = null
      window.removeEventListener('mousemove', this.onFloatDragMove)
      window.removeEventListener('mouseup', this.onFloatDragEnd)
      this.saveFloatState()
    },
    onFloatResizeStart(e) {
      e.preventDefault()
      this._rs = {
        sx: e.clientX, sy: e.clientY,
        sw: this.floatRect.w, sh: this.floatRect.h,
      }
      window.addEventListener('mousemove', this.onFloatResizeMove)
      window.addEventListener('mouseup', this.onFloatResizeEnd)
    },
    onFloatResizeMove(e) {
      if (!this._rs) return
      const d = this._rs
      const w = Math.max(360, Math.min(window.innerWidth - 16, d.sw + (e.clientX - d.sx)))
      const h = Math.max(420, Math.min(window.innerHeight - 16, d.sh + (e.clientY - d.sy)))
      const r = this.floatRect
      // 放大后保持窗口整体在视口内：右下角出界时自动左/上移（手柄始终可拖）
      const nx = Math.max(0, Math.min(r.x, window.innerWidth - 16 - w))
      const ny = Math.max(0, Math.min(r.y, window.innerHeight - 16 - h))
      this.floatRect = { ...r, w, h, x: nx, y: ny }
    },
    onFloatResizeEnd() {
      this._rs = null
      window.removeEventListener('mousemove', this.onFloatResizeMove)
      window.removeEventListener('mouseup', this.onFloatResizeEnd)
      this.saveFloatState()
    },
    saveFloatState() {
      try {
        localStorage.setItem('agentFloatRect', JSON.stringify(this.floatRect))
      } catch (e) { /* 忽略 */ }
    },
  },
}
</script>

<style scoped>
.agent-view {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 8;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: var(--bg);
  overflow: hidden;
}
/* 浮动弹窗：fixed 相对视口，独立悬浮展示。
   right-collapsed 时父级 .inspector 会继承 visibility:hidden / pointer-events:none，
   需在此显式覆盖（visibility/pointer-events 为继承属性，子元素可覆盖），否则浮动窗随属性栏一起隐藏 */
.agent-view.float {
  position: fixed;
  z-index: 400;
  visibility: visible;
  pointer-events: auto;
  width: auto;
  height: auto;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 14px 44px rgba(0, 0, 0, .24), 0 2px 8px rgba(0, 0, 0, .12);
  overflow: hidden;
}
.at-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--panel-2);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.at-btn svg { width: 13px; height: 13px; }
.at-btn:hover { border-color: var(--accent-d); color: var(--accent-d); }
/* 浮动 / 固定 切换按钮：强调色 */
.at-float {
  border-color: var(--accent-l);
  color: var(--accent-d);
  background: var(--accent-l);
}
.at-float:hover { background: var(--accent); color: #fff; border-color: var(--accent-d); }
/* 空闲态标题栏按钮组 */
.ai-titlebtns {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 右下角拖拽调整窗口大小（本析智擎窗口可自由调整大小） */
.ai-resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 22px;
  height: 22px;
  z-index: 12;
  cursor: nwse-resize;
}
.ai-resize-handle::after {
  content: '';
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 10px;
  height: 10px;
  border-right: 2px solid var(--faint);
  border-bottom: 2px solid var(--faint);
  border-radius: 0 0 4px 0;
  opacity: .6;
}
.ai-resize-handle:hover::after { border-color: var(--accent-d); opacity: 1; }
/* 标题栏：仅浮动弹窗可拖动；固定模式由右侧面板左侧手柄调节宽度 */
.ai-titlebar { cursor: default; }
.agent-view.float .ai-titlebar { cursor: grab; }
.agent-view.float .ai-titlebar:active { cursor: grabbing; }

/* —— 历史对话面板 —— */
.ai-hmask {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, .28);
}
.ai-hpanel {
  width: min(560px, 88%);
  max-height: 76%;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, .22);
  overflow: hidden;
}
.ai-hhead {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.ai-hclose {
  width: 26px; height: 26px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.ai-hclose:hover { color: var(--accent-d); background: var(--accent-l); }
.ai-hlist { flex: 1; overflow-y: auto; padding: 8px; }
.ai-heempty {
  padding: 40px 0;
  text-align: center;
  color: var(--faint);
  font-size: 13px;
}
.ai-hrow {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .12s;
}
.ai-hrow:hover { background: var(--panel-2); }
.ai-hrow.on { background: var(--accent-l); }
.ai-hmain { flex: 1; min-width: 0; }
.ai-hname {
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-hrow.on .ai-hname { color: var(--accent-d); font-weight: 600; }
.ai-hsub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--faint);
}
.ai-hdel {
  flex: none;
  width: 26px; height: 26px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--faint);
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s;
}
.ai-hrow:hover .ai-hdel { opacity: 1; }
.ai-hdel svg { width: 13px; height: 13px; }
.ai-hdel:hover { color: #e5534b; background: rgba(229, 83, 75, .1); }

/* —— 空闲态：居中大输入框 —— */
.agent-idle {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: 30px 20px;
}
.ai-inner { width: 100%; max-width: 680px; display: flex; flex-direction: column; align-items: center; gap: 12px; }
/* 统一标题栏：空闲/对话态共用，浮动弹窗拖动区域 */
.ai-titlebar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 0 12px;
  height: 46px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}
.ai-ttls { flex: 1; min-width: 0; }
.ai-histbtn { flex: none; }
.ai-logo {
  flex: none;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px;
  background: var(--accent-l);
  color: var(--accent-d);
}
.ai-logo svg { width: 17px; height: 17px; }
.ai-title { font-size: 13.5px; font-weight: 700; color: var(--text); line-height: 1.2; }
.ai-desc { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.4; }
/* 空闲态首屏：大图标 + 标题 + 介绍（输入框上方） */
.ai-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
}
.ai-hero .ai-logo {
  width: 56px; height: 56px;
  border-radius: 50%;
  background: var(--accent-l);
  color: var(--accent-d);
}
.ai-hero .ai-logo svg { width: 30px; height: 30px; }
.ai-hero-title { font-size: 20px; font-weight: 700; color: var(--text); line-height: 1.2; }
.ai-hero-desc { font-size: 12.5px; color: var(--muted); line-height: 1.6; max-width: 560px; }
.agent-inputbox {
  width: 100%;
  margin-top: 8px;
  padding: 8px 8px 8px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  box-shadow: 0 2px 10px rgba(0, 0, 0, .06);
  transition: border-color .15s, box-shadow .15s;
}
/* 聚焦时保持中性边框，不出现主题色描边 */
.agent-inputbox:focus-within { border-color: var(--border); box-shadow: 0 1px 8px rgba(0, 0, 0, .08); }
.ai-inputrow { display: flex; align-items: flex-end; gap: 8px; }
/* 空闲态（初始输入框）更高、更醒目 */
.agent-idle .agent-inputbox { padding: 12px 10px 12px 16px; }
.agent-idle .ai-textarea { min-height: 50px; font-size: 15px; }
.ai-textarea {
  flex: 1;
  border: none;
  outline: none;
  box-shadow: none; /* 覆盖全局 textarea:focus 的内部选中光环 */
  resize: none;
  background: transparent;
  font-size: 14px;
  font-family: var(--ui);
  color: var(--text);
  line-height: 1.6;
  max-height: 160px;
  padding: 4px 0;
}
.ai-textarea::placeholder { color: var(--faint); }
.ai-textarea:focus, .ai-textarea:focus-visible { outline: none; box-shadow: none; }
.ai-send {
  flex: none;
  width: 34px; height: 34px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  transition: background .15s;
}
.ai-send svg { width: 16px; height: 16px; }
.ai-send:hover:not(:disabled) { background: var(--accent-d); }
.ai-send:disabled { background: var(--border); cursor: not-allowed; }
/* 加号按钮：纯加号（伪元素十字），点击旋转 45° 变 × */
.ai-plus {
  flex: none;
  width: 22px;
  height: 22px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--muted);
  border-radius: 6px;
  cursor: pointer;
  transition: color .15s, background .15s;
}
.ai-plus::before, .ai-plus::after {
  content: '';
  position: absolute;
  background: currentColor;
  border-radius: 2px;
  transition: transform .2s ease;
}
.ai-plus::before { width: 12px; height: 2px; }
.ai-plus::after { width: 2px; height: 12px; }
.ai-plus:hover, .ai-plus.on { color: var(--accent-d); background: var(--accent-l); }
.ai-plus.on::before, .ai-plus.on::after { transform: rotate(45deg); }
/* 底部行：当前智能体标签（点击可切换） */
.ai-bottomrow {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding-top: 7px;
  border-top: 1px dashed var(--border);
}
.ai-agent-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  border: 1px solid var(--accent);
  border-radius: 12px;
  background: var(--accent-l);
  color: var(--accent-d);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
}
.ai-agent-tag:hover { border-color: var(--accent-d); background: var(--accent-l); }
.ai-agent-tag .ai-ae { font-size: 11.5px; }
.ai-tag-arrow { font-size: 9px; color: var(--accent-d); opacity: .7; }
/* 加号弹出菜单（fixed 全屏遮罩 + 两级菜单） */
.ai-pickmask {
  position: fixed;
  inset: 0;
  z-index: 60;
}
.ai-pickmenu {
  position: fixed;
  z-index: 61;
  display: flex;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .2);
  overflow: hidden;
}
.ai-pickcol {
  flex: none;
  width: 112px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--panel-2);
}
.ai-pickcol-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 34px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 13px;
  color: var(--text);
  text-align: left;
  cursor: pointer;
}
.ai-pickcol-item:hover, .ai-pickcol-item.on { background: var(--accent-l); color: var(--accent-d); }
.ai-pickarrow { font-size: 13px; color: var(--faint); }
.ai-pickcol-item.on .ai-pickarrow { color: var(--accent-d); }
.ai-picksub {
  flex: none;
  width: 222px;
  max-height: 248px;
  overflow-y: auto;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ai-pickopt {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 12.5px;
  color: var(--text);
  text-align: left;
  cursor: pointer;
}
.ai-pickopt:hover { background: var(--accent-l); color: var(--accent-d); }
.ai-pickopt .ai-ae { font-size: 12px; }
.ai-pickopt.on { color: var(--accent-d); font-weight: 600; }
.ai-popt-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-pickopt em { font-style: normal; color: var(--accent-d); font-size: 12px; }
.ai-pickempty { padding: 16px 12px; text-align: center; color: var(--faint); font-size: 12px; }
/* 不在当前智能体白名单内的技能：置灰不可用，提示切换智能体 */
.ai-pickopt.off { opacity: .5; cursor: not-allowed; }
.ai-pickopt.off:hover { background: transparent; color: var(--text); }
.ai-pickopt.off .ai-popt-name { color: var(--faint); }
.ai-off-tag { font-style: normal; font-size: 10px; color: #c8a04a; }
/* 顶栏「恢复铺满」按钮 */
/* 浮动窗口背景遮罩由 .agent-view.float 自带 */

.ai-suggests { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 8px; }
.ai-chip {
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 15px;
  background: var(--panel);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}
.ai-chip:hover { border-color: var(--accent-d); color: var(--accent-d); background: var(--accent-l); }

/* —— 对话态 —— */
.agent-chat { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }
.ac-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 12px 24px 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg-row { display: flex; gap: 10px; max-width: 100%; }
.msg-row.user { flex-direction: row-reverse; }
.msg-wrap { max-width: 82%; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.msg-row.user .msg-wrap { align-items: flex-end; }
.msg-avatar {
  flex: none;
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--accent-l);
  color: var(--accent-d);
}
.msg-avatar svg { width: 17px; height: 17px; }
.msg-bubble {
  max-width: 100%;
  padding: 9px 13px;
  border-radius: 10px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.msg-row.user .msg-bubble {
  background: var(--accent);
  border-color: var(--accent-d);
}
.msg-meta { font-size: 11px; color: var(--faint); margin-bottom: 4px; }
.msg-row.user .msg-meta { color: rgba(255, 255, 255, .75); text-align: right; }
.msg-content { font-size: 13.5px; color: var(--text); line-height: 1.7; word-break: break-word; }
.msg-row.user .msg-content { color: #fff; white-space: pre-wrap; }
.msg-content :deep(p) { margin: 4px 0; }
.msg-content :deep(p:first-child) { margin-top: 0; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(h1), .msg-content :deep(h2), .msg-content :deep(h3), .msg-content :deep(h4) {
  margin: 10px 0 6px; font-size: 15px; color: var(--text);
}
.msg-content :deep(ul), .msg-content :deep(ol) { margin: 4px 0; padding-left: 20px; }
.msg-content :deep(li) { margin: 2px 0; }
.msg-content :deep(code) {
  font-family: var(--mono); font-size: 12.5px;
  background: var(--panel-3); border-radius: 3px; padding: 1px 4px;
}
.msg-content :deep(pre) { background: var(--rail); color: #E6E6E6; border-radius: 8px; padding: 10px 12px; overflow-x: auto; margin: 6px 0; }
.msg-content :deep(pre code) { background: transparent; padding: 0; color: inherit; }
/* 代码块：语言标注角标（```python 等） */
.msg-content :deep(pre.rp-code) { position: relative; }
.msg-content :deep(pre.rp-code[data-lang])::after {
  content: attr(data-lang);
  position: absolute;
  top: 6px; right: 10px;
  font-size: 10.5px;
  letter-spacing: .5px;
  text-transform: uppercase;
  color: rgba(230, 230, 230, .45);
}
/* echarts 图表容器（```echarts 代码块） */
.msg-content :deep(.md-chart) {
  position: relative;
  height: 280px;
  margin: 8px 0;
  border-radius: 8px;
  background: #0d1524;
  border: 1px solid var(--border);
  overflow: hidden;
}
.msg-content :deep(.md-chart-fallback) { border: none; background: transparent; color: rgba(230, 230, 230, .55); font-size: 11px; }
.msg-content :deep(.md-chart-err)::after {
  content: '（图表数据解析失败）';
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--faint);
  font-size: 12px;
  pointer-events: none;
}
.msg-content :deep(.md-chart-err .md-chart-fallback) { display: none; }
.msg-content :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 12.5px; }
.msg-content :deep(th), .msg-content :deep(td) { border: 1px solid var(--border); padding: 4px 8px; }
.msg-content :deep(th) { background: var(--panel-3); }
.msg-content :deep(blockquote) { border-left: 3px solid var(--accent); padding-left: 10px; margin: 6px 0; color: var(--muted); }
.msg-content :deep(strong) { font-weight: 600; }

/* —— 思考过程折叠面板 —— */
.msg-thoughts {
  align-self: flex-start;
  max-width: 100%;
}
.msg-row.user .msg-thoughts { display: none; }
.mt-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel-2);
  color: var(--muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: all .15s;
}
.mt-toggle:hover { border-color: var(--accent-d); color: var(--accent-d); }
.mt-ic { font-size: 11px; line-height: 1; }
.mt-count {
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--accent-l);
  color: var(--accent-d);
  font-size: 10px;
  font-weight: 600;
}
.mt-arrow { font-size: 10px; color: var(--faint); }
.mt-body {
  margin-top: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  background: var(--panel-2);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mt-step {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
}
.mt-step .mt-ic { margin-top: 2px; }
.mt-step .mt-text { word-break: break-word; }

.msg-bubble.thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: 13px;
}
.tdot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent);
  animation: tdot-blink 1.2s infinite ease-in-out;
}
.tdot:nth-child(2) { animation-delay: .15s; }
.tdot:nth-child(3) { animation-delay: .3s; }
@keyframes tdot-blink { 0%, 60%, 100% { opacity: .25; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }

.ac-inputbar {
  flex: none;
  padding: 12px 24px 10px;
  background: var(--bg);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ac-inputbar .agent-inputbox { margin-top: 0; box-shadow: none; }
.ac-hint { font-size: 11px; color: var(--faint); text-align: center; }

/* —— 适配右侧属性面板（窄面板） —— */
.ac-msgs { padding: 12px 14px 8px; }
.ac-inputbar { padding: 10px 14px 8px; }
.agent-idle { padding: 24px 16px; }
</style>
