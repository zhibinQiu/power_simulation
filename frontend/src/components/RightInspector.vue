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
            <!-- 全厂总览分两类：实时（小时粒度）与年度核算（按 8000h/年折算） -->
            <div class="plant-group">
              <div class="plant-sec">{{ t('实时全厂总览') }}</div>
              <div class="chips">
                <div class="chip2 e"><span>{{ t('综合能耗') }}</span><b>{{ fmt(plantEnergy.total) }}</b><i>GJ/h</i></div>
                <div class="chip2 e"><span>{{ t('单位能耗') }}</span><b>{{ fmt(plantEnergy.intensity) }}</b><i>kgce/t</i></div>
                <div class="chip2 e"><span>{{ t('电耗') }}</span><b>{{ fmt(plantElec) }}</b><i>MWh/h</i></div>
                <div class="chip2 c"><span>{{ t('总排放') }}</span><b :style="{color:co2Color}">{{ fmt(totals.co2_total) }}</b><i>tCO₂/h</i></div>
                <div class="chip2 c"><span>{{ t('吨钢强度') }}</span><b>{{ fmt(totals.intensity) }}</b><i>kg/t</i></div>
                <div class="chip2"><span>{{ t('钢产量') }}</span><b>{{ fmt(totals.steel_output) }}</b><i>t/h</i></div>
                <div class="chip2 c"><span>{{ t('碳利用率') }}</span><b>{{ (totals.carbon_utilization*100).toFixed(1) }}</b><i>%</i></div>
              </div>
              <div class="scope">
                <div class="scope-bar">
                  <i class="scope-direct" :style="{ width: directPct + '%' }"></i>
                  <i class="scope-indirect" :style="{ width: indirectPct + '%' }"></i>
                </div>
                <div class="scope-legend">
                  <span>{{ t('直接') }} {{ fmt(totals.co2_direct) }} ({{ directPct }}%)</span>
                  <span>{{ t('间接') }} {{ fmt(totals.co2_indirect) }} ({{ indirectPct }}%)</span>
                </div>
              </div>
            </div>

            <div class="plant-group">
              <div class="plant-sec">{{ t('年度核算全厂总览') }}</div>
              <div class="chips">
                <div class="chip2 e"><span>{{ t('年度综合能耗') }}</span><b>{{ fmt(annual.energy) }}</b><i>万GJ</i></div>
                <div class="chip2 e"><span>{{ t('单位能耗') }}</span><b>{{ fmt(plantEnergy.intensity) }}</b><i>kgce/t</i></div>
                <div class="chip2 e"><span>{{ t('年度电耗') }}</span><b>{{ fmt(annual.elec) }}</b><i>亿kWh</i></div>
                <div class="chip2 c"><span>{{ t('年度总排放') }}</span><b :style="{color:co2Color}">{{ fmt(annual.co2) }}</b><i>万tCO₂</i></div>
                <div class="chip2 c"><span>{{ t('吨钢强度') }}</span><b>{{ fmt(totals.intensity) }}</b><i>kg/t</i></div>
                <div class="chip2"><span>{{ t('年度钢产量') }}</span><b>{{ fmt(annual.steel) }}</b><i>万t</i></div>
                <div class="chip2 c"><span>{{ t('碳利用率') }}</span><b>{{ (totals.carbon_utilization*100).toFixed(1) }}</b><i>%</i></div>
              </div>
              <div class="scope">
                <div class="scope-bar">
                  <i class="scope-direct" :style="{ width: directPct + '%' }"></i>
                  <i class="scope-indirect" :style="{ width: indirectPct + '%' }"></i>
                </div>
                <div class="scope-legend">
                  <span>{{ t('直接') }} {{ fmt(annual.direct) }} ({{ directPct }}%)</span>
                  <span>{{ t('间接') }} {{ fmt(annual.indirect) }} ({{ indirectPct }}%)</span>
                </div>
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
import { computed, ref, defineAsyncComponent } from 'vue'
import { energyOf } from '../utils/energy'
import { useSimStore, UNIT_TYPES } from '../stores/sim'
import { MATERIALS } from '../data/flowLibrary'
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

const totals = computed(() => {
  const base = store.resultForView ? store.resultForView.totals : {
    co2_total: 0, intensity: 0, carbon_utilization: 0, steel_output: 0, co2_direct: 0, co2_indirect: 0,
    energy_total: 0, elec: 0, fuel_energy: 0,
  }
  if (store.live) {
    return {
      co2_total: store.live.total_co2, intensity: store.live.intensity,
      steel_output: store.live.steel_output, carbon_utilization: base.carbon_utilization,
      co2_direct: base.co2_direct, co2_indirect: base.co2_indirect,
    }
  }
  return base
})
// 全厂综合能耗（节能减碳主题：先能后碳）。优先用后端 totals，缺失时由工序能耗汇总反推。
const plantEnergy = computed(() => {
  const t = totals.value
  if (t && t.energy_total != null) return { total: t.energy_total, intensity: t.energy_intensity }
  const r = store.resultForView
  const units = (r && r.units) || []
  let total = 0
  for (const u of units) total += energyOf(u).total
  const steel = (t && t.steel_output) || 0
  return { total, intensity: steel > 0 ? (total * 34.12) / steel : 0 }
})
// 全厂电耗：优先用后端 totals，缺失时由工序台账/碳素流反推汇总
const plantElec = computed(() => {
  const t = totals.value
  if (t && t.elec != null) return t.elec
  const r = store.resultForView
  const units = (r && r.units) || []
  let sum = 0
  for (const u of units) sum += energyOf(u).elec
  return sum
})
// 年运行小时（钢铁长流程：日历 8760h 扣除检修停机约 760h），口径与 HMI 大屏「年度碳排放」一致
const ANNUAL_HOURS = 8000
// 年度核算全厂总览：按 ANNUAL_HOURS 折算为年度量（万GJ / 亿kWh / 万tCO₂ / 万t）
const annual = computed(() => {
  const t = totals.value
  const energy = plantEnergy.value.total || 0
  const elec = plantElec.value || 0
  const co2 = t.co2_total || 0
  const direct = t.co2_direct || 0
  const indirect = t.co2_indirect || 0
  const steel = t.steel_output || 0
  return {
    energy: (energy * ANNUAL_HOURS) / 10000,    // 万GJ
    elec: (elec * ANNUAL_HOURS) / 100000,        // 亿kWh（1亿kWh = 10^5 MWh）
    co2: (co2 * ANNUAL_HOURS) / 10000,           // 万tCO₂
    direct: (direct * ANNUAL_HOURS) / 10000,     // 万tCO₂
    indirect: (indirect * ANNUAL_HOURS) / 10000, // 万tCO₂
    steel: (steel * ANNUAL_HOURS) / 10000,       // 万t
  }
})
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
function fmt(n) { return (n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })) }
</script>

<style scoped>
/* .x-btn / .scope* / .park-sum 已统一定义于全局 main.css，此处不再重复 */
/* 本析智擎对话界面 absolute 铺满面板（覆盖 padding，视觉通栏） */
.inspector-body { position: relative; }
/* 总览指标卡：统一中性底色（与全局面板一致），不再按能耗/碳排区分彩色底，避免视觉杂乱；
 * 语义色仅保留在数值上（co2Color 强度警示），卡片本身一色到底 */
.te-row { align-items: flex-start; padding-top: 9px; padding-bottom: 9px; }
/* 全厂总览：实时 / 年度核算两类分区标题（标题 + 延展细线） */
.plant-group + .plant-group { margin-top: 10px; padding-top: 2px; }
.plant-sec {
  display: flex; align-items: center; gap: 8px;
  font-size: 10px; color: var(--muted); letter-spacing: .05em;
  margin: 0 0 5px;
}
.plant-sec::after { content: ''; flex: 1; height: 1px; background: var(--line); }
.plant-group + .plant-group .plant-sec { margin-top: 8px; }
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
