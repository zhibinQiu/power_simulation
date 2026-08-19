<template>
  <div class="mat-insp">
    <template v-if="mat">
      <CollapseSection :title="'物料属性 · ' + (mat ? mat.name : '')" tone="blue" :show-more="false">
      <p class="sec-desc">该类物料可作为原料或中间产物：在「编辑流程」中从左侧拖入画布生成源节点，再从输出端口连入工艺输入端口。</p>
      <div class="card">
        <div class="kv2"><span>类别</span><b>{{ mat.cat }}</b></div>
        <div class="kv2"><span>单位</span><b>{{ mat.unit }}</b></div>
      </div>
      </CollapseSection>

      <CollapseSection title="隐含碳因子" tone="amber" :show-more="false">
      <div class="card">
        <div class="param-row">
          <div class="pr-top"><span>当前值</span><b>{{ fmt(carbon) }} <span class="u">tCO₂/{{ mat.unit }}</span></b></div>
          <div class="num-row">
            <input type="number" class="num" min="0" max="5" step="0.001" :value="carbon" @input="onCarbon($event.target.value)" />
            <span class="num-unit">tCO₂/{{ mat.unit }}</span>
          </div>
          <div class="pr-hint">
            范围 0–5 tCO₂/{{ mat.unit }}；当前为 <b>{{ isOverride ? '会话覆盖值' : '库默认值' }}</b>，用于碳足迹核算与估算。
          </div>
        </div>
        <button v-if="isOverride" class="reset" @click="store.setMaterialCarbon(mat.id, mat.carbon)">恢复库默认值</button>
      </div>
      </CollapseSection>

      <CollapseSection v-if="fuelFactor" title="燃料排放因子 · NCV（低位发热量） / CC（单位热值含碳量）" tone="amber" :show-more="false">
      <div class="card">
        <div class="kv2">
          <span>NCV（低位发热量）</span>
          <span class="kv-edit">
            <input type="number" class="num" step="0.001" :value="fuelFactor.ncv" @change="onFuel('ncv', $event.target.value)" />
            <span class="num-unit">{{ fuelUnit }}</span>
          </span>
        </div>
        <div class="kv2">
          <span>CC（单位热值含碳量）</span>
          <span class="kv-edit">
            <input type="number" class="num" step="0.0004" :value="fuelFactor.cc" @change="onFuel('cc', $event.target.value)" />
            <span class="num-unit">tC/GJ</span>
          </span>
        </div>
        <div class="pr-hint">燃烧排放 = 用量 × NCV（低位发热量） × CC（单位热值含碳量） × 3.667；编辑后应用于全部仿真与 3D 孪生。</div>
      </div>
      </CollapseSection>

      <CollapseSection title="物理与物流参数" tone="teal" :show-more="false">
      <div class="card">
        <div class="kv2" v-for="a in attributeDefs" :key="a.key">
          <span>{{ a.label }}</span>
          <span class="kv-edit">
            <input type="number" class="num" :step="a.step" :value="attrVal(a.key, a.def)" @change="onAttr(a, $event.target.value)" />
            <span class="num-unit">{{ a.unit }}</span>
          </span>
        </div>
        <div class="kv2">
          <span>说明备注</span>
          <input class="num note-input" :value="attrVal('note', '')" @change="onNote($event.target.value)" placeholder="可选备注" />
        </div>
        <div class="pr-hint">以上为物料级自定义配置（本会话覆盖），用于台账与物流碳备注；不影响核心碳核算引擎。</div>
      </div>
      </CollapseSection>

      <CollapseSection title="相关工艺 · 输入 / 输出" tone="green" :show-more="false">
      <div class="card" v-if="usedIn.length">
        <div v-for="u in usedIn" :key="u.type" class="used-row">
          <span class="ur-name">{{ u.label }}</span>
          <span class="ur-tag" :class="u.role">{{ u.role === 'in' ? '输入' : '输出' }}</span>
        </div>
      </div>
      <div class="card note" v-else>暂无工艺引用该物料。</div>
      </CollapseSection>
    </template>
    <div v-else class="empty">未选择物料，请从左侧「原料」栏点击查看。</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'
import CollapseSection from './CollapseSection.vue'

const store = useSimStore()
const mat = computed(() => store.selectedMaterial)
const isOverride = computed(() => !!(store.materialOverrides && store.materialOverrides[mat.value.id]))
const carbon = computed(() => {
  const id = mat.value.id
  const ov = store.materialOverrides[id]
  return ov ? ov.carbon : mat.value.carbon
})
// 物料 id -> 后端燃料因子 key（factors.fuels）。仅燃料类物料有 NCV/CC。
const FUEL_KEY_BY_MAT = { coke: 'coke', coal: 'coal', ngas: 'ng' }
const fuelKey = computed(() => (mat.value ? FUEL_KEY_BY_MAT[mat.value.id] : null))
const fuelFactor = computed(() => {
  const k = fuelKey.value
  if (!k || !store.factors || !store.factors.fuels) return null
  return store.factors.fuels[k] || null
})
const fuelUnit = computed(() => {
  const f = fuelFactor.value
  if (!f) return ''
  return (f.unit === 'm3') ? 'GJ/万Nm³' : 'GJ/' + (f.unit || 't')
})
const usedIn = computed(() => {
  if (!mat.value) return []
  const id = mat.value.id
  const out = []
  for (const t of Object.values(PROCESS_MAP)) {
    if ((t.inputs || []).includes(id)) out.push({ type: t.type, label: t.label, role: 'in' })
    else if ((t.outputs || []).includes(id)) out.push({ type: t.type, label: t.label, role: 'out' })
  }
  return out
})
function onCarbon(v) { store.setMaterialCarbon(mat.value.id, v) }
function onFuel(field, v) { if (fuelKey.value) store.setFuelFactor(fuelKey.value, field, v) }
function fmt(n, d = 3) { return (n == null ? '—' : Number(n).toFixed(d)) }
const attributeDefs = [
  { key: 'density', label: '堆密度', unit: 'kg/m³', def: 1500, step: 10 },
  { key: 'transport_factor', label: '运输排放因子', unit: 'kgCO₂/t·km', def: 0.1, step: 0.01 },
  { key: 'moisture', label: '含水率', unit: '%', def: 0, step: 0.5 },
]
function attrVal(key, def) {
  const ov = store.materialOverrides[mat.value.id]
  const v = ov ? ov[key] : undefined
  return v != null ? v : (mat.value[key] != null ? mat.value[key] : def)
}
function onAttr(a, val) { store.setMaterialAttr(mat.value.id, a.key, Number(val)) }
function onNote(val) { store.setMaterialAttr(mat.value.id, 'note', val) }
</script>

<style scoped>
/* 模块内部说明：不单独成模块，直接写在对应模块内容区顶部 */
.sec-desc { font-size: 10.5px; line-height: 1.5; color: var(--muted); margin: 0 0 8px 0; padding: 0; }
.mat-insp { display: flex; flex-direction: column; }
.num { width: 96px; }
.num-row { margin-top: 6px; }
.note-input { width: auto; flex: 1; min-width: 0; }
.used-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; }
.used-row + .used-row { border-top: 1px solid var(--line); }
.ur-name { font-size: 11px; }
.ur-tag { font-size: 10px; padding: 1px 8px; border-radius: 3px; }
.ur-tag.in { color: var(--accent2); border: 1px solid rgba(95,130,148,.4); background: rgba(95,130,148,.10); }
.ur-tag.out { color: var(--green); border: 1px solid rgba(79,157,107,.4); background: rgba(79,157,107,.08); }
</style>
