<template>
  <div v-if="unit && res">
    <div class="insp-head">
      <div>
        <div class="insp-title">{{ unit.name }}</div>
        <div class="insp-sub">{{ typeLabel(unit.type) }} · 能耗与碳排放核算明细</div>
      </div>
    </div>

    <!-- 厂内实例切换：该工艺类型下有多台实例时，可点击切换查看 -->
    <div class="inst-switch" v-if="siblings.length > 1">
      <button
        v-for="i in siblings"
        :key="i.id"
        class="inst-chip"
        :class="{ on: i.id === unit.id }"
        @click="store.selectUnit(i.id)"
      >{{ i.name }}</button>
    </div>

    <!-- 模块可上下拖拽重排，顺序/折叠状态持久化到 localStorage；各模块说明直接写在本模块内部 -->
    <template v-for="sid in layout.state.order" :key="sid">
      <CollapseSection
        v-if="sid === 'energy'"
        title="能耗"
        tone="blue"
        drag-id="energy"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示工序综合能耗、电耗及燃料能耗等核心指标。</p>
        <div class="chips">
          <div class="chip2"><span>综合能耗</span><b>{{ f(energy.intensity) }}</b><i>kgce/t</i></div>
          <div class="chip2"><span>电耗</span><b>{{ f(energy.elec) }}</b><i>MWh/h</i></div>
          <div class="chip2"><span>燃料能耗</span><b>{{ f(energy.fuel) }}</b><i>GJ/h</i></div>
        </div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'carbon'"
        title="碳排放"
        tone="red"
        drag-id="carbon"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示碳排放总量、直接排放（范围一）、间接排放（范围二）及占全厂排放比例。</p>
        <div class="chips">
          <div class="chip2"><span>总排放</span><b>{{ f(res.co2_total) }}</b><i>tCO₂/h</i></div>
          <div class="chip2"><span>直接 · 范围一</span><b>{{ f(res.co2_direct) }}</b><i>tCO₂/h</i></div>
          <div class="chip2"><span>间接 · 范围二</span><b>{{ f(res.co2_indirect) }}</b><i>tCO₂/h</i></div>
          <div class="chip2"><span>占全厂排放</span><b>{{ sharePct }}</b><i>占比</i></div>
        </div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'ledger'"
        title="核算台账：用量 · 因子 · 贡献"
        tone="amber"
        drag-id="ledger"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示各输入项的用量、排放因子及碳排放贡献明细。</p>
        <div class="ledger">
          <div class="ledger-head"><span>项目</span><span>用量</span><span>贡献</span></div>
          <transition-group name="rise" tag="div" class="ledger-body">
            <div v-for="(it, i) in res.breakdown" :key="i" class="ltr" :class="it.scope">
              <div class="ltr-top">
                <span class="it">{{ it.item }}</span>
                <span class="num">{{ it.qty != null ? fmtNum(it.qty) : '—' }}<span class="u">{{ it.qty_unit }}</span></span>
                <div class="bar-cell">
                  <div class="bar-wrap">
                    <div class="bar" :class="barClass(it)" :style="{ width: barW(it) + '%' }"></div>
                    <span class="bar-val">{{ it.co2 < 0 ? '−' : '' }}{{ f(Math.abs(it.co2)) }}</span>
                  </div>
                </div>
              </div>
              <div class="ltr-basis" v-if="it.formula || it.basis">{{ it.formula || it.basis }}</div>
            </div>
          </transition-group>
        </div>
        <div class="legend-row">
          <span>直接排放（范围一）</span>
          <span>间接排放（范围二）</span>
          <span>减排项</span>
        </div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'balance'"
        title="碳平衡"
        tone="teal"
        drag-id="balance"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示输入碳、排放碳、固于钢及已捕集碳的流向平衡。</p>
        <div class="bal">
          <div class="bal-item"><span>输入碳</span><b>{{ f(res.carbon_in) }}</b><i>tC/h</i></div>
          <div class="bal-item"><span>排放碳</span><b>{{ f(res.carbon_to_co2) }}</b><i>tC/h</i></div>
          <div class="bal-item"><span>固于钢</span><b>{{ f(res.carbon_to_steel) }}</b><i>tC/h</i></div>
          <div class="bal-item"><span>已捕集</span><b>{{ f(res.carbon_captured) }}</b><i>tC/h</i></div>
        </div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'live'"
        title="实时监测"
        tone="teal"
        drag-id="live"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示实时运行指标与排放数据；高炉额外展示风口热制度 TFT。</p>
        <div class="chips">
          <div class="chip2 tft" v-if="tftCtx">
            <span>风口 TFT</span>
            <b :style="{ color: tftCtx.status ? tftCtx.status.color : '' }">{{ f(tftCtx.tft) }}</b>
            <i>℃</i>
            <em v-if="tftCtx.status" :style="{ background: tftCtx.status.color }">{{ tftCtx.status.label }}</em>
          </div>
          <div class="chip2"><span>实时排放</span><b>{{ f(liveData != null ? liveData : res.co2_total) }}</b><i>tCO₂/h</i></div>
        </div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'io'"
        title="输入输出 · 编排设定"
        tone="green"
        drag-id="io"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示在编排模式下设定的输入输出物料与配比（只读，调整请进入「编排」）。</p>
        <div class="card io-card" v-if="ioCtx">
          <div class="io-col">
            <span class="pc-t">输入（配比）</span>
            <div v-for="(p, i) in ioCtx.inputs" :key="p.id || ('in' + i)" class="io-row">
              <span class="io-mat">{{ matName(p.material) }}</span>
              <span class="io-val">{{ ratioOf(p.material) != null ? Math.round(ratioOf(p.material) * 100) + '%' : '—' }}</span>
            </div>
            <div v-if="!ioCtx.inputs.length" class="pr-hint">未在编排中登记输入物料。</div>
          </div>
          <div class="io-col">
            <span class="pc-t">输出（到下游 / 成品）</span>
            <div v-for="(p, i) in ioCtx.outputs" :key="p.id || ('out' + i)" class="io-row">
              <span class="io-mat">{{ matName(p.material) }}</span>
            </div>
            <div v-if="!ioCtx.outputs.length" class="pr-hint">未在编排中登记输出物料。</div>
          </div>
        </div>
        <div class="card note" v-else>该实例未在编排中登记输入输出。</div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'devices'"
        title="可调节"
        tone="amber"
        drag-id="devices"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示可在线调节的设备参数及当前读数，点击可跳转至设备详情进行调整。</p>
        <div class="card list-card" v-if="adjustable.length">
          <div v-for="d in adjustable" :key="d.type" class="lrow" :class="{ click: !!d.devId }" @click="d.devId && store.openDeviceDetail(d.devId)">
            <div class="l-stack">
              <span class="l-tt">{{ d.label }}</span>
              <span class="l-sub">{{ d.measures }}</span>
            </div>
            <span class="l-trail">{{ d.reading == null ? '—' : f(d.reading) }} <span class="u">{{ d.unit }}</span></span>
          </div>
        </div>
        <div class="card note" v-else>该工序未登记可调节设备。</div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'related'"
        title="关联设备"
        tone="green"
        drag-id="related"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">展示与该工序实际连线绑定的工辅设备（鼓风机/热风炉等），由编排连线动态推导。</p>
        <div class="card list-card" v-if="relatedDevices.length">
          <div v-for="d in relatedDevices" :key="d.type" class="lrow" :class="{ click: !!d.devId }" @click="d.devId && store.openDeviceDetail(d.devId)">
            <div class="l-stack">
              <span class="l-tt">{{ d.label }}</span>
              <span class="l-sub">{{ d.measures }}</span>
            </div>
            <span class="l-trail">{{ d.reading == null ? '—' : f(d.reading) }} <span class="u">{{ d.unit }}</span></span>
          </div>
        </div>
        <div class="card note" v-else>该工序暂无关联设备（可在「编排」中连线绑定工辅）。</div>
      </CollapseSection>

      <CollapseSection
        v-else-if="sid === 'strategy' && unitStrategy"
        title="减排策略 · AI 智能优化"
        tone="green"
        drag-id="strategy"
        v-model="layout.state.open[sid]"
        @drop="layout.move($event.from, $event.to, $event.position)"
      >
        <p class="sec-desc">用自然语言描述减排策略，系统自动解析并生成优化方案。</p>
        <div class="card">
          <!-- 策略状态 -->
          <div class="strategy-status" v-if="unitStrategy.parsed">
            <span class="sts-tag green">已解析 · {{ unitStrategy.parsed.ops.length }} 项操作</span>
            <span class="sts-tag" v-if="unitStrategy.delta">已仿真测试</span>
            <span class="sts-tag" v-if="unitStrategy.scenarioName">已保存</span>
          </div>
          <!-- 自然语言输入 -->
          <div class="strategy-prompt">
            <textarea v-model="strategyText" placeholder="用自然语言描述此工序的减排策略，例如：&#10;• 将电炉电弧炉供电煤耗从 0.38 降至 0.25 吨标煤/吨&#10;• 启用焦炉煤气制氢技术&#10;• 增加转炉余热回收率至 85%&#10;系统将自动解析并生成优化方案。"
                      class="strategy-input"></textarea>
            <div class="strategy-actions">
              <button class="btn btn-accent" @click="runStrategy" :disabled="store.parsing || store.busy">
                <span v-if="store.parsing">解析中...</span>
                <span v-else-if="store.busy">仿真中...</span>
                <span v-else>解析并仿真测试</span>
              </button>
              <button class="btn" @click="saveStrategy" :disabled="!unitStrategy.parsed || !unitStrategy.parsed.ops.length">
                保存策略并绑定工序
              </button>
            </div>
          </div>
          <!-- 仿真结果对比 -->
          <div v-if="unitStrategy.delta && unitStrategy.delta.totals" class="strategy-delta">
            <div class="delta-title">仿真测试结果对比</div>
            <div class="delta-grid">
              <div class="delta-item baseline">
                <span class="dl">原始排放</span>
                <span class="dv">{{ f(store.baseline?.totals?.co2_total) }} tCO₂/h</span>
              </div>
              <div class="delta-item strategy">
                <span class="dl">策略后排放</span>
                <span class="dv">{{ f(unitStrategy.delta.totals.co2_total) }} tCO₂/h</span>
              </div>
              <div class="delta-item delta">
                <span class="dl">减排量</span>
                <span class="dv" :style="{color:'#22c55e'}">
                  {{ unitStrategy.delta.totals.delta_co2 ? '-' + f(Math.abs(unitStrategy.delta.totals.delta_co2)) : '—' }} tCO₂/h
                </span>
              </div>
            </div>
          </div>
        </div>
      </CollapseSection>
    </template>
  </div>
  <div v-else class="empty-tip">
    <p>当前产线未部署该工艺，暂无核算数据。</p>
    <p class="sub">进入「编排」后，可将左侧条目拖入编排画布并仿真测试。</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { energyOf } from '../utils/energy'
import { useSimStore, UNIT_TYPES } from '../stores/sim'
import { DEVICE_MAP, PROCESS_ADJUSTABLE, MATERIAL_MAP } from '../data/flowLibrary'
import CollapseSection from './CollapseSection.vue'
import { buildRealtimeTftParams, collectTftContext, DEFAULT_TFT_CONFIG } from '../utils/tft'
import { useDragLayout } from '../composables/useDragSort'

const store = useSimStore()

/* 工序面板模块布局：按工序类型分别持久化（顺序 + 折叠状态，每次打开恢复上次布局）
 * 默认顺序：实时监测 → 能耗 → 碳排放 → 核算台账 → 碳平衡 → 输入输出 → 可调节 → 关联设备 → 减排策略
 * 默认可调节 / 关联设备 / 减排策略折叠，其余展开 */
const unitLayoutKey = computed(() => 'insp-layout:unit:v5:' + (store.selectedUnit?.type || 'unit'))
const layout = useDragLayout(
  unitLayoutKey,
  ['live', 'energy', 'carbon', 'ledger', 'balance', 'io', 'devices', 'related', 'strategy'],
  { live: true, energy: true, carbon: true, ledger: true, balance: true, io: true, devices: false, related: false, strategy: false },
)
// 选中工序实例：场景/列表/左侧工艺目录点击均直接选中具体实例，同一个实例只有一个面板
const unit = computed(() => store.selectedUnit)
const res = computed(() => store.selectedResult)
// 同类型厂内实例（用于实例切换）
const siblings = computed(() => {
  const t = unit.value ? unit.value.type : null
  if (!t) return []
  return store.model.units.filter((u) => u.type === t)
})
// 实时排放（实时遥测优先，缺省回退基线仿真值）
const liveData = computed(() => {
  const u = unit.value
  if (!u) return null
  const lu = store.liveUnit(u.id)
  return lu && lu.co2_total != null ? lu.co2_total : null
})

// TFT 实时参数：工序基础参数 + 当前工序热制度设备实际设定折算（拖动滑块实时联动）
const tftParams = computed(() => {
  const u = unit.value
  if (!u) return {}
  const sps = {}
  for (const dt of ['hot_blast_stove', 'blower', 'injector']) {
    const did = `${u.id}::${dt}`
    const sp = store.deviceSetpoints[did]
    const es = store.deviceExtraSetpoints[did]
    if (sp != null || (es && Object.keys(es).length)) sps[dt] = { setpoint: sp, extraSetpoints: es || {} }
  }
  return buildRealtimeTftParams('blast_furnace', u.params || {}, sps)
})

// TFT 计算上下文（值 + 状态），用于与实时监测其它指标一致的卡片显示
const tftCtx = computed(() => {
  if (!unit.value || unit.value.type !== 'blast_furnace') return null
  try { return collectTftContext(tftParams.value || {}, DEFAULT_TFT_CONFIG) } catch (e) { return null }
})

// 编排模式设定的输入输出与配比（只读展示）：实例 id 与编排节点 id 一致，直接查找
const ioNode = computed(() => {
  const id = unit.value && unit.value.id
  if (!id) return null
  return (store.scheme && store.scheme.nodes || []).find((n) => n.id === id) || null
})
const ioCtx = computed(() => {
  const n = ioNode.value
  if (!n) return null
  return { inputs: (n.ports && n.ports.in) || [], outputs: (n.ports && n.ports.out) || [] }
})
// 该物料在编排配比中的值（1 = 100%）
function ratioOf(mat) {
  const n = ioNode.value
  if (!n || !n.recipe) return null
  const r = n.recipe.find((x) => x.material === mat)
  return r != null ? r.ratio : null
}
const matName = (id) => (MATERIAL_MAP[id] && MATERIAL_MAP[id].name) || id

const energy = computed(() => energyOf(res.value))

// 当前工序的策略数据
const unitStrategy = computed(() => {
  if (!unit.value) return null
  return store.getUnitStrategy(unit.value.id) || null
})
// 策略输入文本（双向绑定到 store）
const strategyText = ref('')
watch(unitStrategy, (us) => { if (us) strategyText.value = us.text || '' }, { immediate: true })
async function runStrategy() {
  if (!unit.value) return
  store.setUnitStrategyText(unit.value.id, strategyText.value)
  await store.runUnitStrategy(unit.value.id)
}
async function saveStrategy() {
  if (!unit.value) return
  const name = unit.value.name + ' · 减排策略'
  await store.saveUnitStrategy(unit.value.id, name)
}

// 设备行数据统一构建：label/measures/reading（实时遥测优先，缺省回退设定值/默认值）
function buildDevRow(dt, u) {
  const d = DEVICE_MAP[dt] || {}
  const devId = `${u.id}::${dt}`
  const live = store.deviceLiveOf(devId)
  const sp = store.deviceSetpoints[devId] != null ? store.deviceSetpoints[devId] : null
  const def = d.setpoint ? d.setpoint.def : null
  return {
    type: dt,
    label: DEVICE_MAP[dt] ? DEVICE_MAP[dt].label : dt,
    measures: d.measures || '',
    unit: (d.setpoint && d.setpoint.unit) || d.unit || '',
    devId,
    reading: live != null ? live : (sp != null ? sp : def),
  }
}
// 可调节：工序基础清单（变频/除尘风机等非工辅设备），点击跳转对应实例详情进行调整
const adjustable = computed(() => {
  const u = unit.value
  if (!u) return []
  return (PROCESS_ADJUSTABLE[u.type] || []).map((dt) => buildDevRow(dt, u))
})
// 关联设备：实际连线绑定的工辅（鼓风机/热风炉等，含上游链路传递，由编排连线动态推导）
const relatedDevices = computed(() => {
  const u = unit.value
  if (!u) return []
  return store.linkedAuxOfUnit(u.id).map((dt) => buildDevRow(dt, u))
})

const maxAbs = computed(() => {
  if (!res.value || !res.value.breakdown.length) return 1
  let m = 0
  for (const it of res.value.breakdown) m = Math.max(m, Math.abs(it.co2))
  return m || 1
})
const sharePct = computed(() => {
  const base = store.baseline
  if (!res.value || !base || !base.totals.co2_total) return '0.0%'
  return (res.value.co2_total / base.totals.co2_total * 100).toFixed(1) + '%'
})
function barW(it) { return Math.max(4, (Math.abs(it.co2) / maxAbs.value) * 100) }
function barClass(it) { return it.co2 < 0 ? 'neg' : (it.scope === 'indirect' ? 'indirect' : 'direct') }
function typeLabel(t) { return (UNIT_TYPES.find((x) => x.type === t) || {}).label || t }
function f(n) { return (n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })) }
function fmtNum(n) { return Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }
</script>

<style scoped>
/* 模块内部说明：不单独成模块，直接写在对应模块内容区顶部 */
.sec-desc { font-size: 10.5px; line-height: 1.5; color: var(--muted); margin: 0 0 8px 0; padding: 0; }
/* .chips 已统一定义于全局 main.css */
/* TFT 卡片：与实时监测其它指标同一 chip2 形式，右侧附加状态徽章 */
.chip2.tft em { font-style: normal; font-size: 9px; line-height: 15px; color: #fff; border-radius: 8px; padding: 0 6px; margin-left: auto; flex: 0 0 auto; }
/* 输入输出（编排设定）只读展示 */
.io-card { display: flex; gap: 14px; }
.io-col { flex: 1; min-width: 0; }
.io-col .pc-t { display: block; font-size: 10px; color: var(--muted); margin-bottom: 4px; }
.io-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 5px 0; border-bottom: 1px dashed var(--line); font-size: 11.5px; }
.io-row:last-child { border-bottom: none; }
.io-mat { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.io-val { color: var(--accent); font-weight: 600; flex: 0 0 auto; }
.bal { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.bal-item { background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 5px 8px; display: flex; flex-direction: column; gap: 3px; }
.bal-item span { font-size: 10px; color: var(--muted); }
.bal-item b { font-size: 11px; font-weight: 400; font-variant-numeric: tabular-nums; }
.bal-item i { font-size: 10px; color: var(--muted); font-style: normal; }
.ledger { font-size: 11px; }
.ledger-head { display: flex; align-items: center; padding: 4px 2px; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 10px; }
.ledger-head span:nth-child(1) { flex: 1; }
.ledger-head span:nth-child(2) { width: 78px; text-align: right; }
.ledger-head span:nth-child(3) { width: 42%; }
.ledger-body { display: flex; flex-direction: column; }
.ltr { padding: 5px 2px; }
.ltr + .ltr { border-top: 1px solid var(--line); }
.ltr-top { display: flex; align-items: center; gap: 8px; }
.ltr-top .it { flex: 1; font-weight: 400; }
.ltr-top .num { width: 78px; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--text); }
.ltr-top .num .u { color: var(--muted); font-size: 10px; margin-left: 2px; }
.ltr-basis { font-size: 10px; color: var(--muted); margin-top: 4px; white-space: nowrap; overflow-x: auto; }
.bar-cell { width: 42%; }
.bar-wrap { display: flex; align-items: center; gap: 6px; }
.bar { height: 4px; border-radius: 2px; min-width: 2px; flex: 1; }
.bar.direct { background: var(--red); }
.bar.indirect { background: var(--yellow); }
.bar.neg { background: var(--green); }
.bar-val { font-size: 10px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.legend-row { display: flex; gap: 14px; flex-wrap: wrap; font-size: 10px; color: var(--muted); margin-top: 10px; }
.scope-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
.scope-dot.direct { background: var(--red); } .scope-dot.indirect { background: var(--yellow); } .scope-dot.neg { background: var(--green); }
/* 空态提示 */
.empty-tip { padding: 14px 10px; text-align: center; color: var(--muted); font-size: 11.5px; }
.empty-tip .sub { font-size: 10.5px; margin-top: 4px; opacity: .75; }
/* 可调设备列表：与资源管理视图一致（.lrow 等为全局样式） */
.list-card { padding: 2px 8px; }
/* 厂内实例切换条 */
.inst-switch { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
.inst-chip { font-size: 10.5px; padding: 3px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel-2); color: var(--text); cursor: pointer; }
.inst-chip:hover { border-color: var(--accent2); }
.inst-chip.on { background: var(--accent2); border-color: var(--accent2); color: #04121d; }

/* 策略面板样式 */
.strategy-status { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.sts-tag { font-size: 10px; padding: 2px 8px; border-radius: 3px; background: rgba(59,130,246,.1); color: var(--accent2); border: 1px solid rgba(59,130,246,.2); }
.sts-tag.green { background: rgba(34,197,94,.1); color: #22c55e; border-color: rgba(34,197,94,.2); }
.strategy-prompt { margin-bottom: 10px; }
.strategy-input { width: 100%; min-height: 80px; background: var(--bg); border: 1px solid var(--line); color: var(--text); border-radius: 3px; padding: 8px; font-size: 11px; line-height: 1.6; resize: vertical; font-family: inherit; }
.strategy-input:focus { border-color: var(--accent2); outline: none; }
.strategy-actions { display: flex; gap: 8px; margin-top: 8px; }
.btn { background: var(--panel-2); border: 1px solid var(--line); color: var(--text); border-radius: 3px; cursor: pointer; padding: 4px 12px; font-size: 11px; white-space: nowrap; }
.btn:hover { border-color: var(--accent2); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-accent { background: var(--accent2); border-color: var(--accent2); color: #04121d; }
.strategy-delta { margin-top: 12px; }
.delta-title { font-size: 11px; font-weight: 500; color: var(--accent2); margin-bottom: 8px; }
.delta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.delta-item { background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 5px; text-align: center; }
.dl { font-size: 10px; color: var(--muted); display: block; }
.dv { font-size: 11px; font-weight: 500; display: block; margin-top: 4px; font-variant-numeric: tabular-nums; }
</style>
