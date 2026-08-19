<template>
  <div class="pd-mask" @click.self="close">
    <div class="pd-dialog" role="dialog" aria-modal="true" aria-labelledby="pd-title">
      <div class="pd-head">
        <div class="pd-title">
          <svg class="pd-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z"/><circle cx="8" cy="10" r="2"/><path d="m2 16 5-5 4 4 6-6 5 5"/></svg>
          <h3 id="pd-title">全景数据</h3>
          <span class="pd-sub">多标准碳核算结果对比</span>
        </div>
        <button class="pd-close" @click="close" aria-label="关闭">×</button>
      </div>

      <div class="pd-body">
        <div v-if="!result" class="pd-empty">
          暂无仿真结果，请先运行一次仿真后查看全景数据。
        </div>
        <template v-else>
          <div class="pd-cards">
            <div
              v-for="s in standards"
              :key="s.id"
              class="pd-card"
              :class="{ active: selected === s.id }"
              @click="selected = s.id"
            >
              <div class="pd-card-head">
                <div class="pd-card-icon" :class="s.id">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="s.icon"></svg>
                </div>
                <div>
                  <div class="pd-card-code">{{ s.code }}</div>
                  <div class="pd-card-sub">{{ s.sub }}</div>
                </div>
              </div>
              <p class="pd-card-desc">{{ s.desc }}</p>
              <div class="pd-card-tags">
                <span v-for="(tag, i) in s.tags" :key="i" class="pd-tag" :class="tag.type">{{ tag.label }}</span>
              </div>
              <div class="pd-card-value">
                <span class="pd-v-num">{{ fmt(cardValue(s.id), 1) }}</span>
                <span class="pd-v-unit">tCO₂/h</span>
              </div>
              <div class="pd-card-hint">当前核算 CO₂排放（t/h）— 长流程</div>
            </div>
          </div>

          <div class="pd-detail">
            <div class="pd-detail-head">
              <div class="pd-detail-icon" :class="current.id">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="current.icon"></svg>
              </div>
              <div>
                <div class="pd-detail-title">{{ current.title }}</div>
                <div class="pd-detail-desc">{{ current.desc }}</div>
              </div>
            </div>

            <div class="pd-scope-row">
              <div v-for="(tag, i) in current.tags" :key="i" class="pd-scope-box" :class="tag.type">
                <div class="pd-scope-label">{{ tag.label }}</div>
                <div class="pd-scope-val">{{ scopeTotal(tag.key) }}</div>
              </div>
            </div>

            <div class="pd-table-wrap">
              <table class="pd-table">
                <thead>
                  <tr>
                    <th v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">{{ c.label }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in rows" :key="idx">
                    <td v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">
                      <template v-if="c.key === 'name'">{{ row.name }}</template>
                      <template v-else-if="c.key === 'intensity'">{{ fmt(row[c.key]) }} <span class="pd-unit">kgCO₂/t</span></template>
                      <template v-else-if="c.key === 'control'">{{ row.control }}</template>
                      <template v-else>{{ fmt(row[c.key]) }}</template>
                    </td>
                  </tr>
                  <tr class="total">
                    <td v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">
                      <template v-if="c.key === 'name'">合计</template>
                      <template v-else-if="c.key === 'intensity'">{{ fmt(totalRow[c.key]) }} <span class="pd-unit">kgCO₂/t</span></template>
                      <template v-else-if="c.key === 'control'"></template>
                      <template v-else>{{ fmt(totalRow[c.key]) }}</template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="pd-tip">
              切换提示：选择核算标准后，返回“能碳总览”页面，碳排放核算边界和顶部CO₂总量将按所选标准重新计算呈现。
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'

const emit = defineEmits(['close'])
const store = useSimStore()
const result = computed(() => store.resultForView)
const selected = ref('iso')

const standards = [
  {
    id: 'iso',
    code: 'ISO 14064-1',
    sub: 'ISO 14064-1:2018',
    title: 'ISO 14064-1:2018 温室气体量化与报告（组织层面）',
    desc: '国际标准化组织发布的温室气体量化与报告规范，按排放范围（Scope）划分，覆盖直接排放、能源间接排放及其他间接排放。',
    tags: [
      { label: 'Scope 1 直接排放', type: 's1', key: 'scope1' },
      { label: 'Scope 2 能源间接排放', type: 's2', key: 'scope2' },
      { label: 'Scope 3 其他间接排放', type: 's3', key: 'scope3' },
    ],
    icon: '<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a15 15 0 0 1 4 9 15 15 0 0 1-4 9 15 15 0 0 1-4-9 15 15 0 0 1 4-9z"/>',
  },
  {
    id: 'gbt',
    code: 'GB/T 32151-2015',
    sub: 'GB/T 32151.5-2015',
    title: 'GB/T 32151.5-2015 钢铁生产企业温室气体排放核算',
    desc: '中国国家标准，专门针对钢铁生产企业的温室气体排放核算规范。覆盖燃料燃烧排放、碳酸盐分解排放、电极消耗排放、外购电力热力排放等。',
    tags: [
      { label: 'Scope 1 燃料燃烧', type: 's1', key: 'fuel' },
      { label: 'Scope 1 工艺过程', type: 's1p', key: 'process' },
      { label: 'Scope 2 净购入电力热力', type: 's2', key: 'elec' },
    ],
    icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 18 15 15"/>',
  },
  {
    id: 'market',
    code: '全国碳市场',
    sub: '生态环境部令第19号',
    title: '全国碳市场 钢铁行业管控口径',
    desc: '全国碳市场对钢铁行业的管控范围，仅覆盖烧结/球团、焦化、炼铁、炼钢（转炉）等核心工序的直接排放，轧钢等间接排放工序暂不纳入管控。',
    tags: [
      { label: 'Scope 1 管控工序直接排放', type: 's1', key: 'controlled' },
      { label: '豁免 非管控工序', type: 'exempt', key: 'exempt' },
    ],
    icon: '<path d="M3 3v18h18"/><path d="M7 16l4-6 4 4 5-8"/>',
  },
]

const current = computed(() => standards.find(s => s.id === selected.value) || standards[0])

const controlledTypes = new Set([
  'sinter_plant', 'pelletizing', 'coke_oven', 'blast_furnace',
  'hydrogen_bf', 'smelting_reduction', 'bof', 'aod'
])

const processKeywords = ['分解', '电极', '金属料脱碳', '残碳氧化', '脱碳(不锈钢)', '碳酸']
function isProcessItem(name) {
  return processKeywords.some(k => name.includes(k))
}

function classifyGbt(unit) {
  const direct = unit.co2_direct || 0
  const ledger = unit.breakdown || []
  let process = 0
  let accounted = 0
  for (const it of ledger) {
    if (it.scope !== 'direct' || !it.co2) continue
    accounted += it.co2
    if (isProcessItem(it.item)) process += it.co2
  }
  const fuel = Math.max(direct - process, 0)
  return { fuel, process, elec: unit.co2_indirect || 0 }
}

function unitRow(unit) {
  const name = unit.name || unit.type || '-'
  const steel = result.value?.totals?.steel_output || 1
  const direct = unit.co2_direct || 0
  const indirect = unit.co2_indirect || 0
  const total = direct + indirect
  const intensity = total / steel * 1000
  const gbt = classifyGbt(unit)
  const controlled = controlledTypes.has(unit.type) ? direct : 0
  const exempt = controlled ? 0 : direct

  return {
    name,
    scope1: direct,
    scope2: indirect,
    scope3: 0,
    fuel: gbt.fuel,
    process: gbt.process,
    elec: gbt.elec,
    controlled,
    exempt,
    total,
    intensity,
    control: controlled ? '管控' : '豁免',
  }
}

const rows = computed(() => {
  if (!result.value) return []
  return (result.value.units || []).map(unitRow)
})

const totalRow = computed(() => {
  const init = {
    scope1: 0, scope2: 0, scope3: 0,
    fuel: 0, process: 0, elec: 0,
    controlled: 0, exempt: 0, total: 0,
  }
  for (const r of rows.value) {
    for (const k of Object.keys(init)) init[k] += r[k] || 0
  }
  const steel = result.value?.totals?.steel_output || 1
  init.intensity = init.total / steel * 1000
  return init
})

const columnSet = {
  iso: [
    { key: 'name', label: '工序设备', align: 'left' },
    { key: 'scope1', label: 'Scope 1 直接排放 (t/h)', align: 'right' },
    { key: 'scope2', label: 'Scope 2 间接排放 (t/h)', align: 'right' },
    { key: 'total', label: '合计排放 (t/h)', align: 'right' },
    { key: 'intensity', label: '吨钢排放 (kg CO₂/t)', align: 'right' },
  ],
  gbt: [
    { key: 'name', label: '工序设备', align: 'left' },
    { key: 'fuel', label: 'Scope 1 燃料燃烧 (t/h)', align: 'right' },
    { key: 'process', label: 'Scope 1 工艺过程 (t/h)', align: 'right' },
    { key: 'elec', label: 'Scope 2 净购入电力热力 (t/h)', align: 'right' },
    { key: 'total', label: '合计排放 (t/h)', align: 'right' },
    { key: 'intensity', label: '吨钢排放 (kg CO₂/t)', align: 'right' },
  ],
  market: [
    { key: 'name', label: '工序设备', align: 'left' },
    { key: 'controlled', label: '管控工序直接排放 (t/h)', align: 'right' },
    { key: 'exempt', label: '非管控工序直接排放 (t/h)', align: 'right' },
    { key: 'total', label: '合计排放 (t/h)', align: 'right' },
    { key: 'intensity', label: '吨钢排放 (kg CO₂/t)', align: 'right' },
  ],
}
const columns = computed(() => columnSet[selected.value] || columnSet.iso)

function cardValue(id) {
  if (!result.value) return 0
  if (id === 'market') return totalRow.value.controlled
  return result.value.totals?.co2_total || 0
}

function scopeTotal(key) {
  return fmt(totalRow.value[key] || 0)
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  return n.toFixed(digits)
}

function close() { emit('close') }

function onKey(e) { if (e.key === 'Escape') close() }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
/* ===== 遮罩 + 对话框：与系统 .scan-mask/.scan-modal 同款 VSCode/MATLAB 工业风 ===== */
.pd-mask { position: fixed; inset: 0; background: rgba(12,16,22,.42); z-index: 500;
  display: flex; align-items: center; justify-content: center; padding: 24px; }
.pd-dialog { width: min(1100px, 96vw); max-height: 90vh; display: flex; flex-direction: column;
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  box-shadow: var(--shadow); color: var(--text); overflow: hidden; }
.pd-head { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); background: var(--panel-2); flex: none; }
.pd-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.pd-title h3 { margin: 0; font-size: 13px; font-weight: 500; }
.pd-title-icon { width: 16px; height: 16px; color: var(--accent2); flex: none; }
.pd-sub { color: var(--muted); font-size: 11px; margin-left: 2px; white-space: nowrap; }
.pd-close { width: 24px; height: 24px; border: none; background: transparent; color: var(--muted);
  font-size: 16px; line-height: 1; cursor: pointer; border-radius: 5px; flex: none; }
.pd-close:hover { color: var(--text); background: var(--panel-3); }
.pd-body { padding: 14px; overflow: auto; }
.pd-empty { text-align: center; color: var(--muted); font-size: 12px; padding: 40px 20px; }

/* ===== 核算标准切换卡：VS Code 面板卡（扁平、无彩色渐变） ===== */
.pd-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
@media (max-width: 900px) { .pd-cards { grid-template-columns: 1fr; } }
.pd-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; cursor: pointer; transition: border-color .12s, background .12s; }
.pd-card:hover { background: var(--panel-3); border-color: var(--accent2); }
.pd-card.active { background: var(--accent-l); border-color: var(--accent); }
.pd-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.pd-card-icon { width: 30px; height: 30px; border-radius: 6px; flex: none;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); background: var(--panel-3); border: 1px solid var(--line); }
.pd-card.active .pd-card-icon { color: var(--accent); border-color: var(--accent); background: var(--accent-l); }
.pd-card-icon svg { width: 18px; height: 18px; }
.pd-card-code { font-size: 13px; font-weight: 600; color: var(--text); }
.pd-card-sub { font-size: 10px; color: var(--muted); margin-top: 1px; }
.pd-card-desc { font-size: 11px; color: var(--muted); line-height: 1.5; margin: 0 0 8px; min-height: 32px; }
.pd-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.pd-tag { font-size: 10px; padding: 2px 7px; border-radius: 4px; white-space: nowrap;
  background: var(--panel); border: 1px solid var(--border); color: var(--muted); }
.pd-card.active .pd-tag { color: var(--accent); border-color: var(--accent); }
.pd-card-value { display: flex; align-items: baseline; gap: 5px; margin-bottom: 2px; }
.pd-v-num { font-size: 22px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.pd-card.active .pd-v-num { color: var(--accent); }
.pd-v-unit { font-size: 11px; color: var(--muted); }
.pd-card-hint { font-size: 10px; color: var(--muted); }

/* ===== 明细区 ===== */
.pd-detail { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.pd-detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.pd-detail-icon { width: 34px; height: 34px; border-radius: 6px; flex: none;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); background: var(--panel-3); border: 1px solid var(--line); }
.pd-detail-icon svg { width: 20px; height: 20px; }
.pd-detail-title { font-size: 13px; font-weight: 600; color: var(--text); }
.pd-detail-desc { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* ===== 范围汇总（chip 风格，中性） ===== */
.pd-scope-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin-bottom: 12px; }
.pd-scope-box { border-radius: 6px; padding: 8px 10px; border: 1px solid var(--border); background: var(--panel-2); }
.pd-scope-label { font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.pd-scope-val { font-size: 16px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }

/* ===== 明细表格（sm 风格） ===== */
.pd-table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 6px; }
.pd-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.pd-table th, .pd-table td { padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
.pd-table th { background: var(--panel-2); color: var(--muted); font-weight: 600; position: sticky; top: 0; }
.pd-table tr:last-child td { border-bottom: none; }
.pd-table tbody tr:hover td { background: var(--panel-2); }
.pd-table tr.total { font-weight: 600; background: var(--panel-3); }
.pd-table td { font-variant-numeric: tabular-nums; }
.text-left { text-align: left; }
.text-right { text-align: right; }
.pd-unit { font-size: 10px; color: var(--muted); margin-left: 2px; font-weight: 400; }

/* ===== 底部提示（sm-note 风格） ===== */
.pd-tip { margin-top: 10px; font-size: 10px; color: var(--muted); line-height: 1.6;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; }
</style>
