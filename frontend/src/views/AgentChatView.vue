<template>
  <div class="agent-view">
    <!-- 空闲态：仅聊天输入框 -->
    <div v-if="messages.length === 0" class="agent-idle">
      <div class="ai-inner">
        <div class="ai-logo"><Icon name="robot" /></div>
        <div class="ai-title">{{ t('本析智擎') }}</div>
        <div class="ai-desc">{{ t('我是本析智擎，只接受钢铁企业节能减碳及系统相关数据的问询与策略，不闲聊') }}</div>
        <div class="agent-inputbox">
          <textarea
            ref="idleInput"
            v-model="input"
            class="ai-textarea"
            rows="1"
            :placeholder="t('输入你的问题，回车发送，Shift+Enter 换行')"
            @keydown="onKeydown"
          ></textarea>
          <button class="ai-send" :disabled="thinking || !input.trim()" :title="t('发送')" @click="send"><Icon name="send" /></button>
        </div>
        <div class="ai-suggests">
          <button v-for="(s, i) in suggests" :key="i" class="ai-chip" @click="quickAsk(s)">{{ s }}</button>
        </div>
      </div>
    </div>

    <!-- 对话态：消息列表 + 输入框 -->
    <div v-else class="agent-chat">
      <button class="at-btn at-new" @click="newChat" :title="t('清空当前对话，开始新对话')"><Icon name="trash" /> {{ t('新对话') }}</button>
      <div ref="msgList" class="ac-msgs">
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div v-if="m.role === 'assistant'" class="msg-avatar"><Icon name="robot" /></div>
          <div class="msg-bubble">
            <div v-if="m.role !== 'user'" class="msg-meta">{{ t('本析智擎') }}</div>
            <div class="msg-content" v-html="m.html"></div>
          </div>
        </div>
        <div v-if="waiting" class="msg-row assistant">
          <div class="msg-avatar"><Icon name="robot" /></div>
          <div class="msg-bubble thinking">
            <span class="tdot"></span><span class="tdot"></span><span class="tdot"></span>
            <span class="ttext">{{ t('本析智擎思考中…') }}</span>
          </div>
        </div>
      </div>
      <div class="ac-inputbar">
        <div class="agent-inputbox">
          <textarea
            ref="chatInput"
            v-model="input"
            class="ai-textarea"
            rows="1"
            :placeholder="t('继续提问…（回车发送，Shift+Enter 换行）')"
            @keydown="onKeydown"
          ></textarea>
          <button class="ai-send" :disabled="thinking || !input.trim()" :title="t('发送')" @click="send"><Icon name="send" /></button>
        </div>
        <div class="ac-hint">{{ t('回答由大模型生成，仅供参考，请以实际设备数据为准') }}</div>
      </div>
    </div>
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
      messages: [], // { role: 'user' | 'assistant', content, html }
      suggests: [t('当前高炉工序的碳排放情况如何？'), t('焦比降低对碳排放有什么影响？'), t('如何降低吨钢综合能耗？'), t('帮我查询设备当前运行状态')],
    }
  },
  watch: {
    waiting(v) { if (v) this.scrollBottom() },
  },
  created() {
    this.store = useSimStore()
  },
  mounted() {
    // 对话内 echarts 图表实例表与 ResizeObserver（非响应式，避免 Vue 代理开销）
    this._chartInsts = new Map()
    this._chartObs = typeof ResizeObserver !== 'undefined' ? new ResizeObserver((entries) => {
      for (const en of entries) {
        const inst = this._chartInsts && this._chartInsts.get(en.target)
        if (inst && en.target.isConnected) inst.resize()
      }
    }) : null
    this.$nextTick(() => { if (this.$refs.idleInput) this.$refs.idleInput.focus() })
  },
  beforeDestroy() {
    this.disposeCharts()
  },
  methods: {
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
    onKeydown(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send() }
    },
    quickAsk(q) { this.input = q; this.send() },
    pushAssistant(content) {
      this.messages.push({ role: 'assistant', content, html: renderMarkdown(content) })
      this.scheduleCharts()
    },
    async send() {
      const text = this.input.trim()
      if (!text || this.thinking) return
      this.input = ''
      this.messages.push({ role: 'user', content: text, html: renderMarkdown(text) })
      this.waiting = true
      this.thinking = true
      this.scrollBottom()
      const history = this.messages.slice(0, -1).map((m) => [m.role, m.content]).slice(-20)
      let ok = false
      try {
        ok = await this.streamChat(text, history)
      } catch (e) {
        ok = false
      }
      if (!ok) {
        // 流式接口不可用时兜底到非流式 /api/chat
        try {
          const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, history, mode: 'chat' }),
          })
          const data = await resp.json()
          const reply = data && data.reply != null ? String(data.reply) : t('（无返回内容）')
          this.pushAssistant(reply)
        } catch (e2) {
          this.pushAssistant(t('（对话服务不可用：请确认后端已启动并配置了 LLM）'))
        }
      }
      this.waiting = false
      this.thinking = false
      this.scrollBottom()
    },
    // 流式回复：SSE 逐段解析增量文本，逐字渲染到最新一条助手消息
    async streamChat(text, history) {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, history, mode: 'chat' }),
      })
      if (!resp.ok || !resp.body) return false
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      let acc = ''
      let started = false
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let nl
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim()
          buf = buf.slice(nl + 1)
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (!payload || payload === '[DONE]') continue
          let evt
          try { evt = JSON.parse(payload) } catch (e) { continue }
          if (!evt || typeof evt.delta !== 'string' || !evt.delta) continue
          if (!started) {
            started = true
            this.waiting = false // 首个字符到达，收起「思考中…」
            this.pushAssistant('')
            this.scrollBottom()
          }
          acc += evt.delta
          const m = this.messages[this.messages.length - 1]
          m.content = acc
          m.html = renderMarkdown(acc)
          this.scheduleCharts()
          this.scrollBottom()
        }
      }
      if (!started) return false
      if (!acc) {
        const m = this.messages[this.messages.length - 1]
        m.content = t('（无返回内容）')
        m.html = renderMarkdown(t('（无返回内容）'))
      }
      return true
    },
    newChat() {
      if (this.thinking) return
      this.disposeCharts()
      this.messages = []
      this.input = ''
      this.$nextTick(() => { if (this.$refs.idleInput) this.$refs.idleInput.focus() })
    },
    scrollBottom() {
      nextTick(() => {
        const el = this.$refs.msgList
        if (el) el.scrollTop = el.scrollHeight
      })
    },
  },
}
</script>

<style scoped>
.agent-view {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  flex-direction: column;
  background: var(--bg);
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
.at-btn:hover { border-color: var(--accent-d); color: var(--accent-d); }

/* 「新对话」悬浮按钮（位于消息区右上角） */
.at-new {
  position: absolute;
  top: 10px;
  right: 14px;
  z-index: 2;
  background: var(--panel);
  box-shadow: 0 1px 6px rgba(0, 0, 0, .1);
}

/* 空闲态：居中大输入框 */
.agent-idle {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: 30px 20px;
}
.ai-inner { width: 100%; max-width: 680px; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.ai-logo {
  width: 64px; height: 64px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--accent-l);
  color: var(--accent-d);
}
.ai-logo svg { width: 34px; height: 34px; }
.ai-title { font-size: 22px; font-weight: 700; color: var(--text); }
.ai-desc { font-size: 13px; color: var(--muted); text-align: center; line-height: 1.6; }
.agent-inputbox {
  width: 100%;
  margin-top: 10px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 8px 8px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--panel);
  box-shadow: 0 2px 10px rgba(0, 0, 0, .06);
  transition: border-color .15s, box-shadow .15s;
}
/* 聚焦时保持中性边框，不出现主题色描边 */
.agent-inputbox:focus-within { border-color: var(--border); box-shadow: 0 1px 8px rgba(0, 0, 0, .08); }
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

/* 对话态 */
.agent-chat { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }
.ac-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg-row { display: flex; gap: 10px; max-width: 100%; }
.msg-row.user { flex-direction: row-reverse; }
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
  max-width: min(78%, 760px);
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
.ac-msgs { padding: 46px 14px 8px; }
.ac-inputbar { padding: 10px 14px 8px; }
.agent-idle { padding: 24px 16px; }
</style>
