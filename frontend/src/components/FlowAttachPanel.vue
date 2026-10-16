<template>
  <!-- ===== 工艺下的三类附加设备：传感器 / 可变设备 / 非可调设备 =====
       所有场景共用同一实现（编排属性面板一致，场景无特殊性）：
       把设备挂到当前工艺节点上，并为每个设备指定「数值来源」——数据源实测值
       （列出当前数据源中的全部设备，一个设备上报多个值时逐值列出）、固定值（手动设定）或工艺参数。 -->
  <CollapseSection :title="t('工艺设备绑定 · 传感器 / 可变设备 / 非可调设备')" tone="blue" :show-more="false">
    <div class="card">
      <div class="pr-hint">{{ t('把传感器 / 可变设备 / 非可调设备挂到本工序下（数据绑定方向：工序 ← 设备）。每个设备可设「数值来源」：数据源实测值 / 固定值（手动设定）/ 工艺参数；数据源中一个设备上报多个数值时逐条列出，可逐值绑定。运行态出现在设备树与数据分析中。') }}</div>
      <div v-if="!dsOptGroups.length" class="pr-hint att-empty">
        {{ t('当前数据源暂无上报数据：请确认数据源已启用且有设备在上报（能碳一体机管理 → 数据源接入）。') }}
        <template v-if="dsSourceNames.length">{{ t('已登记数据源：') }}{{ dsSourceNames.join('、') }}</template>
      </div>
      <div v-for="ag in attachGroups" :key="ag.kind" class="ports-col">
        <span class="pc-t">{{ t(ag.label) }}（{{ t('已绑') }} {{ attachedOf(ag.kind).length }}）</span>
        <div v-for="att in attachedOf(ag.kind)" :key="att.uid" class="gio-row att-row">
          <span class="att-lbl" :title="t('数值来源：') + srcTextOf(att)">{{ att.label }}</span>
          <select class="att-src" :value="srcOf(att)" @change="onAttSrc(att, $event.target.value)">
            <option value="fixed">{{ t('固定值（手动设定）') }}</option>
            <optgroup v-for="g in dsOptGroups" :key="g.id" :label="g.label">
              <option v-for="o in g.options" :key="'d' + o.key" :value="'ds::' + o.key">{{ o.label }}</option>
            </optgroup>
            <option v-if="isLostDs(att)" :value="srcOf(att)">{{ (dsOptOf(att) || {}).label || srcTextOf(att) }}</option>
            <optgroup :label="t('工艺参数')">
              <option v-for="o in paramOpts" :key="'p' + o.param" :value="'param::' + o.param">{{ o.label }}</option>
            </optgroup>
          </select>
          <input v-if="srcOf(att) === 'fixed'" type="number" class="att-fix" :value="fixedValOf(att)"
                 :title="t('固定值：手动设定该设备的读数')" @change="onFixVal(att, $event.target.value)" />
          <button class="x-btn danger" :title="t('解除绑定')" @click="store.removeAttachFromNode(node.id, att.uid)">✕</button>
        </div>
        <div v-if="!attachedOf(ag.kind).length" class="pr-hint att-empty">{{ t('未绑定：下方选择模板添加，或在左侧资源管理「传感器 / 可变设备 / 非可调设备」目录中点击条目直接绑定') }}</div>
        <div class="att-add-row">
          <select class="att-add" :value="''" @change="onAddAttach(ag.kind, $event.target.value)">
            <option value="" disabled>＋ {{ t('添加') }} {{ t(ag.label) }}…</option>
            <option v-for="it in ag.items" :key="it.type" :value="it.type">{{ it.label }}{{ ag.unitOf(it) ? '（' + ag.unitOf(it) + '）' : '' }}</option>
          </select>
        </div>
      </div>
    </div>
  </CollapseSection>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { ATTACH_GROUPS, attachUnit, attachDef, ATTACH_MAP } from '../data/attachLibrary'
import CollapseSection from './CollapseSection.vue'
import { t } from '../i18n'

const store = useSimStore()
const node = computed(() => store.selectedFlowNode)

// 已登记的数据源名（目录条目），用于空态提示：即使暂无上报数据也能看到接入了哪些源
const dsSourceNames = computed(() => (store.dsSignals || []).map((s) => s.name || s.id))

// 三类附加设备（所有场景一致）：传感器 / 可变设备 / 非可调设备
const attachGroups = ATTACH_GROUPS.map((g) => ({
  kind: g.key,
  label: g.label,
  items: g.items,
  unitOf: (it) => attachUnit(it) || '',
}))
const attachedOf = (kind) => (node.value ? (node.value.attached || []).filter((a) => a.kind === kind) : [])

// 工艺参数选项（数值来源之一）
const paramOpts = computed(() => {
  if (!node.value) return []
  return store.attachSourceOptions(node.value.id).filter((o) => o.value === 'param')
})

// 数据源实测值候选：按「数据源／设备」分组，每个数值（field）一条选项
// （一台传感器/设备可能上报多个值，此处全部列出，逐值绑定）
const dsOptGroups = computed(() => {
  const out = []
  for (const s of (store.dsSignals || [])) {
    for (const d of (s.devices || [])) {
      const vals = (d.values || []).filter((v) => v && v.key)
      if (!vals.length) continue
      out.push({
        id: `${s.id}::${d.id}`,
        label: `${s.name || s.id}／${d.id}${s.enabled === false ? `（${t('已停用')}）` : ''}`,
        // 选项只显示指标名（不显示实时数值：列表用于选择绑定哪个指标，读数在运行态展示）
        options: vals.map((v) => ({
          key: v.key,
          label: `${v.field}`,
          ds: { source: s.id, sourceName: s.name || s.id, device: d.id, box: d.box || '', field: v.field, key: v.key },
        })),
      })
    }
  }
  return out
})
// 已绑定信号若已不在目录中（设备停报 / 源已删除），保留一项占位避免下拉错选
function dsOptOf(att) {
  if (!att.ds || !att.ds.key) return null
  for (const g of dsOptGroups.value) {
    const o = g.options.find((x) => x.key === att.ds.key)
    if (o) return o
  }
  return { key: att.ds.key, label: `${att.ds.device} · ${att.ds.field}（${t('已失联')}）`, ds: att.ds }
}
const isLostDs = (att) => att.src === 'ds'
  && !dsOptGroups.value.some((g) => g.options.some((o) => o.key === (att.ds && att.ds.key)))
const srcOf = (att) => {
  if (att.src === 'ds') return 'ds::' + ((att.ds && att.ds.key) || '')
  // 历史版本曾有 sim（平台自产模拟）来源：已取消，统一按固定值回显
  return att.src === 'param' ? 'param::' + (att.param || '') : 'fixed'
}
// 固定值（手动设定）：显示用户设定值，未设定时回显模板默认，可直接修改
function fixedValOf(att) {
  if (att.def != null) return att.def
  const tpl = (ATTACH_MAP[att.kind] || {})[att.type]
  return tpl ? attachDef(tpl) : 0
}
function onFixVal(att, v) {
  if (!node.value) return
  const n = Number(v)
  if (isNaN(n)) return
  store.setAttachSource(node.value.id, att.uid, { def: n })
}
function srcTextOf(att) {
  if (att.src === 'ds') {
    const d = att.ds || {}
    return `${d.sourceName || d.source || t('数据源')}／${d.device || '?'} · ${d.field || '?'}`
  }
  if (att.src === 'param') {
    const o = paramOpts.value.find((x) => x.param === att.param)
    return o ? o.label : att.param
  }
  return t('固定值（手动设定）') + `：${fixedValOf(att)}`
}
// 添加：把模板实例挂到当前工艺节点下
function onAddAttach(kind, type) {
  if (!type || !node.value) return
  const att = store.addAttachToNode(node.value.id, kind, type)
  if (att) store.toast = t('已为工艺「{name}」绑定「{label}」：数值来源默认固定值（可手动设定），可下拉切换为数据源实测值 / 工艺参数', { name: node.value.name, label: att.label })
}
// 下拉切换数值来源（ds::key / param::key / fixed）
function onAttSrc(att, v) {
  if (!node.value) return
  if (v.indexOf('param::') === 0) store.setAttachSource(node.value.id, att.uid, { src: 'param', param: v.slice(7) })
  else if (v.indexOf('ds::') === 0) {
    const key = v.slice(4)
    let ds = att.ds && att.ds.key === key ? att.ds : null
    if (!ds) {
      for (const g of dsOptGroups.value) {
        const o = g.options.find((x) => x.key === key)
        if (o) { ds = o.ds; break }
      }
    }
    if (!ds) return
    store.setAttachSource(node.value.id, att.uid, { src: 'ds', ds })
    store.toast = t('已绑定数据源实测值：{dev} · {field}', { dev: ds.device, field: ds.field })
  } else store.setAttachSource(node.value.id, att.uid, { src: v })
}
</script>

<style scoped>
.ports-col { display: block; width: 100%; }
.ports-col + .ports-col { margin-top: 10px; }
.pc-t { font-size: var(--fs-2xs); color: var(--accent2); font-weight: 400; display: block; margin-bottom: 4px; }
.gio-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.att-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.att-lbl { flex: 1; min-width: 0; font-size: var(--fs-xs); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-src, .att-add { flex: 1; min-width: 0; font-size: var(--fs-xs); padding: 3px 4px; border: 1px solid var(--border); border-radius: 2px; background: var(--panel); color: var(--text); }
.att-fix { width: 74px; flex: 0 0 auto; font-size: var(--fs-xs); padding: 3px 4px; border: 1px solid var(--border); border-radius: 2px; background: var(--panel); color: var(--text); font-variant-numeric: tabular-nums; }
.att-empty { font-size: var(--fs-xs); color: var(--muted); padding: 2px 0 6px; }
.att-add-row { display: flex; margin-top: 2px; }
</style>
