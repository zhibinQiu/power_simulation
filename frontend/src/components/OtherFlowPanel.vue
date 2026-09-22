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

      <!-- 运行指标：随参数编辑即时联动（功率 × 电网因子）；功率口径与实时折碳一致（实测功率优先） -->
      <CollapseSection :title="t('运行指标 · 折碳核算')" tone="blue" :open="true">
        <div class="chips">
          <div class="chip2"><span>{{ t('设定功率') }}</span><b>{{ fmt(packKwNow / 1000, 3) }}</b><i>MW</i></div>
          <div class="chip2"><span>{{ t('实时功耗') }}</span><b>{{ fmt(powerKwNow) }}</b><i>kW</i></div>
          <div class="chip2"><span>{{ t('实时碳排') }}</span><b>{{ fmt(carbonKgH, 3) }}</b><i>kgCO₂/h</i></div>
        </div>
        <div class="kv2"><span>{{ t('折碳总量') }}</span><b>{{ fmt(carbonKgH / 1000, 4) }} <span class="u">tCO₂/h</span></b></div>
        <div class="kv2"><span>{{ t('功率口径') }}</span><b>{{ powerSrcText }}</b></div>
        <div v-for="s in powerSources" :key="s.id" class="kv2">
          <span>{{ s.label }}<i class="u">{{ s.device ? ' · ' + s.device + (s.prop ? ' · ' + s.prop : '') : ' · ' + t(s.src === 'sim' ? '随机模拟值' : (s.src === 'device' ? '数据源管理设备' : '固定值')) }}</i></span>
          <b>{{ fmt(s.measured) }} <span class="u">kW</span></b>
        </div>
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
              <span class="att-lbl" :title="att.kind === 'sensor' ? (t('数据源：') + srcTextOf(att)) : t('设定值：只调运行工况，不参与取数')">{{ att.label }}</span>
              <!-- 传感器：当前读数 + 功率型标记（功率型 = 本工序折碳的功率来源）；
                   可变设备不取数——它的值就是设定值 -->
              <span v-if="att.kind === 'sensor'" class="att-rd" :title="t('当前读数（数据源：{src}）', { src: srcTextOf(att) })">
                <b>{{ fmt(sensorValOf(att)) }}</b> {{ attUnitOf(att) }}
              </span>
              <span v-if="att.kind === 'sensor' && isPowerAtt(att)" class="att-kw"
                    :title="t('功率型传感器（kW）：其读数即本工序能碳核算的功率来源')">{{ t('折碳') }}</span>
              <template v-if="att.kind === 'adjustable'">
                <input class="att-sp" type="number" :min="spOf(att).min" :max="spOf(att).max" :step="spOf(att).step || 1"
                       :value="spShow(att)" @input="onAttSpInput(att, $event.target.value)" @change="onAttSetpoint(att, $event.target.value)"
                       :title="t('设定值（{label}）：只用于调节运行工况，不参与取数；本工序实际功率请在「传感器」中添加电功率传感器', { label: spOf(att).label })" />
                <span class="u">{{ spOf(att).unit }}</span>
                <input class="att-fx" type="number" step="0.01" :value="fxShow(att)" @input="onAttFxInput(att, $event.target.value)" @change="onAttFactor(att, $event.target.value)"
                       :title="t('换算系数：读数 = 源值 × 系数（系统单位与设备实际度量不一致时换算用，默认 1，最多两位小数）')" />
                <select class="att-src" :value="writeSrcOf(att)" @change="onAttWriteSrc(att, $event.target.value)"
                        :title="t('绑定数据源设备的可写点位：修改设定值时自动下发写入（仅列出具有可写权限的点位）')">
                  <option value="">{{ t('不绑定写点位') }}</option>
                  <optgroup v-for="g in boxWritableGroups" :key="g.name" :label="t('数据源设备') + ' · ' + g.name">
                    <option v-for="w in g.writes" :key="w.property" :value="'device::' + g.name + '::' + w.property">
                      {{ w.property }}{{ w.unit ? '（' + w.unit + '）' : '' }}
                    </option>
                  </optgroup>
                </select>
              </template>
              <select v-if="att.kind === 'sensor'" class="att-src" :value="srcOf(att)" @change="onAttSrc(att, $event.target.value)">
                <option value="fixed">{{ t('固定值') }}</option>
                <option value="sim">{{ t('随机模拟值') }}</option>
                <!-- 数据源管理（能碳一体机）中已接入的传感器设备：每台设备一个分组，组内为其点位 -->
                <optgroup v-for="g in boxSourceGroups" :key="g.name"
                          :label="t('数据源设备') + ' · ' + g.name + (g.model ? '（' + g.model + '）' : '')">
                  <option v-for="p in g.props" :key="p.name" :value="'device::' + g.name + '::' + p.name">
                    {{ p.name }}{{ p.unit ? '（' + p.unit + '）' : '' }}{{ p.value != null ? ' · ' + p.value : '' }}
                  </option>
                </optgroup>
                <option v-if="!boxSourceGroups.length" disabled>{{ t('暂无数据源设备') }}</option>
                <!-- 传感器可随同工序的附加可调设备联动（如变频器频率 → 流速，Q ∝ n） -->
                <optgroup v-if="att.kind === 'sensor' && attachedOf('adjustable').length"
                          :label="t('随附加可调设备联动')">
                  <option v-for="rk in attachedOf('adjustable')" :key="'lk' + rk.uid" :value="'attach::' + rk.uid">
                    {{ t('随「{name}」变化', { name: rk.label }) }}
                  </option>
                </optgroup>
                <optgroup v-if="att.src === 'param'" :label="t('工艺参数')">
                  <option v-for="o in paramOpts" :key="'p' + o.param" :value="'param::' + o.param">{{ o.label }}</option>
                </optgroup>
              </select>
              <input v-if="att.kind === 'sensor'" class="att-fx" type="number" step="0.01" :value="fxShow(att)" @input="onAttFxInput(att, $event.target.value)" @change="onAttFactor(att, $event.target.value)"
                     :title="t('换算系数：读数 = 源值 × 系数（系统单位与传感器实际度量不一致时换算用，默认 1，最多两位小数）')" />
              <span v-if="att.src === 'attach'" class="u" :title="t('联动换算：读数 = 设定值 × 读数锚点 / 设定值锚点，绑定瞬间读数保持不变')">{{ linkTextOf(att) }}</span>
              <button v-if="att.src === 'attach'" class="x-btn" :title="t('按当前设定值 / 读数重新标定联动锚点')"
                      @click="store.setAttachLinkScale(node.id, att.uid, linkRefSpOf(att), att.def)">⟲</button>
              <button class="x-btn danger" :title="t('解除绑定')" @click="store.removeAttachFromNode(node.id, att.uid)">✕</button>
            </div>
            <!-- 添加：按钮展开模板清单（语义明确，不用「未选择即为空」的下拉） -->
            <div class="att-add-row">
              <button class="att-add-btn" :class="{ on: addOpen === ag.kind }" @click="toggleAdd(ag.kind)">
                ＋ {{ ag.kind === 'sensor' ? t('添加传感') : t('添加可变设备') }}
              </button>
            </div>
            <div v-if="addOpen === ag.kind" class="att-pick">
              <div class="att-pick-hd">{{ t('选择{label}类型', { label: ag.label }) }}</div>
              <button v-for="it in ag.items" :key="it.type" class="att-pick-item" :title="it.desc"
                      @click="pickAttach(ag.kind, it.type)">
                <span class="api-tt">{{ it.label }}</span>
                <span class="api-u">{{ ag.unitOf(it) }}</span>
              </button>
            </div>
          </div>
          <div class="pr-hint">{{ t('能碳口径：本工序附加的「电功率传感器（kW）」的读数即折碳功率来源（可绑定数据源管理的采集设备点位取实测值，或设为随可变设备联动）；可变设备的设定值只调运行工况、不参与折碳。') }}</div>
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
import { computed, reactive, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'
import CollapseSection from './CollapseSection.vue'
import { ATTACH_GROUPS, ATTACH_MAP, attachUnit, attachPowerSensor } from '../data/attachLibrary'

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

// ---- 运行指标（功率 × 电网因子）：功率口径与实时折碳一致 ----
// 功率取自本工序附加的**功率型传感器**（电功率传感器的有功功率 kW）：数据源可为
// 数据源管理中的采集设备（实测）/ 随机模拟 / 固定值 / 随可变设备联动；
// 未添加功率传感器时回落包内工序功率参数（出厂设定）。
// 可变设备的设定值只调工况、不参与折碳。数值直接取 store.baseline.units（与 KPI / 孪生同源）。
const baseUnit = computed(() => (store.baseline?.units || []).find((x) => x.id === (node.value && node.value.id)) || null)
const powerMW = computed(() => {
  const def = procDef.value?.params?.find((p) => p.key === 'power')?.def ?? 0
  return Number(node.value?.params?.power ?? def) || 0
})
// 包内功率参数（MW → kW）：未接入实测时的估算口径
const packKwNow = computed(() => {
  const u = baseUnit.value
  if (u && isFinite(Number(u.packPowerKW))) return Number(u.packPowerKW)
  return powerMW.value * 1000
})
// 实际参与折碳的功率（kW）：实测/模拟附加可调设备功率优先
const powerKwNow = computed(() => {
  const u = baseUnit.value
  if (u && isFinite(Number(u.powerKW))) return Number(u.powerKW)
  return powerMW.value * 1000
})
const powerSources = computed(() => (baseUnit.value && Array.isArray(baseUnit.value.powerSources)) ? baseUnit.value.powerSources : [])
const powerSrcText = computed(() => {
  const u = baseUnit.value
  if (u && u.powerMeasured) return t('实测功率（数据源管理采集设备）')
  if (u && u.powerSimulated) return t('传感器读数（模拟 / 联动 / 固定来源，未接入实测）')
  return t('包内功率参数（未添加功率传感器）')
})
const carbonKgH = computed(() => {
  const u = baseUnit.value
  if (u && isFinite(Number(u.carbon))) return Number(u.carbon)
  return powerKwNow.value * store._gridFactorKg()
})
// 附加设备的当前读数：只有传感器取数（id = ext::节点::attUid，与设备树 / 详情面板同源）；
// 可变设备不取数——它的值就是设定值。
function sensorValOf(att) {
  if (!att || !node.value) return null
  const id = 'ext::' + node.value.id + '::' + att.uid
  const d = (store.allDevices || []).find((x) => x.id === id)
  if (!d) return att.def != null ? att.def : null
  return d.live != null ? d.live : d.reading
}
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
// 数据源下拉分组：数据源管理（能碳一体机）中已接入的传感器设备，组内为该设备的点位
const boxSourceGroups = computed(() => store.boxSourceGroups)
const paramOpts = computed(() => {
  if (!node.value) return []
  return store.attachSourceOptions(node.value.id).filter((o) => o.value === 'param')
})
const srcOf = (att) => {
  if (att.src === 'param') return 'param::' + (att.param || '')
  if (att.src === 'device') return 'device::' + (att.device || '') + '::' + (att.prop || '')
  if (att.src === 'attach') return 'attach::' + (att.devRef || '')
  return att.src || 'fixed'
}
// 联动源（同工序的附加可调设备）与联动锚点/说明
const linkRefOf = (att) => attachedOf('adjustable').find((a) => a.uid === att.devRef) || null
const attUnitOf = (att) => {
  const tpl = (ATTACH_MAP[att.kind] || {})[att.type]
  return tpl ? attachUnit(tpl) : ''
}
const attTplOf = (att) => (ATTACH_MAP[att.kind] || {})[att.type] || null
// 功率型传感器（kW）：其读数是本工序能碳核算的功率来源
const isPowerAtt = (att) => attachPowerSensor(attTplOf(att))
// 可变设备的设定值（只调工况，不取数）：store 设定优先，其次实例 def / 模板默认
const spOf = (att) => {
  const tpl = attTplOf(att)
  return (tpl && tpl.setpoint) ? tpl.setpoint : { label: t('设定值'), unit: '', min: 0, max: 100, step: 1, def: 0 }
}
function spValOf(att) {
  const id = node.value ? 'ext::' + node.value.id + '::' + att.uid : ''
  if (id && store.deviceSetpoints[id] != null) return Number(store.deviceSetpoints[id])
  const tpl = attTplOf(att)
  return Number(att.def != null ? att.def : (tpl && tpl.setpoint ? tpl.setpoint.def : 0))
}
// 数字输入草稿：编辑期间显示草稿值，避免遥测刷新（读数 1Hz）触发重渲染把正在输入/删除的内容
// 回冲成 store 值（表现为无法编辑删除）。@input 只更新草稿 + 本地预览（不写设备、不进历史），
// @change（失焦/回车）才正式提交：设定值此时才下发写点位，系数此时才进撤销历史。
const spDraft = reactive({})
const fxDraft = reactive({})
const spShow = (att) => (spDraft[att.uid] != null ? spDraft[att.uid] : spValOf(att))
function onAttSpInput(att, v) {
  if (!node.value) return
  spDraft[att.uid] = v
  const n = Number(v)
  if (v !== '' && isFinite(n)) store.setDeviceSetpoint('ext::' + node.value.id + '::' + att.uid, n)
}
function onAttSetpoint(att, v) {
  if (!node.value) return
  delete spDraft[att.uid]
  const n = Number(v)
  if (!isFinite(n)) return
  // 统一入口：本地设定；已绑定数据源设备可写点位时自动下发写入
  store.setExtSetpoint('ext::' + node.value.id + '::' + att.uid, n)
}
// 可变设备绑定数据源设备的可写点位（只列可写）：修改设定值时自动下发写设定
const boxWritableGroups = computed(() => store.boxWritableGroups)
const writeSrcOf = (att) => (att.src === 'device' && att.device ? 'device::' + att.device + '::' + (att.prop || '') : '')
function onAttWriteSrc(att, v) {
  if (!node.value) return
  if (v.indexOf('device::') === 0) {
    const rest = v.slice(8)
    const i = rest.indexOf('::')
    store.setAttachSource(node.value.id, att.uid, { src: 'device', device: rest.slice(0, i), prop: rest.slice(i + 2) })
  } else {
    store.setAttachSource(node.value.id, att.uid, { src: 'fixed', device: '', prop: '' })
  }
}
// 换算系数（默认 1）：读数 = 源值 × 系数，系统单位与设备实际度量不一致时换算用
const factorOf = (att) => (att.factor != null && isFinite(Number(att.factor)) ? Number(att.factor) : 1)
const fxShow = (att) => (fxDraft[att.uid] != null ? fxDraft[att.uid] : factorOf(att))
function onAttFxInput(att, v) {
  if (!node.value) return
  fxDraft[att.uid] = v
  const n = Number(v)
  if (v !== '' && isFinite(n)) store.setAttachFactor(node.value.id, att.uid, n, true)
}
function onAttFactor(att, v) {
  if (!node.value) return
  delete fxDraft[att.uid]
  store.setAttachFactor(node.value.id, att.uid, v)
}
// 添加面板：按钮展开 / 收起（切换工序节点时收起，避免残留展开态）
const addOpen = ref('')
function toggleAdd(kind) { addOpen.value = addOpen.value === kind ? '' : kind }
watch(node, () => { addOpen.value = '' })
function linkRefSpOf(att) {
  const ref = linkRefOf(att)
  if (!ref) return 0
  const id = 'ext::' + node.value.id + '::' + ref.uid
  if (store.deviceSetpoints[id] != null) return Number(store.deviceSetpoints[id])
  const rt = (ATTACH_MAP[ref.kind] || {})[ref.type]
  return Number(ref.def != null ? ref.def : (rt && rt.setpoint ? rt.setpoint.def : 0))
}
function linkTextOf(att) {
  const ref = linkRefOf(att)
  const s = att.scale || {}
  const ru = ref ? attUnitOf(ref) : ''
  return t('随「{name}」联动', { name: ref ? ref.label : '—' }) + '：' + (s.from != null ? s.from : '—') + ' ' + ru
    + ' → ' + (s.to != null ? s.to : '—') + ' ' + attUnitOf(att)
}
function srcTextOf(att) {
  if (att.src === 'param') {
    const o = paramOpts.value.find((x) => x.param === att.param)
    return o ? o.label : att.param
  }
  if (att.src === 'device') return (att.device || '—') + (att.prop ? ' · ' + att.prop : '')
  if (att.src === 'attach') return linkTextOf(att)
  return t(att.src === 'sim' ? '随机模拟值' : '固定值')
}
function onAddAttach(kind, type) {
  if (!type || !node.value) return
  const att = store.addAttachToNode(node.value.id, kind, type)
  if (!att) return
  store.toast = kind === 'sensor'
    ? t('已为工艺「{name}」添加传感「{label}」：数据源默认随机模拟值，可切换为固定值 / 数据源管理中的传感器设备 / 随可变设备联动', { name: node.value.name, label: att.label })
    : t('已为工艺「{name}」添加可变设备「{label}」：其数值为设定值（只调工况、不参与取数）；实际功率请在「传感器」中添加电功率传感器', { name: node.value.name, label: att.label })
}
// 从展开的模板清单中添加
function pickAttach(kind, type) {
  onAddAttach(kind, type)
  addOpen.value = ''
}
function onAttSrc(att, v) {
  if (!node.value) return
  if (v.indexOf('device::') === 0) {
    const rest = v.slice(8)
    const i = rest.indexOf('::')
    store.setAttachSource(node.value.id, att.uid, { src: 'device', device: rest.slice(0, i), prop: rest.slice(i + 2) })
    return
  }
  if (v.indexOf('param::') === 0) store.setAttachSource(node.value.id, att.uid, { src: 'param', param: v.slice(7) })
  else if (v.indexOf('attach::') === 0) store.setAttachSource(node.value.id, att.uid, { src: 'attach', devRef: v.slice(8) })
  else store.setAttachSource(node.value.id, att.uid, { src: v })
}
onMounted(() => store.startBoxSourcePolling())
onBeforeUnmount(() => store.stopBoxSourcePolling())

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
.att-lbl { flex: 1 1 56px; min-width: 0; font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-rd { flex: 0 0 auto; font-size: 10px; color: var(--accent-d); white-space: nowrap; }
.att-rd b { font-weight: 400; font-variant-numeric: tabular-nums; }
.att-kw { flex: 0 0 auto; font-size: 9.5px; color: #b26a00; border: 1px solid rgba(178,106,0,.45); border-radius: 2px; padding: 0 3px; }
.att-src { flex: 1 1 92px; min-width: 66px; font-size: 11px; padding: 3px 4px; border: 1px solid var(--line); border-radius: 2px; background: var(--panel); color: var(--text); }
.att-sp { flex: 0 0 auto; width: 64px; font-size: 11px; padding: 3px 4px; border: 1px solid var(--line); border-radius: 2px; background: var(--panel); color: var(--text); }
.att-fx { flex: 0 0 auto; width: 48px; font-size: 11px; padding: 3px 4px; border: 1px dashed var(--line); border-radius: 2px; background: var(--panel); color: var(--text); }
.att-add-row { display: flex; margin-top: 2px; }
/* 添加按钮 + 模板清单（替代原「未选择即为空」的下拉，语义明确：先点按钮再选型） */
.att-add-btn { flex: 1; font-size: 11px; padding: 4px 6px; cursor: pointer; color: var(--accent2);
  border: 1px dashed var(--accent2); background: transparent; border-radius: 2px; }
.att-add-btn:hover { background: rgba(95,130,148,.10); }
.att-add-btn.on { border-style: solid; background: rgba(95,130,148,.14); }
.att-pick { margin-top: 4px; border: 1px solid var(--line); border-radius: 2px; background: var(--panel-3); max-height: 190px; overflow: auto; }
.att-pick-hd { font-size: 10px; color: var(--muted); padding: 4px 6px; border-bottom: 1px solid var(--line); }
.att-pick-item { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%;
  font-size: 11px; padding: 4px 6px; cursor: pointer; color: var(--text); background: transparent; border: 0; text-align: left; }
.att-pick-item + .att-pick-item { border-top: 1px solid var(--line); }
.att-pick-item:hover { background: rgba(95,130,148,.14); color: var(--accent-d); }
.att-pick-item .api-u { font-size: 10px; color: var(--muted); }
.del-node { margin-top: 10px; width: 100%; padding: 6px; font-size: 11.5px; color: #c0453c; background: transparent; border: 1px dashed rgba(192, 69, 60, 0.55); border-radius: 4px; cursor: pointer; }
.del-node:hover { background: rgba(192, 69, 60, 0.08); }
</style>
