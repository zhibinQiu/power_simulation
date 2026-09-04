<template>
  <div class="mat-insp">
    <template v-if="mat">
      <CollapseSection :title="t('物料属性 · ') + (mat ? mat.name : '')" tone="blue" :show-more="false">
      <p class="sec-desc">{{ t('该类物料可作为原料或中间产物：在「编辑流程」中从左侧拖入画布生成源节点，再从输出端口连入工艺输入端口。') }}</p>
      <div class="card">
        <div class="kv2"><span>{{ t('类别') }}</span><b>{{ mat.cat }}</b></div>
        <div class="kv2"><span>{{ t('单位') }}</span><b>{{ mat.unit }}</b></div>
      </div>
      </CollapseSection>

      <CollapseSection v-if="purchasable" :title="t('外购单价（全厂成本核算）')" tone="amber" :show-more="false">
      <div class="card">
        <div class="kv2">
          <span>{{ t('外购单价') }}</span>
          <span class="kv-edit">
            <input type="number" class="num" min="0" step="0.1" :value="price" @change="onPrice($event.target.value)" />
            <span class="num-unit">元/{{ mat.unit }}</span>
          </span>
        </div>
        <div class="pr-hint">{{ t('全厂总览「成本 = 外购用量 × 单价」：本物料当前为行业参考价，可按采购合同调整；保存后实时联动全厂成本与当日/当月/当年累计。') }}</div>
        <button v-if="isPriceOverride" class="reset" @click="resetPrice">{{ t('恢复库默认价') }}</button>
      </div>
      </CollapseSection>

      <CollapseSection :title="t('隐含碳因子')" tone="amber" :show-more="false">
      <div class="card">
        <div class="param-row">
          <div class="pr-top"><span>{{ t('当前值') }}</span><b>{{ fmt(carbon) }} <span class="u">tCO₂/{{ mat.unit }}</span></b></div>
          <div class="num-row">
            <input type="number" class="num" min="0" max="5" step="0.001" :value="carbon" @input="onCarbon($event.target.value)" />
            <span class="num-unit">tCO₂/{{ mat.unit }}</span>
          </div>
          <div class="pr-hint">
            {{ t('范围 0–5 tCO₂/{unit}；当前为', { unit: mat.unit }) }} <b>{{ isOverride ? t('会话覆盖值') : t('库默认值') }}</b>，{{ t('用于碳足迹核算与估算。') }}
          </div>
        </div>
        <button v-if="isOverride" class="reset" @click="store.setMaterialCarbon(mat.id, mat.carbon)">{{ t('恢复库默认值') }}</button>
      </div>
      </CollapseSection>

      <CollapseSection v-if="fuelFactor" :title="t('燃料排放因子 · NCV（低位发热量） / CC（单位热值含碳量）')" tone="amber" :show-more="false">
      <div class="card">
        <div class="kv2">
          <span>{{ t('NCV（低位发热量）') }}</span>
          <span class="kv-edit">
            <input type="number" class="num" step="0.001" :value="fuelFactor.ncv" @change="onFuel('ncv', $event.target.value)" />
            <span class="num-unit">{{ fuelUnit }}</span>
          </span>
        </div>
        <div class="kv2">
          <span>{{ t('CC（单位热值含碳量）') }}</span>
          <span class="kv-edit">
            <input type="number" class="num" step="0.0004" :value="fuelFactor.cc" @change="onFuel('cc', $event.target.value)" />
            <span class="num-unit">tC/GJ</span>
          </span>
        </div>
        <div class="pr-hint">{{ t('燃烧排放 = 用量 × NCV（低位发热量） × CC（单位热值含碳量） × 3.667；编辑后应用于全部仿真与 3D 孪生。') }}</div>
      </div>
      </CollapseSection>

      <CollapseSection :title="t('物理与物流参数')" tone="teal" :show-more="false">
      <div class="card">
        <div class="kv2" v-for="a in attributeDefs" :key="a.key">
          <span>{{ a.label }}</span>
          <span class="kv-edit">
            <input type="number" class="num" :step="a.step" :value="attrVal(a.key, a.def)" @change="onAttr(a, $event.target.value)" />
            <span class="num-unit">{{ a.unit }}</span>
          </span>
        </div>
        <div class="kv2">
          <span>{{ t('说明备注') }}</span>
          <input class="num note-input" :value="attrVal('note', '')" @change="onNote($event.target.value)" :placeholder="t('可选备注')" />
        </div>
        <div class="pr-hint">{{ t('以上为物料级自定义配置（随方案保存），用于台账与物流碳备注；不影响核心碳核算引擎。') }}</div>
      </div>
      </CollapseSection>

      <CollapseSection v-if="compFields && mat.id !== 'pulverized_coal'" :title="t('详细化学成分')" tone="green" :show-more="false">
      <div class="card">
        <div class="kv2" v-for="f in mainCompFields" :key="f.key">
          <span>{{ t(f.label) }}</span>
          <span class="kv-edit">
            <input type="number" class="num" :min="f.min" :max="f.max" :step="f.step"
                   :value="compVal(f.key)" @change="onComp(f, $event.target.value)" />
            <span class="num-unit">%</span>
          </span>
        </div>
        <template v-if="ashCompFields.length">
          <div class="ash-sub-t">{{ t('灰分组成（占灰分质量分数 %）') }}</div>
          <div class="ash-sub">
            <div class="kv2" v-for="f in ashCompFields" :key="f.key">
              <span>{{ t(f.label) }}</span>
              <span class="kv-edit">
                <input type="number" class="num" :min="f.min" :max="f.max" :step="f.step"
                       :value="compVal(f.key)" @change="onComp(f, $event.target.value)" />
                <span class="num-unit">%</span>
              </span>
            </div>
          </div>
        </template>
        <div class="pr-hint">{{ compHint }}</div>
        <button v-if="isCompOverride" class="reset" @click="resetComp">{{ t('恢复库默认成分') }}</button>
      </div>
      </CollapseSection>

      <CollapseSection v-if="mat.id === 'pulverized_coal'" :title="t('喷吹煤粉 · 配煤混合（N 种煤）')" tone="green" :show-more="false">
      <div class="card">
        <div class="pr-hint">{{ t('喷吹煤粉由多种煤按设定比例混合磨制。设置每种煤的占比与成分，系统按质量分数加权折算有效成分，联动 TFT / 置换比 RR / CO₂ / 炉渣碱度。默认混合（无烟煤/烟煤各 50%）加权 == 原单一煤粉值，数值中性。') }}</div>

        <div class="pc-coal" v-for="(b, i) in coalBlend" :key="b.id">
          <div class="pc-coal-head">
            <input class="pc-name" :value="b.name" @change="onCoalName(i, $event.target.value)" />
            <span class="pc-ratio">
              <input type="number" class="num" min="0" max="100" step="1" :value="(b.ratio*100).toFixed(0)" @change="onCoalRatio(i, $event.target.value)" />
              <span class="num-unit">%</span>
            </span>
            <button v-if="coalBlend.length > 1" class="x-btn danger" @click="removeCoal(i)" :title="t('删除该煤种')">✕</button>
          </div>
          <div class="kv2" v-for="f in pcMainFields" :key="f.key">
            <span>{{ t(f.label) }}</span>
            <span class="kv-edit">
              <input type="number" class="num" :min="0" :step="f.step" :value="b.comp[f.key]" @change="onCoalComp(i, f.key, $event.target.value)" />
              <span class="num-unit">%</span>
            </span>
          </div>
          <details class="pc-ash">
            <summary>{{ t('灰分组成（占灰分质量分数 %）') }}</summary>
            <div class="ash-sub">
              <div class="kv2" v-for="f in pcAshFields" :key="f.key">
                <span>{{ t(f.label) }}</span>
                <span class="kv-edit">
                  <input type="number" class="num" :min="0" :step="f.step" :value="b.comp[f.key]" @change="onCoalComp(i, f.key, $event.target.value)" />
                  <span class="num-unit">%</span>
                </span>
              </div>
            </div>
          </details>
        </div>

        <button class="pc-add" @click="addCoal">+ {{ t('添加煤种') }}</button>

        <div class="pc-weighted">
          <div class="pc-w-title">{{ t('加权有效成分（随上方配比实时联动）') }}</div>
          <div class="kv2" v-for="f in pcAllFields" :key="'w'+f.key">
            <span>{{ t(f.label) }}</span><b class="mono">{{ fmtW(weightedComp[f.key]) }}</b>
          </div>
        </div>

        <button v-if="isBlendOverride" class="reset" @click="store.clearCoalBlend('pulverized_coal')">{{ t('恢复默认混合（无烟煤/烟煤各 50%）') }}</button>
      </div>
      </CollapseSection>

      <CollapseSection :title="t('相关工艺 · 输入 / 输出')" tone="green" :show-more="false">
      <div class="card" v-if="usedIn.length">
        <div v-for="u in usedIn" :key="u.type" class="used-row">
          <span class="ur-name">{{ u.label }}</span>
          <span class="ur-tag" :class="u.role">{{ u.role === 'in' ? t('输入') : t('输出') }}</span>
        </div>
      </div>
      <div class="card note" v-else>{{ t('暂无工艺引用该物料。') }}</div>
      </CollapseSection>
    </template>
    <div v-else class="empty">{{ t('未选择物料，请从左侧「原料」栏点击查看。') }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'
import CollapseSection from './CollapseSection.vue'
import { t } from '../i18n'

const store = useSimStore()
const mat = computed(() => store.selectedMaterial)
const isOverride = computed(() => !!(store.materialOverrides && store.materialOverrides[mat.value.id]))
// ---- 外购单价：后端 purchases 只含下列可外购计量物料，成本 = 用量 × 单价（元/单位）----
const PURCHASABLE_IDS = ['iron_ore', 'coke', 'coal', 'limestone', 'scrap', 'electrode', 'ngas', 'electricity', 'biomass']
const purchasable = computed(() => !!mat.value && PURCHASABLE_IDS.includes(mat.value.id))
const price = computed(() => {
  const ov = store.materialOverrides && store.materialOverrides[mat.value.id]
  if (ov && ov.price != null) return ov.price
  return mat.value.price != null ? mat.value.price : 0
})
const isPriceOverride = computed(() => {
  if (!purchasable.value) return false
  const ov = store.materialOverrides && store.materialOverrides[mat.value.id]
  return !!(ov && ov.price != null)
})
function onPrice(v) { store.setMaterialAttr(mat.value.id, 'price', Number(v)) }
function resetPrice() { store.setMaterialAttr(mat.value.id, 'price', mat.value.price) }
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
// ---- 详细化学成分定义（质量分数 %）----
// 单一数据源在 data/materialComp.js（MaterialInspector 与炉渣碱度计算共用），
// 默认值为行业典型值（高碱度烧结矿 / 氧化球团 / 干熄焦 / 石灰石 / 块矿）；
// 覆盖值经 store.setMaterialComp 写入 materialOverrides[id].composition，随方案持久化。
// 灰分组成字段（sub:'ash'）为灰分内部构成（占灰分 %），单独分组渲染。
import { COMP_DEFS } from '../data/materialComp'
const compFields = computed(() => (mat.value ? COMP_DEFS[mat.value.id] || null : null))
const mainCompFields = computed(() => (compFields.value || []).filter((f) => !f.sub))
const ashCompFields = computed(() => (compFields.value || []).filter((f) => f.sub === 'ash'))
const isCompOverride = computed(() => {
  if (!mat.value) return false
  const ov = store.materialOverrides[mat.value.id]
  return !!(ov && ov.composition)
})
function compVal(key) {
  const ov = store.materialOverrides[mat.value.id]
  const c = ov && ov.composition
  if (c && c[key] != null) return c[key]
  const f = (compFields.value || []).find((x) => x.key === key)
  return f ? f.def : ''
}
function onComp(f, v) { store.setMaterialComp(mat.value.id, f.key, v) }
function resetComp() { store.clearMaterialComp(mat.value.id) }
const compHint = computed(() => {
  if (!mat.value || !compFields.value) return ''
  const id = mat.value.id
  if (id === 'coke') return t('干基工业分析典型值（FC+A+V≈100%）；灰分组成为灰分内部构成（各项之和≈100%），焦灰中 CaO/SiO₂/MgO/Al₂O₃ 全部入渣，参与炉渣二元碱度计算。')
  if (id === 'coal') return t('炼焦煤工业分析+元素分析典型值（FC+V+A+M≈100%）；灰分组成为灰分内部构成，用于焦炭灰分溯源与配煤参考。')
  if (id === 'pulverized_coal') return t('喷吹煤粉（PCI）成分典型值；元素碳 C / 氢 H 驱动置换比与 TFT 计算（与 tft.js 默认值对齐）；灰分组成为灰分内部构成，煤灰入渣参与炉渣二元碱度计算。')
  if (id === 'limestone') return t('石灰石（熔剂）典型成分；CaO 为炉渣碱度的主要外源，入炉受热分解 CaCO₃→CaO+CO₂（LOI≈42% 为分解失重，亦为熔剂碳排放来源）。')
  if (id === 'iron_ore') return t('天然块矿典型成分；SiO₂/Al₂O₃ 脉石为酸性物来源，入炉比例与品位共同影响渣量与炉渣二元碱度。')
  return t('化学成分（质量分数 %）典型值；TFe 品位与碱度（CaO/SiO₂）用于炉料结构与渣量对标，烧结/球团成分参与炉渣二元碱度计算。')
})

// ---- 喷吹煤粉配煤混合编辑器（N 种煤）----
// 单一数据源在 utils/coalBlend.js（与 TFT / 置换比 / CO₂ / 炉渣碱度计算共用）。
// 覆盖值经 store.setCoalBlend 写入 materialOverrides['pulverized_coal'].blend，随方案持久化；
// 未覆盖时读默认混合（无烟煤/烟煤各 50%，加权 == 原 tft.js 固定值）。
import { getCoalBlend, blendedComposition } from '../utils/coalBlend'
const coalBlend = computed(() => getCoalBlend(store.materialOverrides, 'pulverized_coal'))
const isBlendOverride = computed(() => !!(store.materialOverrides['pulverized_coal'] && store.materialOverrides['pulverized_coal'].blend))
const weightedComp = computed(() => blendedComposition(store.materialOverrides, 'pulverized_coal'))

const pcMainFields = [
  { key: 'c', label: 'C 元素碳', step: 0.1 },
  { key: 'h', label: 'H 氢', step: 0.1 },
  { key: 'fc', label: 'FC 固定碳', step: 0.1 },
  { key: 'ash', label: 'Ash 灰分', step: 0.1 },
  { key: 'h2o', label: 'H₂O 水分', step: 0.1 },
  { key: 'decomp', label: '热解热', step: 0.01 },
  { key: 'carbon_pct', label: '等效碳%(CO₂)', step: 0.01 },
]
const pcAshFields = [
  { key: 'ash_cao', label: '灰分 CaO', step: 0.1 },
  { key: 'ash_sio2', label: '灰分 SiO₂', step: 0.1 },
  { key: 'ash_al2o3', label: '灰分 Al₂O₃', step: 0.1 },
  { key: 'ash_mgo', label: '灰分 MgO', step: 0.1 },
  { key: 'ash_fe2o3', label: '灰分 Fe₂O₃', step: 0.1 },
  { key: 'ash_base', label: '灰分 碱度', step: 0.1 },
  { key: 'ash_so3', label: '灰分 SO₃', step: 0.1 },
]
const pcAllFields = [...pcMainFields, ...pcAshFields]

function _cloneBlend() {
  return coalBlend.value.map((x) => ({ id: x.id, name: x.name, ratio: x.ratio, comp: { ...x.comp } }))
}
function _commit(next) { store.setCoalBlend('pulverized_coal', next) }
function onCoalName(i, v) { const n = _cloneBlend(); n[i].name = v; _commit(n) }
function onCoalRatio(i, v) { const n = _cloneBlend(); n[i].ratio = Math.max(0, Number(v) || 0) / 100; _commit(n) }
function onCoalComp(i, key, v) { const n = _cloneBlend(); n[i].comp = { ...n[i].comp, [key]: Number(v) || 0 }; _commit(n) }
let _coalSeq = 0
function addCoal() {
  const n = _cloneBlend()
  _coalSeq++
  n.push({
    id: 'custom_' + Date.now() + '_' + _coalSeq, name: t('自定义煤') + _coalSeq, ratio: 0.2,
    comp: { c: 80, h: 4, fc: 80, ash: 10, h2o: 5, decomp: 0.35, carbon_pct: 69.95, ash_cao: 5, ash_sio2: 44, ash_al2o3: 28, ash_mgo: 1.5, ash_fe2o3: 9, ash_base: 1.3, ash_so3: 2.2 },
  })
  _commit(n)
}
function removeCoal(i) { const n = _cloneBlend(); if (n.length <= 1) return; n.splice(i, 1); _commit(n) }
function fmtW(v) { return v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(2) }
const attributeDefs = [
  { key: 'density', label: t('堆密度'), unit: 'kg/m³', def: 1500, step: 10 },
  { key: 'transport_factor', label: t('运输排放因子'), unit: 'kgCO₂/t·km', def: 0.1, step: 0.01 },
  { key: 'moisture', label: t('含水率'), unit: '%', def: 0, step: 0.5 },
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
.ash-sub-t { font-size: 11px; font-weight: 500; color: var(--green, #4f9d6b); margin: 10px 0 2px; padding-top: 8px; border-top: 1px dashed var(--line); }
.ash-sub { padding: 4px 0 0 10px; }
.num { width: 96px; }
.num-row { margin-top: 6px; }
.note-input { width: auto; flex: 1; min-width: 0; }
.used-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; }
.used-row + .used-row { border-top: 1px solid var(--line); }
.ur-name { font-size: 11px; }
.ur-tag { font-size: 10px; padding: 1px 8px; border-radius: 3px; }
.ur-tag.in { color: var(--accent2); border: 1px solid rgba(95,130,148,.4); background: rgba(95,130,148,.10); }
.ur-tag.out { color: var(--green); border: 1px solid rgba(79,157,107,.4); background: rgba(79,157,107,.08); }

/* ---- 喷吹煤粉配煤混合编辑器 ---- */
.pc-coal { border: 1px solid var(--line); border-radius: 4px; padding: 8px 9px; margin-top: 8px; }
.pc-coal + .pc-coal { margin-top: 8px; }
.pc-coal-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.pc-name { flex: 1; min-width: 0; font-size: 11px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 3px;
  background: var(--input, var(--bg)); color: var(--text); }
.pc-name:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); outline: none; }
.pc-ratio { display: inline-flex; align-items: center; gap: 3px; }
.pc-ratio .num { width: 56px; }
.pc-add { margin-top: 8px; width: 100%; border: 1px solid var(--accent2); background: transparent; color: var(--accent2); border-radius: 3px; padding: 6px; cursor: pointer; font-size: 11.5px; }
.pc-add:hover { background: var(--accent2); color: #fff; }
.pc-ash { margin-top: 6px; }
.pc-ash summary { font-size: 10.5px; color: var(--green, #4f9d6b); cursor: pointer; user-select: none; }
.pc-ash[open] summary { margin-bottom: 4px; }
.pc-weighted { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--line); }
.pc-w-title { font-size: 11px; font-weight: 500; color: var(--muted); margin-bottom: 4px; }
.pc-weighted .kv2 { font-size: 11px; padding: 2px 0; }
.pc-weighted .mono { font-variant-numeric: tabular-nums; margin-left: auto; }
</style>
