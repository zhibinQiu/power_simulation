<template>
  <!-- ============ 碳排核算视图：中间 3D 场景替换为多标准碳核算结果对比 ============ -->
  <div class="cc-view">
    <!-- 关闭/返回等操作已由顶栏工具栏提供 -->
    <div class="cc-body">
      <div v-if="!result" class="cc-empty">
        {{ t('暂无仿真结果，请先运行一次仿真后查看碳排核算。') }}
      </div>
      <template v-else>
        <!-- 测算口径：实时（小时粒度）/ 年度（默认全年，可下拉选择每月，按计划运行小时折算） -->
        <div class="cc-period">
          <div class="cc-period-seg">
            <button type="button" class="cc-pbtn" :class="{ active: period === 'realtime' }" @click="period = 'realtime'">{{ t('实时测算') }}</button>
            <button type="button" class="cc-pbtn" :class="{ active: period === 'annual' }" @click="period = 'annual'">{{ t('年度测算') }}</button>
          </div>
          <label v-if="period === 'annual'" class="cc-month">
            <span>{{ t('核算期间') }}</span>
            <select v-model="month" class="cc-month-sel">
              <option :value="0">{{ t('全年') }}</option>
              <option v-for="m in 12" :key="m" :value="m">{{ m }}月</option>
            </select>
          </label>
        </div>

        <div class="cc-cards">
          <div
            v-for="s in standards"
            :key="s.id"
            class="cc-card"
            :class="{ active: selected === s.id }"
            @click="selected = s.id"
          >
            <div class="cc-card-head">
              <div class="cc-card-icon" :class="s.id">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="s.icon"></svg>
              </div>
              <div>
                <div class="cc-card-code">{{ t(s.code) }}</div>
                <div class="cc-card-sub">{{ t(s.sub) }}</div>
              </div>
            </div>
            <p class="cc-card-desc">{{ t(s.desc) }}</p>
            <div class="cc-card-tags">
              <span v-for="(tag, i) in s.tags" :key="i" class="cc-tag" :class="tag.type">{{ t(tag.label) }}</span>
            </div>
            <div class="cc-card-value">
              <span class="cc-v-num">{{ fmt(qty(cardValue(s.id)), 1) }}</span>
              <span class="cc-v-unit">{{ unitText }}</span>
            </div>
            <div class="cc-card-hint">{{ t('当前核算 CO₂排放') }}（{{ unitText }}）— 长流程</div>
          </div>
        </div>

        <div class="cc-detail">
          <div class="cc-detail-head">
            <div class="cc-detail-icon" :class="current.id">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="current.icon"></svg>
            </div>
            <div>
              <div class="cc-detail-title">{{ t(current.title) }}</div>
              <div class="cc-detail-desc">{{ t(current.desc) }}</div>
            </div>
          </div>

          <div class="cc-scope-row">
            <div v-for="(tag, i) in current.tags" :key="i" class="cc-scope-box" :class="tag.type">
              <div class="cc-scope-label">{{ t(tag.label) }}</div>
              <div class="cc-scope-val">{{ scopeTotal(tag.key) }} <span class="cc-unit">{{ unitText }}</span></div>
            </div>
          </div>

          <div class="cc-table-wrap">
            <table class="cc-table">
              <thead>
                <tr>
                  <th v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">{{ c.label }}<template v-if="c.key !== 'name' && c.key !== 'intensity' && c.key !== 'control'"> ({{ unitText }})</template></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in rows" :key="idx">
                  <td v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">
                    <template v-if="c.key === 'name'">{{ row.name }}</template>
                    <template v-else-if="c.key === 'intensity'">{{ fmt(row[c.key]) }} <span class="cc-unit">kgCO₂/t</span></template>
                    <template v-else-if="c.key === 'control'">{{ t(row.control) }}</template>
                    <template v-else>{{ fmt(qty(row[c.key])) }}</template>
                  </td>
                </tr>
                <tr class="total">
                  <td v-for="c in columns" :key="c.key" :class="`text-${c.align || 'right'}`">
                    <template v-if="c.key === 'name'">{{ t('合计') }}</template>
                    <template v-else-if="c.key === 'intensity'">{{ fmt(totalRow[c.key]) }} <span class="cc-unit">kgCO₂/t</span></template>
                    <template v-else-if="c.key === 'control'"></template>
                    <template v-else>{{ fmt(qty(totalRow[c.key])) }}</template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="cc-tip">
            {{ t('切换提示：选择核算标准后，返回“能碳总览”页面，碳排放核算边界和顶部CO₂总量将按所选标准重新计算呈现。') }}
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
const result = computed(() => store.resultForView)
const selected = ref('iso')

// ===== 测算口径：实时（小时粒度）/ 年度（默认全年，可下拉选择每月）=====
const period = ref('realtime')
const month = ref(0) // 0 = 全年
const ANNUAL_HOURS = 8000
// 各月计划运行小时：全年合计 = 8000h（2/6/7/12 月为检修减负荷月）
const MONTH_HOURS = [700, 650, 700, 680, 700, 620, 620, 700, 680, 700, 680, 570]
// 折算因子：实时 = 1；年度全年 = 8000；月度 = 该月计划运行小时
const factor = computed(() => {
  if (period.value === 'realtime') return 1
  if (month.value === 0) return ANNUAL_HOURS
  return MONTH_HOURS[month.value - 1]
})
const unitText = computed(() => (period.value === 'realtime' ? 'tCO₂/h' : '万tCO₂'))
// 数值按口径折算：实时保持 t/h；年度/月度换算为 万tCO₂（×factor÷10000）
function qty(n) {
  if (n == null || Number.isNaN(n)) return 0
  const v = n * factor.value
  return period.value === 'realtime' ? v : v / 10000
}

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
    { key: 'scope1', label: 'Scope 1 直接排放', align: 'right' },
    { key: 'scope2', label: 'Scope 2 间接排放', align: 'right' },
    { key: 'total', label: '合计排放', align: 'right' },
    { key: 'intensity', label: '吨钢排放', align: 'right' },
  ],
  gbt: [
    { key: 'name', label: '工序设备', align: 'left' },
    { key: 'fuel', label: 'Scope 1 燃料燃烧', align: 'right' },
    { key: 'process', label: 'Scope 1 工艺过程', align: 'right' },
    { key: 'elec', label: 'Scope 2 净购入电力热力', align: 'right' },
    { key: 'total', label: '合计排放', align: 'right' },
    { key: 'intensity', label: '吨钢排放', align: 'right' },
  ],
  market: [
    { key: 'name', label: '工序设备', align: 'left' },
    { key: 'controlled', label: '管控工序直接排放', align: 'right' },
    { key: 'exempt', label: '非管控工序直接排放', align: 'right' },
    { key: 'total', label: '合计排放', align: 'right' },
    { key: 'intensity', label: '吨钢排放', align: 'right' },
  ],
}
const columns = computed(() => {
  const cols = columnSet[selected.value] || columnSet.iso
  return cols.map((c) => ({ ...c, label: t(c.label) }))
})

function cardValue(id) {
  if (!result.value) return 0
  if (id === 'market') return totalRow.value.controlled
  return result.value.totals?.co2_total || 0
}

function scopeTotal(key) {
  return fmt(qty(totalRow.value[key] || 0))
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  return n.toFixed(digits)
}

// 关闭碳排核算视图，返回数字孪生
const close = () => store.toggleCarbonCalc()
</script>

<style scoped>
.cc-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
}
.cc-body { flex: 1 1 auto; padding: 14px; overflow: auto; }
.cc-empty { text-align: center; color: var(--muted); font-size: 12px; padding: 60px 20px; }

/* ===== 测算口径切换：实时 / 年度（月度下拉） ===== */
.cc-period { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.cc-period-seg { display: flex; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.cc-pbtn {
  padding: 6px 16px; font-size: 12px; border: none; background: transparent;
  color: var(--muted); cursor: pointer; transition: background .12s, color .12s;
}
.cc-pbtn + .cc-pbtn { border-left: 1px solid var(--border); }
.cc-pbtn:hover { background: var(--panel-3); color: var(--text); }
.cc-pbtn.active { background: var(--accent-d); color: #fff; }
.cc-month { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); }
.cc-month-sel {
  background: var(--panel); color: var(--text); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 6px; font-size: 12px; outline: none; cursor: pointer;
}
.cc-month-sel:focus { border-color: var(--accent-d); }

/* ===== 核算标准切换卡 ===== */
.cc-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
@media (max-width: 900px) { .cc-cards { grid-template-columns: 1fr; } }
.cc-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; cursor: pointer; transition: border-color .12s, background .12s; }
.cc-card:hover { background: var(--panel-3); border-color: var(--accent2); }
.cc-card.active { background: var(--accent-l); border-color: var(--accent-d); }
.cc-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cc-card-icon { width: 30px; height: 30px; border-radius: 6px; flex: none;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); background: var(--panel-3); border: 1px solid var(--line); }
.cc-card.active .cc-card-icon { color: var(--accent-d); border-color: var(--accent-d); background: var(--accent-l); }
.cc-card-icon svg { width: 18px; height: 18px; }
.cc-card-code { font-size: 13px; font-weight: 600; color: var(--text); }
.cc-card-sub { font-size: 10px; color: var(--muted); margin-top: 1px; }
.cc-card-desc { font-size: 11px; color: var(--muted); line-height: 1.5; margin: 0 0 8px; min-height: 32px; }
.cc-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.cc-tag { font-size: 10px; padding: 2px 7px; border-radius: 4px; white-space: nowrap;
  background: var(--panel); border: 1px solid var(--border); color: var(--muted); }
.cc-card.active .cc-tag { color: var(--accent-d); border-color: var(--accent-d); }
.cc-card-value { display: flex; align-items: baseline; gap: 5px; margin-bottom: 2px; }
.cc-v-num { font-size: 22px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.cc-card.active .cc-v-num { color: var(--accent-d); }
.cc-v-unit { font-size: 11px; color: var(--muted); }
.cc-card-hint { font-size: 10px; color: var(--muted); }

/* ===== 明细区 ===== */
.cc-detail { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.cc-detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.cc-detail-icon { width: 34px; height: 34px; border-radius: 6px; flex: none;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); background: var(--panel-3); border: 1px solid var(--line); }
.cc-detail-icon svg { width: 20px; height: 20px; }
.cc-detail-title { font-size: 13px; font-weight: 600; color: var(--text); }
.cc-detail-desc { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* ===== 范围汇总 ===== */
.cc-scope-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin-bottom: 12px; }
.cc-scope-box { border-radius: 6px; padding: 8px 10px; border: 1px solid var(--border); background: var(--panel-2); }
.cc-scope-label { font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.cc-scope-val { font-size: 16px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }

/* ===== 明细表格 ===== */
.cc-table-wrap { overflow: auto; border: 1px solid var(--border); border-radius: 6px; }
.cc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cc-table th, .cc-table td { padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
.cc-table th { background: var(--panel-2); color: var(--muted); font-weight: 600; position: sticky; top: 0; }
.cc-table tr:last-child td { border-bottom: none; }
.cc-table tbody tr:hover td { background: var(--panel-2); }
.cc-table tr.total { font-weight: 600; background: var(--panel-3); }
.cc-table td { font-variant-numeric: tabular-nums; }
.text-left { text-align: left; }
.text-right { text-align: right; }
.cc-unit { font-size: 10px; color: var(--muted); margin-left: 2px; font-weight: 400; }

/* ===== 底部提示 ===== */
.cc-tip { margin-top: 10px; font-size: 10px; color: var(--muted); line-height: 1.6;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; }
</style>
