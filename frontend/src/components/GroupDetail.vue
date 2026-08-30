<template>
  <div v-if="group" class="group-detail">
    <div class="insp-head">
      <div>
        <div class="insp-title">▦ {{ group.name }}</div>
        <div class="insp-sub">{{ group.members.length }} {{ t('台成员设备') }} · {{ t('小组数值概览') }}</div>
      </div>
    </div>

    <CollapseSection :title="t('小组概览')" tone="blue" :default-open="true">
      <div class="chips">
        <div class="chip2"><span>{{ t('成员设备') }}</span><b>{{ group.members.length }}</b><i>{{ t('台') }}</i></div>
        <div class="chip2"><span>{{ t('碳排放') }}</span><b>{{ fmt(totals.co2) }}</b><i>tCO₂/h</i></div>
        <div class="chip2"><span>{{ t('能耗') }}</span><b>{{ fmt(totals.energy) }}</b><i>MWh/h</i></div>
        <div class="chip2"><span>{{ t('产量') }}</span><b>{{ fmt(totals.outMass) }}</b><i>t/h</i></div>
      </div>
      <div v-if="totals.intensity != null" class="kv2">
        <span>{{ t('小组排放强度') }}</span>
        <b>{{ fmt(totals.intensity) }} <span class="u">kg/t</span></b>
      </div>
    </CollapseSection>

    <CollapseSection :title="t('成员工艺 / 设备（实测值）')" tone="teal" :default-open="true">
      <div v-for="m in members" :key="m.id" class="lrow click" :class="{ active: activeMember === m.id }" @click="onMemberClick(m)">
        <div class="l-stack">
          <span class="l-tt">{{ m.name }}</span>
          <span class="l-sub">{{ nodeSub(m) }}</span>
        </div>
        <span v-if="m.kind === 'process' && estOf(m.id)" class="l-trail">{{ fmt(estOf(m.id).co2) }} <span class="u">tCO₂/h</span></span>
      </div>
      <div v-if="!members.length" class="empty">{{ t('该小组暂无成员。') }}</div>
      <div class="pr-hint">{{ t('点击成员可查看该工序/设备的详细数值属性。') }}</div>
    </CollapseSection>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'
import CollapseSection from './CollapseSection.vue'
import { t } from '../i18n'

const store = useSimStore()

const group = computed(() => store.selectedGroup)
const members = computed(() => {
  if (!group.value) return []
  const ids = new Set(group.value.members || [])
  return (store.scheme.nodes || []).filter((n) => ids.has(n.id))
})
function estOf(id) { return store.schemeResult.nodes[id] }
// 当前检视器选中的节点（工序实例 / 设备 / 工艺节点），用于成员行高亮
const activeMember = computed(() => {
  if (store.selectedUnitId) return store.selectedUnitId
  if (store.deviceDetailId) return store.deviceDetailId
  if (store.selectedFlowId) return store.selectedFlowId
  return null
})
// 点击成员：与左侧工艺/设备列表行为一致——工序实例、设备均展示数值型面板，
// 而非编排模式下的属性面板（selectFlow）
function onMemberClick(m) {
  // 工艺节点 → 工序实例属性面板（与 3D 场景点击铭牌一致，id 即 model.units 实例 id）
  if (m.kind === 'process') { store.pickUnit(m.id); return }
  // 设备节点 → 设备详情面板（linkedAuxDeviceOf 解析为「工序id::设备类型」的设备实例 id）
  if (m.kind === 'device') {
    const devId = store.linkedAuxDeviceOf(m.type)
    if (devId) { store.openDeviceDetail(devId); return }
    store.selectFlow(m.id)
    return
  }
  store.selectFlow(m.id)
}
const totals = computed(() => {
  const ms = members.value
  let co2 = 0, energy = 0, outMass = 0
  for (const m of ms) {
    const r = estOf(m.id)
    if (!r) continue
    co2 += r.co2 || 0
    energy += r.energy || 0
    outMass += r.outMass || 0
  }
  return { co2, energy, outMass, intensity: outMass > 0 ? (co2 / outMass) * 1000 : null }
})
function nodeSub(n) {
  if (n.kind === 'material') return t('原料/产物源')
  if (n.kind === 'device') return n.metering ? t('计量·只读') : t('可调·设定')
  return (PROCESS_MAP[n.type] && PROCESS_MAP[n.type].label) || n.type
}
function fmt(n) { return (n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })) }
</script>

<style scoped>
.group-detail { padding: 0 2px; }
</style>
