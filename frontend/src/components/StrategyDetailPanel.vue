<template>
  <div class="strategy-detail">
    <template v-if="strategy">
      <!-- 内置预置策略：只读展示 -->
      <template v-if="strategy.source === 'preset'">
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>名称</span><b>{{ strategy.name }} <span class="tag">内置</span></b></div></div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        </CollapseSection>
        <CollapseSection title="数值调整" tone="amber" :show-more="false">
        <div class="note">该策略为系统内置，点击「策略仿真」进入仿真模式解析测试。</div>
        <div class="actions">
          <button class="x" :disabled="store.busy" @click="runSim">策略仿真</button>
        </div>
        </CollapseSection>
      </template>

      <!-- AI 优化模型（强化学习/遗传算法/粒子群）：随实时传感器数据采集，后台定时训练、模型逐渐变优 -->
      <template v-else-if="strategy.source === 'ai'">
        <CollapseSection title="模型名称" tone="blue" :show-more="false">
          <div class="card">
            <div class="kv2"><span>名称</span><b>{{ strategy.name }} <span class="tag">{{ modelTag }}</span></b></div>
            <div class="kv2"><span>状态</span><b><span class="badge" :class="badgeCls">{{ badgeTxt }}</span></b></div>
          </div>
          <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
          <div class="note" v-if="st.ready && !st.iteration">模型已就绪：可「开始自动训练」或「训练一轮」启动迭代优化。</div>
        </CollapseSection>

        <CollapseSection title="训练概览" tone="green" :show-more="false">
          <div v-if="st.ready" class="stat-row">
            <div class="stat"><b>{{ st.iteration || 0 }}</b><span>迭代轮数</span></div>
            <div class="stat"><b>{{ fmtSamples }}</b><span>传感器样本</span></div>
            <div class="stat"><b>{{ bestTxt }}</b><span>最优强度 kgCO₂/t</span></div>
            <div class="stat"><b :class="impCls">{{ impTxt }}</b><span>较初始提升</span></div>
          </div>
          <div v-else class="note">{{ notReadyTip }}</div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy" @click="toggleTrain">{{ st.running ? '暂停训练' : '开始自动训练' }}</button>
            <button class="x" :disabled="store.busy || st.running" @click="trainOnce">训练一轮</button>
          </div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy" @click="resetModel">重置</button>
            <button class="x main" :disabled="store.busy || !st.iteration" @click="applyModel">应用最优参数</button>
          </div>
          <div v-if="st.ready" class="tip-row">
            <span class="dot" :class="{ on: st.running }"></span>
            <span class="muted">{{ st.running ? '后台定时训练进行中：随实时传感器数据每轮迭代' : '已暂停：点击「开始自动训练」恢复后台定时迭代' }}</span>
          </div>
        </CollapseSection>

        <!-- 手动模式调优提醒：系统提醒引导手动应用优化参数 -->
        <div v-if="st.ready && !st.auto_control && st.reminder" class="reminder">
          <div class="rem-txt">训练取得新进展：最优强度降至 <b>{{ st.reminder.best_fitness != null ? st.reminder.best_fitness.toFixed(1) : '—' }}</b> kgCO₂/t（较上版提升 {{ st.reminder.improvement_pct != null ? st.reminder.improvement_pct.toFixed(1) : '0' }}%）。建议手动应用优化参数调优可调设备。</div>
          <div class="rem-actions">
            <button class="x main" :disabled="store.busy" @click="applyModel">应用最优参数</button>
            <button class="x" :disabled="store.busy" @click="ackReminder">知道了</button>
          </div>
        </div>

        <CollapseSection title="控制与训练设置" tone="amber" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">自动化控制</span>
              <button class="x sw" :class="{ on: !!st.auto_control }" :disabled="store.busy" @click="toggleAutoControl">{{ st.auto_control ? '已开启' : '未开启' }}</button>
            </div>
            <div class="note" v-if="st.auto_control">已开启自动化控制：训练获得更优模型时将自动把新版本参数下发到可调设备，无需人工干预。</div>
            <div class="note" v-else>未开启自动化控制：训练取得进展时通过系统提醒引导手动调优。</div>
          </div>
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">自训练频率</span>
              <select class="inp sel" v-model.number="intervalDraft" @change="saveSchedule" :disabled="store.busy">
                <option :value="5">每 5 秒</option>
                <option :value="10">每 10 秒</option>
                <option :value="30">每 30 秒</option>
                <option :value="60">每 60 秒</option>
                <option :value="120">每 2 分钟</option>
                <option :value="300">每 5 分钟</option>
              </select>
            </div>
            <div class="set-row">
              <span class="set-label">训练时段</span>
              <label class="chk"><input type="checkbox" v-model="windowOn" @change="saveSchedule" :disabled="store.busy" /> 仅限时段内自训练</label>
            </div>
            <div class="set-row time-row" v-if="windowOn">
              <input type="time" v-model="winStart" class="inp time" @change="saveSchedule" :disabled="store.busy" />
              <span class="muted">至</span>
              <input type="time" v-model="winEnd" class="inp time" @change="saveSchedule" :disabled="store.busy" />
            </div>
            <div class="note" v-if="st.ready && st.running && !st.in_window">当前处于训练时段之外，自动训练已挂起，进入时段后自动恢复。</div>
          </div>
        </CollapseSection>

        <CollapseSection title="适应度曲线" tone="amber" :show-more="false">
          <div v-if="curve.length > 1" class="chart">
            <svg :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none" class="chart-svg">
              <line v-for="g in gridY" :key="'g' + g" :x1="0" :x2="CW" :y1="g" :y2="g" class="grid" />
              <polyline :points="pts('best')" class="line-best" />
              <polyline :points="pts('avg')" class="line-avg" />
            </svg>
            <div class="legend">
              <span class="lg best">最优</span>
              <span class="lg avg">平均</span>
              <span class="lg muted">当前最优 {{ bestTxt }} kgCO₂/t</span>
            </div>
          </div>
          <div v-else class="note">尚无训练轨迹：开启自动训练或「训练一轮」后生成（最优强度随迭代递减）。</div>
        </CollapseSection>

        <CollapseSection title="算法超参数" tone="teal" :show-more="false">
          <div v-for="(hp, key) in st.hyper_schema || {}" :key="key" class="hp-row">
            <span class="hp-label">{{ hp.label }}</span>
            <input class="hp-slider" type="range" :min="hp.min" :max="hp.max" :step="hp.step" v-model.number="hpDraft[key]" />
            <span class="hp-val">{{ fmtHp(hpDraft[key]) }}</span>
          </div>
          <div class="actions"><button class="x" :disabled="store.busy || !st.ready" @click="saveHyper">保存超参数</button></div>
        </CollapseSection>

        <CollapseSection title="最优参数建议" tone="blue" :show-more="false">
          <div class="note" v-if="recommended">以下参数来自当前生效版本 <b>{{ recommended.version_id }}</b>（迭代 {{ recommended.iteration }} 轮 · 最优 {{ recommended.best_fitness }} kgCO₂/t）。</div>
          <div v-if="bestParams.length" class="bp-list">
            <div v-for="bp in bestParams" :key="bp.unit_id + ':' + bp.key" class="bp-row">
              <div class="bp-left">
                <b>{{ bp.label }}</b>
                <span class="muted">{{ bp.unit_label }} · {{ bp.unit }}</span>
              </div>
              <div class="bp-right">
                <span class="muted init">{{ bp.initial }}</span>
                <span class="arrow" :class="{ up: bp.delta > 0, down: bp.delta < 0 }">{{ bp.delta > 0 ? '▲' : bp.delta < 0 ? '▼' : '·' }}</span>
                <b>{{ bp.value }}</b>
              </div>
            </div>
          </div>
          <div v-else class="note">暂无最优参数建议：训练迭代后生成。</div>
          <div class="note" v-if="st.archived && st.archived.best_fitness != null">上一轮模型：迭代 {{ st.archived.iteration }} 轮 · 最优 {{ st.archived.best_fitness }} kgCO₂/t</div>
        </CollapseSection>

        <CollapseSection title="模型版本" tone="green" :show-more="false">
          <div class="note">仅当新模型的评估指标（吨钢碳强度）优于当前版本时才自动替换为新版本；历史版本全部保留，可随时切换。</div>
          <div v-if="versions.length" class="ver-list">
            <div v-for="v in versions" :key="v.id" class="ver-row" :class="{ active: v.active }">
              <div class="ver-head">
                <b>{{ v.id }}</b>
                <span class="ver-badge" v-if="v.active">当前版本</span>
                <span class="ver-badge cand" v-else>历史版本</span>
              </div>
              <div class="ver-meta muted">迭代 {{ v.iteration }} 轮 · {{ v.samples != null ? v.samples + ' 样本' : '' }} · {{ fmtTime(v.created_at) }}</div>
              <div class="ver-meta">
                <span class="muted">最优强度</span> <b>{{ v.best_fitness != null ? v.best_fitness.toFixed(1) : '—' }}</b> kgCO₂/t
                <span class="imp" :class="v.improvement_pct > 0.01 ? 'good' : 'bad'">{{ v.improvement_pct != null ? (v.improvement_pct >= 0 ? '↓' : '↑') + ' ' + Math.abs(v.improvement_pct).toFixed(1) + '%' : '' }}</span>
              </div>
              <div class="actions">
                <button class="x" :disabled="store.busy || v.active" @click="switchVer(v.id)">{{ v.active ? '使用中' : '切换到此版本' }}</button>
              </div>
            </div>
          </div>
          <div v-else class="note">暂无版本：训练取得提升后自动保存新版本，也可手动存档。</div>
          <div class="actions">
            <button class="x" :disabled="store.busy || !st.iteration" @click="saveVersion">保存当前最优为版本</button>
          </div>
        </CollapseSection>

        <CollapseSection title="训练日志" tone="purple" :show-more="false">
          <div v-if="st.logs && st.logs.length" class="logs">
            <div v-for="(lg, i) in st.logs" :key="i" class="lg-line">{{ lg }}</div>
          </div>
          <div v-else class="note">暂无日志。</div>
        </CollapseSection>

        <CollapseSection title="工作机制" tone="gray" :show-more="false">
          <div class="note">
            实时传感器数据持续采集 → 后台按自训练频率定时训练（每轮迭代）→ 模型参数逐步收敛。
            只有新模型的评估指标（吨钢碳强度）优于当前版本时才替换为新版本，历史版本均保留可切换。
            开启「自动化控制」时，模型变优后自动把参数下发到可调设备；未开启时通过系统提醒手动调优。
          </div>
        </CollapseSection>
      </template>

      <!-- 工艺策略（某工艺对应的绿色策略）：只读展示 + 启用/停用 + 查看工艺 -->
      <template v-else-if="strategy.source === 'green'">
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>名称</span><b>{{ strategy.name }} <span class="tag">工艺策略</span></b></div></div>
        <div class="card">
          <div class="kv2"><span>所属工艺</span><b>{{ strategy.processLabel }}</b></div>
        </div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        <div class="card" v-if="strategy.saving || strategy.carbon">
          <div class="kv2" v-if="strategy.saving"><span>节能效果</span><b>{{ strategy.saving }}</b></div>
          <div class="kv2" v-if="strategy.carbon"><span>减碳效果</span><b>{{ strategy.carbon }} kgCO₂/t</b></div>
        </div>
        <div class="card" v-if="strategy.tags && strategy.tags.length">
          <div class="tag-row">
            <span v-for="t in strategy.tags" :key="t" class="tag">{{ t }}</span>
          </div>
        </div>
        </CollapseSection>
        <CollapseSection title="启用状态" tone="green" :show-more="false">
        <div class="card toggle-card">
          <span class="muted">{{ strategy.enabled ? '该策略已在对应工艺中启用' : '该策略未启用' }}</span>
          <button class="x" :class="{ on: strategy.enabled }" @click="toggleGreen">
            {{ strategy.enabled ? '已启用' : '启用策略' }}
          </button>
        </div>
        <button class="btn-mini" @click="goProcess">查看工艺属性</button>
        </CollapseSection>
      </template>

      <!-- 自定义策略：可编辑 -->
      <template v-else>
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><input v-model="nameDraft" class="inp" @change="markDirty" /></div>
        </CollapseSection>
        <CollapseSection title="来源" tone="teal" :show-more="false">
        <div class="card">
          <span class="tag">{{ strategy.applied ? '已应用' : '自定义' }}</span>
          <span class="muted src-tip">仿真模式下保存</span>
        </div>
        </CollapseSection>
        <CollapseSection v-if="strategy.description" title="描述" tone="teal" :show-more="false">
        <div class="card">
          <textarea v-model="descDraft" class="inp" rows="2" @change="markDirty"></textarea>
        </div>
        </CollapseSection>

        <!-- 数值调整（可编辑） -->
        <CollapseSection title="数值调整" tone="amber" :show-more="false">
        <div v-if="opsDraft.length" class="ops">
          <div v-for="(op, i) in opsDraft" :key="i" class="op-row">
            <div class="op-head">
              <span class="op-note">{{ opNote(op) }}</span>
              <span class="op-kind">{{ op.action === 'set_param' ? '参数' : op.action === 'apply_tech' ? '技术' : '操作' }}</span>
            </div>
            <div v-if="op.action === 'set_param'" class="op-edit">
              <span class="op-label">{{ op.target }} {{ opParamLabel(op) }}</span>
              <input v-model.number="op.value" type="number" class="inp num" @change="markDirty" />
              <span class="op-unit">{{ opUnit(op) }}</span>
            </div>
            <div v-else class="op-static muted">{{ opNote(op) }}</div>
          </div>
        </div>
        <div v-else class="note">该策略暂无数值调整项。</div>

        <div class="actions">
          <button class="x" :disabled="store.busy" @click="save">保存修改</button>
          <button class="x" :disabled="store.busy" @click="runSim">策略仿真</button>
        </div>
        </CollapseSection>
      </template>
    </template>
    <div v-else class="empty">未选择策略，请先在左侧「策略」中选择。</div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useSimStore, EDITABLE_PARAMS, AI_MODEL_MAP } from '../stores/sim'
import CollapseSection from './CollapseSection.vue'

const store = useSimStore()

const strategy = computed(() => store.selectedStrategy)
const nameDraft = ref('')
const descDraft = ref('')
const opsDraft = ref([])
let hpInited = false   // AI 算法超参数草稿是否已初始化（避免轮询覆盖用户编辑）
let settingsInited = false  // 控制与训练设置草稿是否已初始化
const intervalDraft = ref(30)
const windowOn = ref(false)
const winStart = ref('08:00')
const winEnd = ref('18:00')

watch(strategy, (s) => {
  nameDraft.value = s ? s.name || '' : ''
  descDraft.value = s ? s.description || '' : ''
  opsDraft.value = s && s.ops ? JSON.parse(JSON.stringify(s.ops)) : []
  hpInited = false   // 切换条目后重新初始化 AI 算法超参数草稿
  settingsInited = false
}, { immediate: true })

// ==================== AI 优化模型（GA / PSO / RL 在线训练面板） ====================
// 后端状态（store.optimizers[id]）由全局轮询每数秒刷新，展示迭代/曲线/最优参数随实时数据逐渐变优。
const st = computed(() => store.optimizers[strategy.value.id] || {})
const modelTag = computed(() => (AI_MODEL_MAP[strategy.value.id] || {}).tag || 'AI')
const badgeCls = computed(() => (st.value.running ? 'run' : st.value.iteration > 0 ? 'pause' : 'idle'))
const badgeTxt = computed(() => (st.value.running ? '训练中' : st.value.iteration > 0 ? '已暂停' : '待训练'))
const notReadyTip = computed(() => '训练上下文未同步：进入面板后将随流程模型自动初始化')
const fmtSamples = computed(() => {
  const s = st.value.samples || 0
  return s >= 10000 ? (s / 10000).toFixed(1) + ' 万' : String(s)
})
const bestTxt = computed(() => (st.value.best_fitness != null ? st.value.best_fitness.toFixed(1) : '—'))
const impTxt = computed(() => {
  const p = st.value.improvement_pct
  if (p == null) return '—'
  return p >= 0 ? '↓ ' + Math.abs(p).toFixed(1) + '%' : '↑ ' + Math.abs(p).toFixed(1) + '%'
})
const impCls = computed(() => {
  const p = st.value.improvement_pct
  if (p == null) return ''
  return p > 0.01 ? 'good' : p < -0.01 ? 'bad' : ''
})
// 当前生效版本的参数建议（推荐下发）；无版本时回退实时最优参数
const recommended = computed(() => st.value.recommended || null)
const bestParams = computed(() => {
  if (recommended.value && recommended.value.params && recommended.value.params.length) return recommended.value.params
  return st.value.best_params || []
})
// 模型版本列表：新→旧
const versions = computed(() => {
  const vs = st.value.versions || []
  return vs.slice().reverse()
})

// 适应度曲线（SVG 折线，最优/平均）
const CW = 320
const CH = 100
const curve = computed(() => st.value.history || [])
const gridY = computed(() => [CH / 4, CH / 2, (CH * 3) / 4])
function pts(key) {
  const c = curve.value
  if (c.length < 2) return ''
  let min = Infinity
  let max = -Infinity
  for (const p of c) {
    min = Math.min(min, p.best, p.avg)
    max = Math.max(max, p.best, p.avg)
  }
  const span = max - min || 1
  const pad = 8
  return c
    .map((p, i) => {
      const x = (i / (c.length - 1)) * CW
      const y = CH - pad - ((p[key] - min) / span) * (CH - 2 * pad)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

// 算法超参数草稿（轮询刷新时不覆盖用户编辑：仅在首次/切换条目时初始化）
const hpDraft = ref({})
// 控制与训练设置草稿：同样仅在首次/切换条目时从后端状态初始化
watch(st, (s) => {
  if (!hpInited && s && s.hyperparams) {
    hpDraft.value = JSON.parse(JSON.stringify(s.hyperparams))
    hpInited = true
  }
  if (!settingsInited && s && s.schedule) {
    intervalDraft.value = s.schedule.interval || 30
    const w = s.schedule.window
    windowOn.value = !!w
    winStart.value = (w && w.start) || '08:00'
    winEnd.value = (w && w.end) || '18:00'
    settingsInited = true
  }
}, { deep: true })
function fmtHp(v) { return v == null ? '—' : Number(v) }

// 训练控制
function toggleTrain() {
  if (st.value.running) store.stopOptimizer(strategy.value.id)
  else store.startOptimizer(strategy.value.id)
}
function trainOnce() { store.trainOptimizer(strategy.value.id, 1) }
function resetModel() { store.resetOptimizer(strategy.value.id) }
function saveHyper() { store.setOptimizerHyper(strategy.value.id, { ...hpDraft.value }) }
function applyModel() { store.applyOptimizer(strategy.value.id) }
// ---- 控制与训练设置 ----
function toggleAutoControl() {
  store.setOptimizerSettings(strategy.value.id, { auto_control: !st.value.auto_control })
}
function saveSchedule() {
  store.setOptimizerSettings(strategy.value.id, {
    schedule: {
      interval: Math.max(5, Math.round(intervalDraft.value || 30)),
      window: windowOn.value ? { start: winStart.value || '08:00', end: winEnd.value || '18:00' } : null,
    },
  })
}
// ---- 模型版本 ----
function saveVersion() { store.archiveOptimizer(strategy.value.id) }
function switchVer(vid) { store.switchOptimizerVersion(strategy.value.id, vid) }
function ackReminder() { store.ackOptimizer(strategy.value.id) }
function fmtTime(iso) {
  if (!iso) return '—'
  const t = iso.includes('T') ? iso : iso.replace(' ', 'T')
  const d = new Date(t)
  if (isNaN(d.getTime())) return iso
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 进入面板：同步最新流程为训练上下文并立即拉取训练状态（全局轮询已在 store.init 启动）
onMounted(() => {
  store.syncOptimizerContext().then(() => store.refreshOptimizers())
})

function opParamLabel(op) {
  const u = op.target
  const p = op.param
  if (!u || !p) return p || ''
  // 从参数元数据中查找该工序参数的显示名（label），找不到则回退原始 key
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.label || p
  }
  return p
}
function opUnit(op) {
  const p = op.param
  if (!p) return ''
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.unit || ''
  }
  return ''
}
function opNote(op) {
  return op.note || (op.action === 'set_param' ? `${op.target || ''} ${op.param || ''} = ${op.value}` : op.action || '')
}
function markDirty() {}

async function save() {
  if (!strategy.value) return
  await store.updateStrategy(strategy.value.id, {
    name: nameDraft.value.trim() || '未命名策略',
    description: descDraft.value,
    ops: opsDraft.value,
  })
}
function runSim() {
  if (!strategy.value) return
  store.runStrategySimulation(strategy.value.id)
}
// 工艺策略：跳转到对应工艺的属性面板
function goProcess() {
  if (!strategy.value) return
  store.selectAssetType(strategy.value.processType)
}
// 工艺策略：切换启用/停用
function toggleGreen() {
  if (!strategy.value) return
  store.toggleGreenStrategy(strategy.value.processType, strategy.value.sid)
  const on = store.greenStrategiesFor(strategy.value.processType).includes(strategy.value.sid)
  store.toast = on ? `已启用策略「${strategy.value.name}」` : `已停用策略「${strategy.value.name}」`
}
</script>

<style scoped>
.strategy-detail { padding: 2px 0; }
.inp { width: 100%; box-sizing: border-box; background: var(--panel-2); border: 1px solid var(--line); color: var(--text); border-radius: 3px; padding: 4px 8px; font-size: 11px; }
.inp.num { width: 90px; text-align: right; flex: 0 0 auto; padding: 4px 8px; }
textarea.inp { resize: vertical; font-family: inherit; line-height: 1.5; }
.tag { display: inline-block; font-size: 10px; color: var(--accent2); border: 1px solid var(--line); border-radius: 3px; padding: 1px 6px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.toggle-card { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.src-tip { margin-left: 8px; }
.toggle-card .x.on { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }
.btn-mini { flex: 0 0 auto; font-size: 11px; padding: 3px 9px; border-radius: 3px; background: var(--panel-2); color: var(--accent2); border: 1px solid var(--line); cursor: pointer; margin-top: 8px; }
.btn-mini:hover { border-color: var(--accent2); }
.ops { display: flex; flex-direction: column; gap: 8px; }
.op-row { border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; background: var(--panel-2); }
.op-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.op-note { font-size: 11px; color: var(--text); }
.op-kind { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 6px; }
.op-edit { display: flex; align-items: center; gap: 8px; }
.op-label { flex: 1; font-size: 11px; color: var(--muted); }
.op-unit { font-size: 11px; color: var(--muted); }
.op-static { font-size: 11px; }
.actions { display: flex; gap: 8px; margin-top: 14px; }
.actions .x { flex: 1; padding: 9px 0; font-size: 12px; }
/* ---- AI 优化模型训练面板 ---- */
.badge { display: inline-block; font-size: 10px; padding: 1px 9px; border-radius: 9px; border: 1px solid var(--line); color: var(--muted); }
.badge.run { color: #34d399; border-color: #34d399; background: rgba(52, 211, 153, .12); }
.badge.pause { color: var(--accent2); border-color: var(--accent2); background: rgba(56, 132, 255, .12); }
.actions .x.main { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }
.actions .x.main:disabled { opacity: .5; cursor: not-allowed; }
.stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat { background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.stat b { font-size: 15px; color: var(--text); font-variant-numeric: tabular-nums; }
.stat b.good { color: #34d399; }
.stat b.bad { color: #f87171; }
.stat span { font-size: 10px; color: var(--muted); }
.tip-row { display: flex; align-items: center; gap: 6px; margin-top: 12px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex: 0 0 auto; }
.dot.on { background: #34d399; box-shadow: 0 0 6px #34d399; animation: optpulse 1.6s infinite; }
@keyframes optpulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
.chart { width: 100%; }
.chart-svg { width: 100%; height: 96px; display: block; }
.chart-svg .grid { stroke: var(--line); stroke-width: 1; opacity: .5; }
.chart-svg .line-best { fill: none; stroke: #34d399; stroke-width: 2; stroke-linejoin: round; }
.chart-svg .line-avg { fill: none; stroke: #fbbf24; stroke-width: 1.2; opacity: .65; stroke-linejoin: round; }
.legend { display: flex; align-items: center; gap: 12px; margin-top: 6px; font-size: 10px; color: var(--muted); }
.legend .lg { display: inline-flex; align-items: center; gap: 4px; }
.legend .lg::before { content: ''; width: 14px; height: 3px; border-radius: 2px; }
.legend .lg.best::before { background: #34d399; }
.legend .lg.avg::before { background: #fbbf24; opacity: .7; }
.legend .lg.muted::before { display: none; }
.hp-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; }
.hp-label { flex: 0 0 92px; font-size: 11px; color: var(--muted); }
.hp-slider { flex: 1; accent-color: var(--accent2); min-width: 0; }
.hp-val { flex: 0 0 46px; text-align: right; font-size: 11px; color: var(--text); font-variant-numeric: tabular-nums; }
.bp-list { display: flex; flex-direction: column; gap: 6px; }
.bp-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; }
.bp-left { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.bp-left b { font-size: 11px; }
.bp-left .muted { font-size: 10px; }
.bp-right { display: flex; align-items: center; gap: 6px; font-size: 11px; flex: 0 0 auto; }
.bp-right .init { text-decoration: line-through; opacity: .7; }
.bp-right .arrow { color: var(--muted); font-size: 9px; }
.bp-right .arrow.up { color: #fbbf24; }
.bp-right .arrow.down { color: #34d399; }
.bp-right b { font-size: 12px; color: var(--accent2); font-variant-numeric: tabular-nums; }
.logs { display: flex; flex-direction: column; gap: 3px; }
.lg-line { font-size: 10px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.6; word-break: break-all; }
/* ---- 手动调优提醒 ---- */
.reminder { border: 1px solid #fbbf24; border-radius: 3px; background: rgba(251, 191, 36, .08); padding: 8px 10px; margin-bottom: 10px; }
.rem-txt { font-size: 11px; color: var(--text); line-height: 1.6; }
.rem-txt b { color: #fbbf24; }
.rem-actions { display: flex; gap: 8px; margin-top: 8px; }
.rem-actions .x { flex: 1; padding: 7px 0; font-size: 11px; }
.rem-actions .x.main { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }
/* ---- 控制与训练设置 ---- */
.set-block { padding: 8px 0 2px; }
.set-block + .set-block { border-top: 1px dashed var(--line); margin-top: 8px; }
.set-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 0; }
.set-label { font-size: 11px; color: var(--text); flex: 0 0 auto; }
.x.sw { flex: 0 0 auto; font-size: 11px; padding: 3px 10px; border-radius: 3px; background: var(--panel-2); color: var(--muted); border: 1px solid var(--line); cursor: pointer; }
.x.sw.on { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }
.inp.sel { width: auto; min-width: 108px; flex: 0 0 auto; padding: 3px 6px; font-size: 11px; }
.inp.time { width: auto; min-width: 86px; flex: 0 0 auto; padding: 3px 6px; font-size: 11px; }
.chk { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); cursor: pointer; }
.chk input { accent-color: var(--accent2); }
.time-row { justify-content: flex-end; gap: 6px; }
/* ---- 模型版本 ---- */
.ver-list { display: flex; flex-direction: column; gap: 8px; }
.ver-row { border: 1px solid var(--line); border-radius: 3px; padding: 8px; background: var(--panel-2); }
.ver-row.active { border-color: #34d399; background: rgba(52, 211, 153, .06); }
.ver-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.ver-head b { font-size: 12px; color: var(--accent2); }
.ver-badge { font-size: 10px; padding: 0 6px; border-radius: 8px; color: #34d399; border: 1px solid #34d399; background: rgba(52, 211, 153, .1); }
.ver-badge.cand { color: var(--muted); border-color: var(--line); background: transparent; }
.ver-meta { font-size: 10px; color: var(--muted); line-height: 1.7; }
.ver-meta b { color: var(--text); font-size: 11px; font-variant-numeric: tabular-nums; }
.ver-meta .imp { margin-left: 6px; font-size: 10px; }
.ver-meta .imp.good { color: #34d399; }
.ver-meta .imp.bad { color: #f87171; }
.ver-row .actions { margin-top: 8px; }
.ver-row .actions .x { padding: 6px 0; font-size: 11px; }
</style>
