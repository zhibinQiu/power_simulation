<template>
  <aside class="inspector">
    <!-- 宽度拖拽手柄（左侧边缘） -->
    <div class="inspector-rsz" :class="{ dragging: rszDragging }" @mousedown.prevent="onRszStart" :title="t('拖拽调整宽度')"></div>
    <!-- 本析智擎模式：按需隐藏顶部标题栏与关闭按钮（窗口内自含工具条） -->
    <div v-if="mode !== 'agent'" class="sidebar-head">
      <span class="ttl">{{ headTitle }}</span>
      <span class="spacer"></span>
      <button v-if="mode !== 'overview' || store.selectedGroupId || store.selectedFlowId" class="x-btn" :title="t('返回总览')" @click="store.closeInspector()">✕</button>
    </div>    <div class="inspector-body" :class="{ scrolling }" @scroll="onScroll">
      <!-- 本析智擎：智能体对话界面（工具栏「本析智擎」切换，替换右侧属性弹窗，中间 3D 场景保持） -->
      <AgentChatView v-if="mode === 'agent'" />

      <!-- 报告面板（工具条「数据 → 报告 → 导出报告」，含历史报告管理） -->
      <ReportPanel v-else-if="mode === 'report'" />

      <!-- 场景/列表/左侧工艺目录点击实例：统一只用一个工序实例属性面板（能耗/碳排放/碳平衡/实时监测/可调节/核算台账/关联设备） -->
      <UnitCarbonDetail v-else-if="mode === 'unit'" />

      <!-- 原料属性 -->
      <MaterialInspector v-else-if="mode === 'material'" />

      <!-- 策略详情（点击左侧「策略 → 自定义」） -->
      <StrategyDetailPanel v-else-if="mode === 'strategyDetail'" />

      <!-- 编辑态：流程编排属性面板；非编辑态下点击工艺节点也展示其编排属性 -->
      <FlowInspector v-else-if="store.editMode || store.selectedFlowId" />

      <!-- 数字孪生（非编辑态）点击小组：数值展示型小组属性面板（成员工艺列表 + 实测值） -->
      <GroupDetail v-else-if="store.selectedGroupId" />

      <!-- 总览（模块可上下拖拽重排，顺序/折叠状态持久化） -->
      <template v-else-if="mode === 'overview'">
        <template v-for="sid in layout.state.order" :key="sid">
          <CollapseSection
            v-if="sid === 'plant'"
            :title="t('全厂总览')"
            tone="blue"
            drag-id="plant"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <!-- 全厂总览：实时 / 日度 / 月度 / 年度 四档时段核算。
                 realtime=小时速率；日/月/年=当日/当月/当年 0 点起截止当前的累计量（墙钟口径，跨周期自动归零）。
                 每档含 综合能耗/电耗/总排放/钢产量/单位能耗/吨钢强度/成本/碳利用率；
                 成本 = 外购用量 × 单价（点击成本卡展开构成明细）；同比/环比待接入历史台账后启用。 -->
            <div class="plant">
              <div class="plant-tabs" role="tablist">
                <button v-for="p in plantPeriods" :key="p.id" type="button" role="tab"
                        class="plant-tab" :class="{ on: plantPeriod === p.id }"
                        :aria-selected="plantPeriod === p.id"
                        :title="t(p.hint)" @click="plantPeriod = p.id">{{ t(p.label) }}</button>
              </div>
              <div class="plant-note">{{ periodDesc }}</div>
              <div class="chips">
                <div class="chip2"><span>{{ t('综合能耗') }}</span><b>{{ fmt(period.energy) }}</b><i>{{ period.u.energy }}</i></div>
                <div class="chip2"><span>{{ t('电耗') }}</span><b>{{ fmt(period.elec) }}</b><i>{{ period.u.elec }}</i></div>
                <div class="chip2"><span>{{ t('总排放') }}</span><b :style="{color:co2Color}">{{ fmt(period.co2) }}</b><i>{{ period.u.co2 }}</i></div>
                <div class="chip2"><span>{{ t('钢产量') }}</span><b>{{ fmt(period.steel) }}</b><i>{{ period.u.steel }}</i></div>
                <div class="chip2"><span>{{ t('单位能耗') }}</span><b>{{ fmt(plantEnergy.intensity) }}</b><i>kgce/t</i></div>
                <div class="chip2"><span>{{ t('吨钢强度') }}</span><b :style="{color:co2Color}">{{ fmt(totals.intensity) }}</b><i>kgCO₂/t</i></div>
                <div class="chip2 tog" :class="{ open: costOpen }" role="button" :title="t('点击展开成本构成（外购用量 × 单价）')" @click="costOpen = !costOpen">
                  <span>{{ t('成本') }} <em class="caret">{{ costOpen ? '▾' : '▸' }}</em></span>
                  <b>{{ fmt(period.cost) }}</b><i>{{ period.u.cost }}</i>
                </div>
                <div class="chip2"><span>{{ t('碳利用率') }}</span><b>{{ (totals.carbon_utilization*100).toFixed(1) }}</b><i>%</i></div>
              </div>
              <div v-if="costOpen" class="cost-detail">
                <div class="cd-head">{{ t('成本构成 = 外购用量 × 单价（下表为小时速率 · 总卡金额随所选周期累计）') }}</div>
                <div v-for="it in costDetail" :key="it.id" class="cd-row">
                  <span class="cd-name" :style="{ background: it.color || 'var(--panel-3)' }">{{ it.name }}</span>
                  <span class="cd-qty">{{ fmt(it.qty) }} {{ it.unit }}/h × {{ fmt(it.price) }} 元/{{ it.unit }}</span>
                  <span class="cd-amt"><b>{{ fmt(it.amt / 1e4) }}</b><i>万元/h</i></span>
                </div>
                <div v-if="!costDetail.length" class="cd-row cd-empty">{{ t('当前流程无外购原燃料用量（自产/闭环），成本为 0。') }}</div>
                <div class="cd-note">{{ t('单价在「物料属性」中按采购合同调整后实时联动；内部中间品与副产品不重复计入。') }}</div>
              </div>
              <div class="scope">
                <div class="scope-bar">
                  <i class="scope-direct" :style="{ width: directPct + '%' }"></i>
                  <i class="scope-indirect" :style="{ width: indirectPct + '%' }"></i>
                </div>
                <div class="scope-legend">
                  <span><i class="dot d"></i>{{ t('直接') }} {{ fmt(period.direct) }} {{ period.u.co2 }}<em> ({{ directPct }}%)</em></span>
                  <span><i class="dot i"></i>{{ t('间接') }} {{ fmt(period.indirect) }} {{ period.u.co2 }}<em> ({{ indirectPct }}%)</em></span>
                </div>
              </div>
              <div v-if="plantPeriod === 'day' || plantPeriod === 'month'" class="cmp-row">
                <div class="chip2">
                  <span>{{ t('综合能耗同比') }}</span>
                  <b :class="dirCls(cmp.yoy)">{{ signedPct(cmp.yoy) }}</b>
                  <i>{{ t('较上年同期') }}</i>
                </div>
                <div class="chip2">
                  <span>{{ t('综合能耗环比') }}</span>
                  <b :class="dirCls(cmp.mom)">{{ signedPct(cmp.mom) }}</b>
                  <i>{{ t('较上一核算期') }}</i>
                </div>
              </div>
              <div v-if="plantPeriod === 'day' || plantPeriod === 'month'" class="plant-foot">
                {{ t('同比/环比暂无历史台账数据，显示「—」；接入日/月报历史后自动启用，当前不做折算填充。') }}
              </div>
            </div>
          </CollapseSection>

          <CollapseSection
            v-else-if="sid === 'strategy' && store.strategy"
            :title="t('策略节能减碳效果')"
            tone="green"
            drag-id="strategy"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <div class="strat-cmp">
              <div class="sc-item"><span>{{ t('节能量') }}</span><b class="good">{{ fmt(stratCmp.energyRed) }}</b><i>GJ/h</i></div>
              <div class="sc-item"><span>{{ t('节能率') }}</span><b class="good">{{ stratCmp.energyPct }}%</b><i>{{ t('较基线') }}</i></div>
              <div class="sc-item"><span>{{ t('减排量') }}</span><b class="good">{{ fmt(stratCmp.co2Red) }}</b><i>tCO₂/h</i></div>
              <div class="sc-item"><span>{{ t('减排率') }}</span><b class="good">{{ stratCmp.co2Pct }}%</b><i>{{ t('较基线') }}</i></div>
            </div>
          </CollapseSection>

          <CollapseSection
            v-else-if="sid === 'top'"
            :title="t('排放最高工序')"
            tone="red"
            drag-id="top"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <div v-for="u in topEmitters" :key="u.id" class="lrow click te-row" :class="{active: store.selectedUnitId===u.id}" @click="store.selectUnit(u.id)">
              <div class="l-stack">
                <span class="l-tt">{{ u.name }}</span>
                <span class="l-sub">{{ typeLabel(u.type) }}</span>
                <span class="te-bar"><i :style="{ width: Math.min(100, u.share*100).toFixed(1)+'%', background: shareColor(u.share) }"></i></span>
              </div>
              <span class="l-trail" :style="{color:co2Color}">{{ fmt(u.co2_total) }} <i class="u">tCO₂/h</i></span>
              <span class="te-pct">{{ (u.share*100).toFixed(1) }}%</span>
            </div>
          </CollapseSection>
        </template>
      </template>

      <!-- 设备属性 -->
      <DeviceDetail v-else-if="mode === 'device'" />

      <!-- 物料库（点击左侧「物料」） -->
      <template v-else-if="mode === 'materials'">
        <div class="park-sum">{{ t('共') }} {{ materialList.length }} {{ t('种物料（原料/中间产物/能源/副产品），点击查看隐含碳因子与配置。') }}</div>
        <div class="lview">
          <div v-for="m in materialList" :key="m.id" class="lrow click" :class="{active: store.selectedMaterialId===m.id}" @click="store.selectMaterial(m.id)">
            <div class="l-stack">
              <span class="l-tt">{{ m.name }}</span>
              <span class="l-sub">{{ m.cat }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { energyOf } from '../utils/energy'
import { useSimStore, UNIT_TYPES } from '../stores/sim'
import { MATERIALS, MATERIAL_MAP } from '../data/flowLibrary'
import { t } from '../i18n'
const AgentChatView = defineAsyncComponent(() => import('../views/AgentChatView.vue'))
import UnitCarbonDetail from './UnitCarbonDetail.vue'
import DeviceDetail from './DeviceDetail.vue'
import FlowInspector from './FlowInspector.vue'
import GroupDetail from './GroupDetail.vue'
import MaterialInspector from './MaterialInspector.vue'
import CollapseSection from './CollapseSection.vue'
import StrategyDetailPanel from './StrategyDetailPanel.vue'
import ReportPanel from './ReportPanel.vue'
import { useDragLayout } from '../composables/useDragSort'

/* 总览面板模块布局：顺序 + 折叠状态持久化到 localStorage（打开面板恢复上次状态）
 * v2：默认全部折叠（ISA-101 少即是多），不再继承 v1 持久化的展开状态 */
const ovLayoutKey = ref('insp-layout:overview:v2')
const layout = useDragLayout(
  ovLayoutKey,
  ['plant', 'strategy', 'top'],
  { plant: false, strategy: false, top: false },
)

/* 宽度拖拽手柄：将事件转发给 App.vue 处理（与左侧栏一致） */
const emit = defineEmits(['rsz'])
const rszDragging = ref(false)
function onRszStart(e) {
  rszDragging.value = true
  const cleanup = () => { rszDragging.value = false }
  window.addEventListener('mouseup', cleanup, { once: true })
  emit('rsz', e)
}

const store = useSimStore()
const materialList = MATERIALS

// 滚动条显隐：滚动时显示，停止滚动 2s 后自动隐藏
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}

const mode = computed(() => store.inspectorMode)
const headTitle = computed(() => {
  if (mode.value === 'agent') return t('本析智擎')
  if (mode.value === 'report') return t('报告面板')
  if (mode.value === 'park') return t('园区构成')
  if (mode.value === 'materials') return t('物料库')
  if (mode.value === 'material') return t('物料属性')
  if (mode.value === 'strategyDetail') return t('策略属性')
  if (store.editMode) return t('编排属性')
  if (store.selectedGroupId) return t('小组属性')
  if (store.selectedFlowId) return t('工艺属性')
  if (mode.value === 'device') {
    const d = store.deviceDetail
    return (d && d.device && d.device.adjustable) ? t('可调设备') : t('计量设备')
  }
  return ({ overview: t('检视器 · 总览'), unit: t('工序属性') }[mode.value] || t('检视器'))
})

// ---------- 全厂总览：实时 / 日度 / 月度 / 年度 四档时段核算 ----------
// 统计口径（v2）：日/月/年 = 当日 / 当月 / 当年「0 点起截止当前」的真实累计量（墙钟自然周期，
// 与生产日报同口径）——速率 × 周期已过小时数，跨 0 点 / 月初 / 年初自动归零重计；
// realtime = 当前小时速率。成本 = 外购用量(后端 totals.purchases) × 物料单价(原料属性可调)。
const KGCE_PER_GJ = 34.12                  // 1 GJ = 34.12 kgce（与后端 factors 一致，强度兜底计算用）

const plantPeriods = [
  { id: 'realtime', label: '实时', hint: '实时：按当前小时速率展示（GJ/h · MWh/h · tCO₂/h）' },
  { id: 'day', label: '日度', hint: '日度：今日 0 点起累计（截至当前）' },
  { id: 'month', label: '月度', hint: '月度：本月 1 日 0 点起累计（截至当前）' },
  { id: 'year', label: '年度', hint: '年度：本年 1 月 1 日 0 点起累计（截至当前）' },
]
// 各档展示单位：h 级单位(实时) / 原始单位(日内累计) / 万级(月) / 万~亿级(年)
const P_UNIT = {
  realtime: { energy: 'GJ/h', elec: 'MWh/h', co2: 'tCO₂/h', steel: 't/h', cost: '万元/h' },
  day:      { energy: 'GJ', elec: 'MWh', co2: 'tCO₂', steel: 't', cost: '万元' },
  month:    { energy: '万GJ', elec: '万kWh', co2: '万tCO₂', steel: '万t', cost: '万元' },
  year:     { energy: '万GJ', elec: '亿kWh', co2: '万tCO₂', steel: '万t', cost: '亿元' },
}

const plantPeriod = ref('realtime')

// 全厂实时核算：优先取 ws 遥测帧内与本次 tick 同步的 totals（后端 /api/ws/feed 已全量下发），
// 实时态不再混用静态基线（旧 bug：实时直接/间接/能耗停留在初始仿真值，与实时总量对不上）。
const totals = computed(() => {
  const fb = {
    co2_total: 0, co2_direct: 0, co2_indirect: 0, intensity: 0, steel_output: 0,
    carbon_utilization: 0, energy_total: 0, energy_intensity: 0, elec: 0, fuel_energy: 0,
    purchases: {},
  }
  const base = (store.resultForView && store.resultForView.totals) ? store.resultForView.totals : fb
  const live = store.live
  if (!live) return base
  const lt = live.totals || {}
  const pick = (k, alt) => (lt[k] != null ? lt[k] : alt)
  return {
    co2_total: pick('co2_total', live.total_co2 != null ? live.total_co2 : base.co2_total),
    co2_direct: pick('co2_direct', base.co2_direct),
    co2_indirect: pick('co2_indirect', base.co2_indirect),
    intensity: pick('intensity', live.intensity != null ? live.intensity : base.intensity),
    steel_output: pick('steel_output', live.steel_output != null ? live.steel_output : base.steel_output),
    carbon_utilization: pick('carbon_utilization', base.carbon_utilization),
    energy_total: pick('energy_total', base.energy_total),
    energy_intensity: pick('energy_intensity', base.energy_intensity),
    elec: pick('elec', base.elec),
    fuel_energy: pick('fuel_energy', base.fuel_energy),
    purchases: pick('purchases', base.purchases || {}),
  }
})
// 全厂综合能耗（节能减碳主题：先能后碳）。优先用后端 totals（实时帧已含），缺失时由工序能耗汇总反推。
const plantEnergy = computed(() => {
  const t = totals.value
  if (t && t.energy_total != null && t.energy_total > 0) {
    let intensity = t.energy_intensity
    if ((intensity == null || intensity <= 0) && (t.steel_output || 0) > 0) {
      intensity = (t.energy_total * KGCE_PER_GJ) / t.steel_output
    }
    return { total: t.energy_total, intensity: intensity || 0 }
  }
  const r = store.resultForView
  const units = (r && r.units) || []
  let total = 0
  for (const u of units) total += energyOf(u).total
  const steel = (t && t.steel_output) || 0
  return { total, intensity: steel > 0 ? (total * KGCE_PER_GJ) / steel : 0 }
})
// 全厂电耗：优先用后端 totals，缺失时由工序台账/碳素流反推汇总
const plantElec = computed(() => {
  const t = totals.value
  if (t && t.elec != null && t.elec > 0) return t.elec
  const r = store.resultForView
  const units = (r && r.units) || []
  let sum = 0
  for (const u of units) sum += energyOf(u).elec
  return sum
})

// ---------- 成本：外购用量(后端 totals.purchases) × 物料单价(原料属性可调，默认行业参考价) ----------
const priceOf = (id) => {
  const ov = store.materialOverrides && store.materialOverrides[id]
  if (ov && ov.price != null) return Number(ov.price)
  const m = MATERIAL_MAP[id]
  return (m && m.price != null) ? Number(m.price) : 0
}
const purchaseRate = computed(() => totals.value.purchases || {})
// 成本明细（小时速率）：仅列出有外购用量的物料，按金额降序
const costDetail = computed(() => {
  const rows = []
  for (const k in purchaseRate.value) {
    const qty = Number(purchaseRate.value[k]) || 0
    if (qty <= 0) continue
    const m = MATERIAL_MAP[k]
    rows.push({ id: k, name: m ? m.name : k, unit: (m && m.unit) ? m.unit : 't', color: m ? m.color : null, qty, price: priceOf(k) })
  }
  for (const r of rows) r.amt = r.qty * r.price
  rows.sort((a, b) => b.amt - a.amt)
  return rows
})
// 外购成本小时速率（元/h）
const costRateRaw = computed(() => costDetail.value.reduce((s, r) => s + r.amt, 0))
// 成本构成明细展开开关
const costOpen = ref(false)

// ---------- 墙钟周期：当日 / 当月 / 当年 0 点起已过小时数（30s 刷新，离线/无遥测也随时间推进） ----------
const clock = ref(0)
let _clockTimer = null
onMounted(() => { _clockTimer = setInterval(() => { clock.value++ }, 30000) })
onBeforeUnmount(() => { if (_clockTimer) clearInterval(_clockTimer) })
function elapsedHours(kind) {
  void clock.value
  const n = new Date()
  const start = kind === 'day' ? new Date(n.getFullYear(), n.getMonth(), n.getDate())
    : kind === 'month' ? new Date(n.getFullYear(), n.getMonth(), 1)
    : new Date(n.getFullYear(), 0, 1)
  return Math.max(0, (n - start) / 3.6e6)
}

// 当前档位核算：realtime=小时速率；day/month/year = 速率 × 周期已过小时数（当日/当月/当年累计）
const period = computed(() => {
  const p = plantPeriod.value
  const t = totals.value
  const energy = plantEnergy.value.total || 0   // GJ/h
  const elec = plantElec.value || 0             // MWh/h
  const co2 = t.co2_total || 0
  const direct = t.co2_direct || 0
  const indirect = t.co2_indirect || 0
  const steel = t.steel_output || 0
  const costRate = costRateRaw.value            // 元/h
  if (p === 'realtime') {
    return { energy, elec, co2, direct, indirect, steel, cost: costRate / 1e4, u: P_UNIT.realtime }
  }
  const h = elapsedHours(p)
  if (p === 'day') {
    return {
      energy: energy * h, elec: elec * h, co2: co2 * h, direct: direct * h, indirect: indirect * h,
      steel: steel * h, cost: (costRate * h) / 1e4, u: P_UNIT.day,
    }
  }
  if (p === 'month') {
    return {
      energy: (energy * h) / 1e4, elec: (elec * h) / 10, co2: (co2 * h) / 1e4,
      direct: (direct * h) / 1e4, indirect: (indirect * h) / 1e4, steel: (steel * h) / 1e4,
      cost: (costRate * h) / 1e4, u: P_UNIT.month,
    }
  }
  return { // year
    energy: (energy * h) / 1e4, elec: (elec * h) / 1e5, co2: (co2 * h) / 1e4,
    direct: (direct * h) / 1e4, indirect: (indirect * h) / 1e4, steel: (steel * h) / 1e4,
    cost: (costRate * h) / 1e8, u: P_UNIT.year,
  }
})
const periodDesc = computed(() => {
  const p = plantPeriod.value
  if (p === 'realtime') return t('口径：当前小时速率 · 综合能耗 GJ/h · 电耗 MWh/h · 总排放 tCO₂/h · 钢产量 t/h')
  const n = new Date()
  const pad = (x) => String(x).padStart(2, '0')
  const dayMark = `${n.getMonth() + 1}月${n.getDate()}日 ${pad(n.getHours())}:${pad(n.getMinutes())}`
  if (p === 'day') return t('累计口径：今日 0 点起至 ') + dayMark + t('（速率 × 已过小时 · 跨日自动归零）')
  if (p === 'month') return t('累计口径：本月 1 日 0 点起至 ') + dayMark
  return t('累计口径：本年 1 月 1 日 0 点起至 ') + dayMark
})

// ---------- 同比 / 环比（日度 / 月度档） ----------
// 无真实历史台账时不填数（不造假）：卡片保留、值显示「—」；接入日/月报历史后在此启用真实对比。
const cmp = computed(() => {
  if (plantPeriod.value !== 'day' && plantPeriod.value !== 'month') return null
  return { yoy: null, mom: null }
})
function signedPct(v) {
  if (v == null) return '—'
  const s = v >= 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(1)}%`
}
function dirCls(v) {
  if (v == null) return 'flat'
  if (v > 0.0005) return 'worse'    // 能耗上升 → 警示色
  if (v < -0.0005) return 'better'  // 能耗下降 → 向好色
  return 'flat'
}
// 策略节能减碳效果（基线 vs 策略）：节能与减碳并重
const stratCmp = computed(() => {
  const b = store.baseline && store.baseline.totals
  const s = store.strategy && store.strategy.totals
  if (!b || !s) return { energyRed: 0, energyPct: '—', co2Red: 0, co2Pct: '—' }
  const er = (b.energy_total || 0) - (s.energy_total || 0)
  const cr = (b.co2_total || 0) - (s.co2_total || 0)
  return {
    energyRed: er,
    energyPct: b.energy_total ? (er / b.energy_total * 100).toFixed(1) : '—',
    co2Red: cr,
    co2Pct: b.co2_total ? (cr / b.co2_total * 100).toFixed(1) : '—',
  }
})

const directPct = computed(() => {
  const t = totals.value.co2_total || 0
  return t ? Math.round((totals.value.co2_direct || 0) / t * 100) : 0
})
const indirectPct = computed(() => 100 - directPct.value)
const co2Color = computed(() => {
  const v = totals.value.intensity
  if (v > 1200) return 'var(--red)'
  if (v > 600) return 'var(--yellow)'
  return 'var(--green)'
})
const topEmitters = computed(() => {
  const r = store.resultForView
  if (!r || !r.units) return []
  const total = r.units.reduce((s, u) => s + (u.co2_total || 0), 0) || 1
  return [...r.units]
    .sort((a, b) => b.co2_total - a.co2_total)
    .slice(0, 4)
    .map((u) => ({ ...u, share: (u.co2_total || 0) / total }))
})

function shareColor(p) {
  const stops = [[61, 110, 140], [201, 162, 59], [192, 86, 76]]
  const t = Math.max(0, Math.min(1, (p || 0) / 0.25))
  let c
  if (t < 0.5) c = stops[0].map((v, i) => Math.round(v + (stops[1][i] - v) * (t / 0.5)))
  else c = stops[1].map((v, i) => Math.round(v + (stops[2][i] - v) * ((t - 0.5) / 0.5)))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
function typeLabel(t) { return (UNIT_TYPES.find((x) => x.type === t) || {}).label || t }
function fmt(n) {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  const v = Number(n)
  const abs = Math.abs(v)
  const d = abs >= 1e5 ? 0 : abs >= 100 ? 1 : abs >= 1 ? 2 : 3
  return v.toLocaleString('zh-CN', { maximumFractionDigits: d })
}
</script>

<style scoped>
/* .x-btn / .scope* / .park-sum 已统一定义于全局 main.css，此处不再重复 */
/* 本析智擎对话界面 absolute 铺满面板（覆盖 padding，视觉通栏） */
.inspector-body { position: relative; }
/* 总览指标卡：统一中性底色（与全局面板一致），不再按能耗/碳排区分彩色底，避免视觉杂乱；
 * 语义色仅保留在数值上（co2Color 强度警示），卡片本身一色到底 */
.te-row { align-items: flex-start; padding-top: 9px; padding-bottom: 9px; }
/* 全厂总览：实时 / 日度 / 月度 / 年度 时段切换（紧凑分段条，激活金底墨字） */
.plant-tabs {
  display: flex; gap: 2px; margin: 0 0 7px; padding: 2px;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 4px;
}
.plant-tab {
  flex: 1; min-width: 0; height: 22px; padding: 0 2px;
  border: none; background: transparent; border-radius: 3px;
  color: var(--muted); font-size: 10px; cursor: pointer;
  white-space: nowrap; transition: background .12s, color .12s;
}
.plant-tab:hover { background: var(--panel-3); color: var(--text); }
.plant-tab.on { background: var(--accent); color: var(--on-accent); font-weight: 600; }
.plant-note { font-size: 9px; line-height: 1.5; color: var(--muted); margin: 0 0 6px; }
/* 同比 / 环比 对比行（日度 / 月度档） */
.cmp-row { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 8px; }
.cmp-row .chip2 b { font-size: 12px; font-weight: 500; }
.chip2 b.better { color: var(--green); }
.chip2 b.worse { color: var(--red); }
.chip2 b.flat { color: var(--muted); }
.plant-foot { margin-top: 6px; font-size: 9px; line-height: 1.5; color: var(--muted); }
/* 成本卡（可点击展开构成明细） */
.chip2.tog { cursor: pointer; transition: border-color .15s, background .15s; }
.chip2.tog:hover { border-color: var(--accent); }
.chip2.tog.open { border-color: var(--accent); background: var(--accent-l, rgba(95,130,148,.08)); }
.chip2.tog .caret { font-style: normal; font-size: 8px; margin-left: 2px; }
.cost-detail { margin-top: 6px; border: 1px solid var(--line); border-radius: 4px; background: var(--panel-2, rgba(0,0,0,.02)); padding: 5px 7px; }
.cd-head { font-size: 9.5px; color: var(--accent2); margin-bottom: 4px; line-height: 1.5; }
.cd-row { display: flex; align-items: baseline; gap: 6px; padding: 3px 0; font-size: 10px; }
.cd-row + .cd-row { border-top: 1px dashed var(--line); }
.cd-name { flex: 0 0 auto; font-size: 9.5px; color: #fff; border-radius: 3px; padding: 1px 5px; }
.cd-qty { flex: 1; min-width: 0; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cd-amt { flex: 0 0 auto; text-align: right; font-variant-numeric: tabular-nums; }
.cd-amt b { font-weight: 600; }
.cd-amt i, .cd-qty i { font-style: normal; color: var(--muted); }
.cd-empty { justify-content: center; color: var(--muted); border-top: none !important; }
.cd-note { margin-top: 4px; font-size: 9px; line-height: 1.5; color: var(--muted); border-top: 1px dashed var(--line); padding-top: 4px; }
.app.sim-dark .chip2.tog.open { background: rgba(95,130,148,.15); }
/* 直接/间接 图例：百分占比小注与色点间距 */
.scope-legend em { font-style: normal; color: var(--muted); }
.scope-legend .dot { margin-left: 0; }
.app.sim-dark .plant-tab:hover { background: #2A2E2A; color: #E2E0DA; }
.app.sim-dark .plant-tab.on { background: var(--accent); color: var(--on-accent); }
.te-bar { display: block; height: 4px; border-radius: 2px; background: var(--panel-2); overflow: hidden; margin-top: 5px; }
.te-bar > i { display: block; height: 100%; border-radius: 2px; }
.te-pct { flex: 0 0 44px; text-align: right; color: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.strat-cmp { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 6px 0; }
.sc-item {
  border: 1px solid var(--line); border-radius: 4px; padding: 6px 8px;
  display: flex; flex-direction: column; gap: 2px; background: var(--panel-2, rgba(0,0,0,.03));
}
.sc-item span { font-size: 10px; color: var(--muted); }
.sc-item b { font-size: 16px; font-variant-numeric: tabular-nums; }
.sc-item b.good { color: var(--green, #2E8B57); }
.sc-item i { font-style: normal; font-size: 10px; color: var(--muted); }
</style>
