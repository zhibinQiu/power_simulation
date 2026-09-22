<template>
  <div v-if="unit" class="other-unit-panel">
    <!-- 行业资源包（非钢铁主场景）工序属性：按包内字典/模板参数渲染，替代钢铁专用核算面板 -->
    <div class="ou-head">
      <div class="ou-name">{{ unit.name }}</div>
      <div class="ou-sub">
        <span class="ou-type">{{ typeName }}</span>
        <span class="ou-tag">{{ t('资源包工序') }}</span>
      </div>
    </div>

    <!-- 运行指标 · 静态核算（功率 × 电网因子）：功率口径与实时折碳一致（实测功率优先） -->
    <CollapseSection :title="t('运行指标 · 折碳核算')" tone="blue" :open="true">
      <div class="chips">
        <div class="chip2"><span>{{ t('实时功耗') }}</span><b>{{ fmt(powerKW) }}</b><i>kW</i></div>
        <div class="chip2"><span>{{ t('实时碳排') }}</span><b>{{ fmt(carbonKgH, 3) }}</b><i>kgCO₂/h</i></div>
      </div>
      <div class="kv2c">
        <div class="kv2-row"><span class="k">{{ t('功率口径') }}</span><span class="v"><b>{{ powerSrcText }}</b></span></div>
        <div v-for="s in powerSources" :key="s.id" class="kv2-row">
          <span class="k">{{ s.label }}<i class="u">{{ s.device ? ' · ' + s.device + (s.prop ? ' · ' + s.prop : '') : '' }}</i></span>
          <span class="v"><b>{{ fmt(s.measured) }}</b> <span class="u">kW</span></span>
        </div>
        <div class="kv2-row"><span class="k">{{ t('电耗速率') }}</span><span class="v"><b>{{ fmt(energyKH) }}</b> <span class="u">kWh/h</span></span></div>
        <div class="kv2-row"><span class="k">{{ t('折碳总量（tCO₂/h）') }}</span><span class="v"><b>{{ fmt(tCO2H, 4) }}</b> <span class="u">tCO₂/h</span></span></div>
      </div>
      <div class="pr-hint">{{ methodNote }}</div>
    </CollapseSection>

    <!-- 工艺参数（包内出厂设定） -->
    <CollapseSection v-if="paramRows.length" :title="t('工艺参数（出厂设定）')" tone="amber">
      <div class="kv2c">
        <div v-for="p in paramRows" :key="p.key" class="kv2-row">
          <span class="k">{{ p.label }}</span>
          <span class="v"><b>{{ p.value }}</b> <span class="u">{{ p.unit }}</span></span>
        </div>
      </div>
      <div class="pr-hint">{{ t('参数取值来自资源包工艺模板；可在「流程编排」中调整后保存为方案。') }}</div>
    </CollapseSection>

    <!-- 输入 / 输出物料 -->
    <CollapseSection v-if="ins.length || outs.length" :title="t('输入 / 输出')" tone="green">
      <div class="kv2c">
        <div v-if="ins.length" class="kv2-row"><span class="k">{{ t('输入') }}</span><span class="v"><b>{{ ins.join('、') }}</b></span></div>
        <div v-if="outs.length" class="kv2-row"><span class="k">{{ t('输出') }}</span><span class="v"><b>{{ outs.join('、') }}</b></span></div>
      </div>
    </CollapseSection>

    <!-- 关联工艺（物料流上下游） -->
    <CollapseSection v-if="ups.length || downs.length" :title="t('关联工艺')" tone="teal">
      <div class="kv2c">
        <div v-if="ups.length" class="kv2-row"><span class="k">{{ t('上游来料') }}</span><span class="v"><b>{{ ups.join('、') }}</b></span></div>
        <div v-if="downs.length" class="kv2-row"><span class="k">{{ t('下游供出') }}</span><span class="v"><b>{{ downs.join('、') }}</b></span></div>
      </div>
    </CollapseSection>

    <!-- 工艺说明 -->
    <CollapseSection v-if="procDesc" :title="t('工艺说明')" tone="gray">
      <div class="ou-desc">{{ procDesc }}</div>
    </CollapseSection>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'
import CollapseSection from './CollapseSection.vue'

const store = useSimStore()

const fmt = (v, d = 2) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d))
const unit = computed(() => store.selectedUnit)
// 模板节点（含端口/参数/连接关系）；非钢场景 model.units 与 scheme.nodes 一一对应
const node = computed(() => {
  const u = unit.value
  if (!u || !store.scheme) return null
  return store.scheme.nodes.find((n) => n.id === u.id) || null
})
const dict = computed(() => store.sceneCtx || null)
const procDef = computed(() => {
  const u = unit.value
  if (!u || !dict.value?.processes) return null
  return dict.value.processes.find((p) => p.type === u.type) || null
})
const typeName = computed(() => procDef.value?.name || unit.value?.type || '')
const procDesc = computed(() => procDef.value?.desc || '')
const blu = computed(() => store.selectedResult || null)

const powerMW = computed(() => node.value?.params?.power ?? unit.value?.params?.power ?? 0)
// 包内功率参数（MW → kW）：未接入实测时的估算口径
const packKW = computed(() => (Number(powerMW.value) || 0) * 1000)
// 实际参与折碳的功率（kW）：本工序附加的功率型传感器（电功率传感器 kW）读数优先；
// 可变设备的设定值只调工况、不参与折碳。
const powerKW = computed(() => {
  const v = blu.value?.powerKW
  return (v != null && isFinite(v)) ? Number(v) : packKW.value
})
const powerSources = computed(() => (blu.value && Array.isArray(blu.value.powerSources)) ? blu.value.powerSources : [])
const powerSrcText = computed(() => {
  const b = blu.value
  if (b && b.powerMeasured) return t('实测功率（数据源管理采集设备）')
  if (b && b.powerSimulated) return t('传感器读数（模拟 / 联动 / 固定来源，未接入实测）')
  return t('包内功率参数（未添加功率传感器）')
})
// baseline 静态核算单位：energy=kWh/h，carbon=kgCO₂/h；缺失时按功率×排放因子回退
const energyKH = computed(() => {
  const e = blu.value?.energy
  if (e != null && isFinite(e)) return e
  return powerKW.value
})
const carbonKgH = computed(() => {
  const c = blu.value?.carbon
  if (c != null && isFinite(c)) return c
  return powerKW.value * store._gridFactorKg()
})
const tCO2H = computed(() => carbonKgH.value / 1000)

const methodNote = computed(() => {
  const m = dict.value?.method
  return m ? `${m.name}。${m.note}` : t('按电网排放因子折算范围二间接排放（kgCO₂/kWh）。')
})
const paramRows = computed(() => {
  const defs = procDef.value?.params
  const p = node.value?.params || unit.value?.params || {}
  if (!defs || !defs.length) return []
  return defs
    .filter((d) => p[d.key] != null)
    .map((d) => ({
      key: d.key,
      label: d.label || d.key,
      unit: d.unit || '',
      value: p[d.key],
    }))
})

const matName = (id) => {
  if (!id) return ''
  const m = dict.value?.materials?.find((x) => x.id === id)
  return m?.name || id
}
const ioOf = (dir) => {
  const n = node.value
  if (!n?.ports?.[dir]) return []
  const list = (Array.isArray(n.ports[dir]) ? n.ports[dir] : [n.ports[dir]])
    .map((p) => p?.material || p)
  const names = list.map(matName).filter(Boolean)
  const main = procDef.value?.mainOut
  if (dir === 'out' && main) {
    const mainName = matName(main)
    const idx = names.findIndex((x) => x === mainName)
    if (idx >= 0) names[idx] = mainName + '（主产物）'
  }
  return names
}
const ins = computed(() => ioOf('in'))
const outs = computed(() => ioOf('out'))

const nodeNameOf = (id) => {
  const n = store.scheme?.nodes?.find((x) => x.id === id)
  if (!n) return id
  if (n.name) return String(n.name)
  const def = dict.value?.processes?.find((p) => p.type === n.type)
  return def?.name || n.type || id
}
const ups = computed(() => {
  const u = unit.value
  if (!u || !store.scheme) return []
  return store.scheme.connections
    .filter((c) => c.to === u.id)
    .map((c) => nodeNameOf(c.from))
    .filter((v, i, a) => a.indexOf(v) === i)
})
const downs = computed(() => {
  const u = unit.value
  if (!u || !store.scheme) return []
  return store.scheme.connections
    .filter((c) => c.from === u.id)
    .map((c) => nodeNameOf(c.to))
    .filter((v, i, a) => a.indexOf(v) === i)
})
</script>

<style scoped>
.other-unit-panel { display: flex; flex-direction: column; gap: 10px; }
.ou-head { padding: 2px 2px 4px; }
.ou-name { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.4; }
.ou-sub { display: flex; align-items: center; gap: 8px; margin-top: 3px; flex-wrap: wrap; }
.ou-type { font-size: 11px; color: var(--muted); }
.ou-tag { font-size: 10px; color: var(--brand2, #3a7bd5); background: color-mix(in srgb, var(--brand2, #3a7bd5) 10%, transparent); border: 1px solid color-mix(in srgb, var(--brand2, #3a7bd5) 30%, transparent); padding: 1px 6px; border-radius: 8px; }
.ou-desc { font-size: 11px; color: var(--muted); line-height: 1.7; white-space: pre-line; }
</style>
