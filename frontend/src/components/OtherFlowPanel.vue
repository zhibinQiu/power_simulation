<template>
  <div class="ofp">
    <!-- ===== 小组（双击进入子编排前的一层，点击成员可选中） ===== -->
    <div v-if="group">
      <CollapseSection :title="t('工艺设备小组')" tone="blue">
        <div class="card">
          <div class="kv2"><span>{{ t('名称') }}</span><b>{{ group.name }}</b></div>
          <div class="kv2"><span>{{ t('成员设备') }}</span><b>{{ group.members.length }} {{ t('台') }}</b></div>
        </div>
      </CollapseSection>
      <CollapseSection :title="t('成员设备（点击查看/编辑）')" tone="teal" :show-more="false">
        <div v-for="m in groupMembers" :key="m.id" class="lrow click" :class="{ active: m.id === store.selectedFlowId }" @click="store.selectFlow(m.id)">
          <div class="l-stack">
            <span class="l-tt">{{ m.name }}</span>
            <span class="l-sub">{{ nodeSub(m) }}</span>
          </div>
        </div>
        <div v-if="!groupMembers.length" class="empty">{{ t('该小组暂无成员。') }}</div>
      </CollapseSection>
      <div class="pr-hint">{{ t('在画布中双击小组卡片可进入子编排。') }}</div>
    </div>

    <!-- ===== 未选中：编排方案总览 ===== -->
    <div v-else-if="!node">
      <CollapseSection :title="t('编排方案总览')" tone="blue" :show-more="false">
        <div class="chips">
          <div class="chip2"><span>{{ t('总功耗') }}</span><b>{{ fmt(totals.energy / 1000, 3) }}</b><i>MW</i></div>
          <div class="chip2"><span>{{ t('总碳排') }}</span><b>{{ fmt(totals.carbon) }}</b><i>kgCO₂/h</i></div>
          <div class="chip2"><span>{{ t('折碳总量') }}</span><b>{{ fmt(totals.carbon / 1000, 3) }}</b><i>tCO₂/h</i></div>
        </div>
        <div class="pr-hint">{{ methodHint }}</div>
      </CollapseSection>

      <CollapseSection v-if="store.scheme.groups.length" :title="t('工艺设备小组（点击查看成员）')" tone="teal" :show-more="false">
        <div v-for="g in store.scheme.groups" :key="g.id" class="lrow click" :class="{ active: g.id === store.selectedGroupId }" @click="store.selectFlowGroup(g.id)">
          <div class="l-stack">
            <span class="l-tt">▦ {{ g.name }}</span>
            <span class="l-sub">{{ g.members.length }} {{ t('台设备') }}</span>
          </div>
        </div>
      </CollapseSection>

      <CollapseSection :title="t('节点清单（点击查看/编辑）')" tone="amber" :show-more="false">
        <div v-for="n in store.scheme.nodes" :key="n.id" class="lrow click" :class="{ active: n.id === store.selectedFlowId }" @click="store.selectFlow(n.id)">
          <div class="l-stack">
            <span class="l-tt">{{ n.name }}</span>
            <span class="l-sub">{{ nodeSub(n) }}</span>
          </div>
          <span v-if="n.kind === 'process'" class="l-trail">{{ fmt(carbonOf(n.id) / 1000, 3) }} <span class="u">tCO₂/h</span></span>
        </div>
        <div v-if="!store.scheme.nodes.length" class="empty">{{ t('画布为空，请从左侧拖入节点或载入模板。') }}</div>
      </CollapseSection>
    </div>

    <!-- ===== 工艺节点：属性 + 参数设定（资源包字典渲染，编辑即生效） ===== -->
    <div v-else-if="node.kind === 'process'">
      <CollapseSection :title="t('工序 · ') + (procDef ? procDef.name : typeNameOf(node.type))" tone="blue">
        <div class="card">
          <div class="kv2"><span>{{ t('名称') }}</span><b>{{ node.name }}</b></div>
          <div class="kv2"><span>{{ t('类型') }}</span><b>{{ procDef ? procDef.name : node.type }}</b></div>
          <div class="kv2" v-if="mainOutName"><span>{{ t('主产物') }}</span><b>{{ mainOutName }}</b></div>
          <div class="kv2" v-if="procDesc">
            <span>{{ t('说明') }}</span>
            <b class="ofp-desc">{{ procDesc }}</b>
          </div>
        </div>
      </CollapseSection>

      <!-- 运行指标：随参数编辑即时联动（功率 × 电网因子） -->
      <CollapseSection :title="t('运行指标 · 折碳核算')" tone="blue" :open="true">
        <div class="chips">
          <div class="chip2"><span>{{ t('设定功率') }}</span><b>{{ fmt(powerMW) }}</b><i>MW</i></div>
          <div class="chip2"><span>{{ t('实时功耗') }}</span><b>{{ fmt(powerMW * 1000) }}</b><i>kW</i></div>
          <div class="chip2"><span>{{ t('实时碳排') }}</span><b>{{ fmt(carbonKgH, 3) }}</b><i>kgCO₂/h</i></div>
        </div>
        <div class="kv2"><span>{{ t('折碳总量') }}</span><b>{{ fmt(carbonKgH / 1000, 4) }} <span class="u">tCO₂/h</span></b></div>
        <div class="pr-hint">{{ methodNote }}</div>
      </CollapseSection>

      <!-- 工艺参数设定（可编辑：功率等参数改动立即反映到上方折碳） -->
      <CollapseSection :title="t('工艺参数设定')" tone="amber" :show-more="false">
        <div class="card">
          <div v-for="p in paramDefs" :key="p.key" class="param-row">
            <div class="pr-top">
              <span>{{ p.label }}</span>
              <span class="pr-val-wrap"><b>{{ node.params[p.key] ?? p.def }} <span class="u">{{ p.unit }}</span></b></span>
            </div>
            <input type="number" :min="p.min" :max="p.max" :step="p.step" :value="node.params[p.key] ?? p.def" class="num"
                   @input="store.setFlowParam(node.id, p.key, $event.target.value)" />
            <div class="pr-hint">{{ t('范围') }} {{ p.min }} – {{ p.max }} {{ p.unit }}</div>
          </div>
          <div v-if="!paramDefs.length" class="pr-hint">{{ t('该工艺无参数设定项。') }}</div>
          <div class="pr-hint ofp-tip">{{ t('参数修改立即应用（折碳随之更新）；完成后在工具条「应用编排」生效到孪生视图。') }}</div>
        </div>
      </CollapseSection>

      <!-- 输入 / 输出物料（资源包模板固定，端口中文名） -->
      <CollapseSection v-if="ioRows.length" :title="t('输入 / 输出')" tone="green" :show-more="false">
        <div class="card">
          <div class="ports-col">
            <span class="pc-t">{{ t('输入') }}</span>
            <div v-for="m in ioRows.in" :key="m.id" class="pc">
              <span class="pc-dot"></span>{{ m.name }}<span class="u">（{{ m.cat || t('上游来料') }}）</span>
            </div>
            <div v-if="!ioRows.in.length" class="pr-hint">{{ t('无输入（源头工序）') }}</div>
          </div>
          <div class="ports-col">
            <span class="pc-t">{{ t('输出') }}</span>
            <div v-for="m in ioRows.out" :key="m.id" class="pc">
              <span class="pc-dot out"></span>{{ m.name }}
              <span class="u">（{{ m.id === mainOutId ? t('主产物') : (m.cat || t('下游产物')) }}）</span>
            </div>
            <div v-if="!ioRows.out.length" class="pr-hint">{{ t('无输出（末端工序）') }}</div>
          </div>
        </div>
      </CollapseSection>

      <!-- 附加传感 / 可变设备 -->
      <CollapseSection :title="t('附加传感 / 可变设备')" tone="blue" :show-more="false">
        <div class="card">
          <div v-for="ag in attachGroups" :key="ag.kind" class="ports-col">
            <span class="pc-t">{{ ag.label }}（{{ t('已绑') }} {{ attachedOf(ag.kind).length }}）</span>
            <div v-for="att in attachedOf(ag.kind)" :key="att.uid" class="gio-row att-row">
              <span class="att-lbl" :title="t('数值来源：') + srcTextOf(att)">{{ att.label }}</span>
              <select class="att-src" :value="srcOf(att)" @change="onAttSrc(att, $event.target.value)">
                <option value="sim">{{ t('模拟数据（缓变）') }}</option>
                <option value="fixed">{{ t('固定值（模板默认）') }}</option>
                <optgroup :label="t('工艺参数')">
                  <option v-for="o in paramOpts" :key="'p' + o.param" :value="'param::' + o.param">{{ o.label }}</option>
                </optgroup>
              </select>
              <button class="x-btn danger" :title="t('解除绑定')" @click="store.removeAttachFromNode(node.id, att.uid)">✕</button>
            </div>
            <div class="att-add-row">
              <select class="att-add" value="" @change="onAddAttach(ag.kind, $event.target.value)">
                <option value="" disabled>＋ {{ t('添加') }} {{ ag.label }}…</option>
                <option v-for="it in ag.items" :key="it.type" :value="it.type">{{ it.label }}{{ ag.unitOf(it) ? '（' + ag.unitOf(it) + '）' : '' }}</option>
              </select>
            </div>
          </div>
        </div>
      </CollapseSection>

      <button class="del-node" @click="store.removeFlowNode(node.id)">{{ t('删除该工序节点') }}</button>
    </div>

    <!-- ===== 设备节点 ===== -->
    <div v-else-if="node.kind === 'device'">
      <CollapseSection :title="node.metering ? t('计量设备（只读）') : t('可调设备')" tone="blue" :show-more="false">
        <div class="card">
          <div class="kv2"><span>{{ t('名称') }}</span><b>{{ node.name }}</b></div>
          <div class="kv2"><span>{{ t('类别') }}</span><b>{{ node.metering ? t('计量·监测') : t('可调·控制') }}</b></div>
          <div class="kv2"><span>{{ t('量纲') }}</span><b>{{ devMeasureText }}</b></div>
          <div class="kv2"><span>{{ t('数量（台）') }}</span>
            <input type="number" min="1" max="9" step="1" class="spec-sel" :value="node.count || 1"
                   @change="store.setFlowCount(node.id, $event.target.value)" />
          </div>
          <div v-if="!node.metering" class="param-row">
            <div class="pr-top"><span>{{ t('设定值') }}</span><b>{{ node.setpoint }} <span class="u">{{ setpointUnit }}</span></b></div>
            <input type="number" :step="node.range?.step || 1" class="num" :value="node.setpoint"
                   @input="store.setDeviceSetpoint(node.id, $event.target.value)" />
          </div>
        </div>
      </CollapseSection>
      <button class="del-node" @click="store.removeFlowNode(node.id)">{{ t('删除该设备节点') }}</button>
    </div>

    <!-- ===== 其它（原料源等，钢铁场景专属概念） ===== -->
    <div v-else>
      <CollapseSection :title="t('节点属性')" tone="blue" :show-more="false">
        <div class="card">
          <div class="kv2"><span>{{ t('名称') }}</span><b>{{ node.name || node.type }}</b></div>
        </div>
      </CollapseSection>
      <div class="pr-hint">{{ t('该节点类型为本行业资源包未定义项，属性不可编辑。') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'
import CollapseSection from './CollapseSection.vue'
import { ATTACH_GROUPS } from '../data/attachLibrary'

const store = useSimStore()

const node = computed(() => store.selectedFlowNode)
const group = computed(() => store.selectedGroup)
const dict = computed(() => store.sceneCtx || null)

const fmt = (v, d = 1) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d))
const groupMembers = computed(() => {
  if (!group.value) return []
  const ids = new Set(group.value.members || [])
  return store.scheme.nodes.filter((n) => ids.has(n.id))
})

// ---- 总览 ----
const totals = computed(() => {
  const b = store.baseline?.totals || {}
  return { carbon: Number(b.carbon) || 0, energy: Number(b.energy) || 0 }
})
const methodHint = computed(() => {
  const m = dict.value?.method
  return m ? m.name + '。' + m.note : t('非钢场景为本地静态核算：总功耗 × 电网排放因子 → 范围二碳排。')
})
const carbonOf = (id) => {
  const u = (store.baseline?.units || []).find((x) => x.id === id)
  return u && isFinite(u.carbon) ? u.carbon : 0
}

// ---- 字典映射 ----
const procDef = computed(() => {
  const u = node.value
  if (!u || !dict.value?.processes) return null
  return dict.value.processes.find((p) => p.type === u.type) || null
})
const typeNameOf = (type) => {
  const d = dict.value?.processes?.find((p) => p.type === type)
  return d ? d.name : type
}
const procDesc = computed(() => procDef.value?.desc || '')
const nodeSub = (n) => {
  if (n.kind === 'device') return n.metering ? t('计量·只读') : t('可调·设定')
  if (n.kind === 'material') return t('原料/产物源')
  return typeNameOf(n.type)
}
const matOf = (id) => (dict.value?.materials || []).find((m) => m.id === id) || null
const matName = (id) => {
  const m = matOf(id)
  return m ? m.name : (id || '—')
}
const mainOutId = computed(() => procDef.value?.mainOut || (node.value && node.value.ports?.out?.[0]?.material) || null)
const mainOutName = computed(() => (mainOutId.value ? matName(mainOutId.value) : ''))
const ioRows = computed(() => {
  const n = node.value
  if (!n?.ports) return { in: [], out: [] }
  const map = (p) => {
    const mid = p.material
    const m = matOf(mid)
    return { id: mid, name: m ? m.name : mid, cat: m ? m.cat : '' }
  }
  return {
    in: (Array.isArray(n.ports.in) ? n.ports.in : []).map(map).filter((x) => x.id),
    out: (Array.isArray(n.ports.out) ? n.ports.out : []).map(map).filter((x) => x.id),
  }
})

// ---- 运行指标（本地即时联动：功率 × 电网因子） ----
const powerMW = computed(() => {
  const def = procDef.value?.params?.find((p) => p.key === 'power')?.def ?? 0
  return Number(node.value?.params?.power ?? def) || 0
})
const carbonKgH = computed(() => powerMW.value * 1000 * store._gridFactorKg())
const methodNote = computed(() => {
  const m = dict.value?.method
  return m ? `${m.name}。${m.note}` : t('实时碳排 ≈ 功率(kW) × 电网排放因子(kgCO₂/kWh)。')
})

// ---- 参数设定（按包字典渲染，可编辑） ----
const paramDefs = computed(() => {
  const n = node.value
  if (!n) return []
  const defs = procDef.value?.params || []
  if (defs.length) return defs
  // 字典缺失时的回退：直接把节点上已有参数键渲染为可编辑行
  return Object.keys(n.params || {}).map((k) => ({
    key: k,
    label: k === 'power' ? t('功率') : k,
    unit: '',
    min: 0,
    max: 9999,
    step: 0.01,
    def: n.params[k],
  }))
})

// ---- 附加传感 / 可变设备 ----
const attachGroups = ATTACH_GROUPS.map((g) => ({
  kind: g.key,
  label: g.label,
  items: g.items,
  unitOf: (it) => (g.key === 'sensor' ? (it.measure ? it.measure.unit : '') : (it.setpoint ? it.setpoint.unit : '')),
}))
const attachedOf = (kind) => (node.value ? (node.value.attached || []).filter((a) => a.kind === kind) : [])
const paramOpts = computed(() => {
  if (!node.value) return []
  return store.attachSourceOptions(node.value.id).filter((o) => o.value === 'param')
})
const srcOf = (att) => (att.src === 'param' ? 'param::' + (att.param || '') : att.src || 'fixed')
function srcTextOf(att) {
  if (att.src === 'param') {
    const o = paramOpts.value.find((x) => x.param === att.param)
    return o ? o.label : att.param
  }
  return t(att.src === 'sim' ? '模拟数据（缓变）' : '固定值（模板默认）')
}
function onAddAttach(kind, type) {
  if (!type || !node.value) return
  const att = store.addAttachToNode(node.value.id, kind, type)
  if (att) store.toast = t('已为工艺「{name}」绑定「{label}」：数值来源默认模拟数据，可下拉切换为工艺参数 / 固定值', { name: node.value.name, label: att.label })
}
function onAttSrc(att, v) {
  if (!node.value) return
  if (v.indexOf('param::') === 0) store.setAttachSource(node.value.id, att.uid, { src: 'param', param: v.slice(7) })
  else store.setAttachSource(node.value.id, att.uid, { src: v })
}

// ---- 设备 ----
const devMeasureText = computed(() => {
  const u = node.value
  if (u && u.measure) return (u.measure.name || '') + (u.measure.unit ? '（' + u.measure.unit + '）' : '')
  return '—'
})
const setpointUnit = computed(() => node.value?.range?.unit || '')
</script>

<style scoped>
.ofp { display: flex; flex-direction: column; }
.ofp-desc { font-weight: 400; font-size: 11px; color: var(--muted); line-height: 1.6; text-align: right; }
.ofp-tip { color: var(--accent-d); }
.lrow { display: flex; align-items: center; gap: 8px; padding: 7px 2px; font-size: 12px; cursor: pointer; }
.lrow + .lrow { border-top: 1px solid var(--line); }
.lrow.click:hover { color: var(--accent-d); }
.lrow.active { color: var(--accent-d); }
.l-stack { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.l-tt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.l-sub { font-size: 10.5px; color: var(--muted); }
.l-trail { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.u { font-size: 10px; color: var(--muted); font-style: normal; }
.empty { font-size: 11px; color: var(--muted); padding: 8px 0; }
.card { }
.ports-col { display: block; width: 100%; }
.ports-col + .ports-col { margin-top: 10px; }
.pc-t { font-size: 10px; color: var(--accent2); font-weight: 400; display: block; margin-bottom: 4px; }
.pc { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text); padding: 3px 0; }
.pc + .pc { border-top: 1px solid var(--line); }
.pc-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green, #4f9d6b); flex: 0 0 auto; }
.pc-dot.out { background: var(--accent2); }
.param-row { margin-bottom: 8px; }
.param-row:last-child { margin-bottom: 0; }
.pr-top { display: flex; justify-content: space-between; align-items: baseline; font-size: 11.5px; margin-bottom: 4px; }
.pr-top b { color: var(--text); font-weight: 400; font-variant-numeric: tabular-nums; }
.pr-val-wrap { display: inline-flex; align-items: center; gap: 6px; }
.num { width: 100%; }
.gio-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.att-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.att-lbl { flex: 1; min-width: 0; font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-src, .att-add { flex: 1; min-width: 0; font-size: 11px; padding: 3px 4px; border: 1px solid var(--line); border-radius: 2px; background: var(--panel); color: var(--text); }
.att-add-row { display: flex; margin-top: 2px; }
.del-node { margin-top: 10px; width: 100%; padding: 6px; font-size: 11.5px; color: #c0453c; background: transparent; border: 1px dashed rgba(192, 69, 60, 0.55); border-radius: 4px; cursor: pointer; }
.del-node:hover { background: rgba(192, 69, 60, 0.08); }
</style>
