<template>
  <teleport to="body">
    <div v-if="state.open" class="scan-mask" @click.self="close">
      <div class="scan-modal" role="dialog" aria-label="参数扫描与守恒审计">
        <div class="sm-head">
          <div class="sm-title">
            <Icon :name="state.tab === 'scan' ? 'search' : 'bolt'" :size="15" />
            <span>{{ state.tab === 'scan' ? '参数扫描 · 敏感性分析' : '碳素流守恒审计' }}</span>
            <span v-if="state.tab === 'scan' && state.unitName" class="sm-sub">· {{ state.unitName }}</span>
          </div>
          <div class="sm-tabs">
            <div class="sm-tab" :class="{ on: state.tab === 'scan' }" @click="state.tab = 'scan'">参数扫描</div>
            <div class="sm-tab" :class="{ on: state.tab === 'audit' }" @click="state.tab = 'audit'">守恒审计</div>
          </div>
          <button class="sm-x" @click="close" title="关闭 (Esc)">✕</button>
        </div>

        <!-- ============ 参数扫描 ============ -->
        <div v-if="state.tab === 'scan'" class="sm-body">
          <div v-if="!paramOptions.length" class="sm-empty">该工序无可扫描的数值参数。</div>
          <template v-else>
            <div class="sm-row">
              <label>扫描参数</label>
              <select v-model="selKey" @change="onParamChange">
                <option v-for="p in paramOptions" :key="p.key" :value="p.key">
                  {{ p.label }}（{{ p.unit }}）
                </option>
              </select>
            </div>
            <div class="sm-row sm-range">
              <label>区间</label>
              <input type="number" class="num" v-model.number="low" :step="step" />
              <span class="sm-arrow">→</span>
              <input type="number" class="num" v-model.number="high" :step="step" />
              <label class="sm-steps">步数</label>
              <input type="number" class="num sm-steps-in" v-model.number="steps" min="2" max="41" step="1" />
              <button class="sm-run" @click="runScan" :disabled="loading">
                {{ loading ? '计算中…' : '运行扫描' }}
              </button>
            </div>
            <div v-if="err" class="sm-err">{{ err }}</div>

            <div v-if="scan && scan.points.length" class="sm-charts">
              <div class="sm-chart">
                <div class="sm-chart-t">吨钢碳强度 (kgCO₂/t)</div>
                <TrendChart :data="intensitySeries" :color="'var(--accent)'" :height="120" />
              </div>
              <div class="sm-chart">
                <div class="sm-chart-t">全厂碳排 (tCO₂/h)</div>
                <TrendChart :data="co2Series" :color="'var(--red)'" :height="120" />
              </div>
            </div>

            <div v-if="scan && scan.points.length" class="sm-table">
              <div class="sm-th">
                <span>{{ paramLabel }}</span>
                <span>吨钢强度</span><span>全厂碳排</span><span>钢产量</span>
              </div>
              <div v-for="p in scan.points" :key="p.value" class="sm-tr" :class="{ base: isBaseline(p.value) }">
                <span>{{ fmt(p.value) }}</span>
                <span>{{ fmt(p.intensity) }}</span>
                <span>{{ fmt(p.co2_total) }}</span>
                <span>{{ fmt(p.steel_output) }}</span>
              </div>
            </div>
            <div v-if="scan" class="sm-note">
              敏感性分析：固定其余参数，扫描单工序「{{ paramLabel }}」对全厂指标的影响。
              当前基线值 {{ fmt(currentValue) }} 已高亮。扫描结果仅反映本平台的经验耦合模型趋势，绝对值非合规报送依据。
            </div>
          </template>
        </div>

        <!-- ============ 守恒审计 ============ -->
        <div v-else class="sm-body">
          <div class="sm-row">
            <button class="sm-run" @click="runAudit" :disabled="loading">{{ loading ? '计算中…' : '运行守恒审计' }}</button>
            <span class="sm-hint">逐工序核对碳输入 = 排CO₂ + 固钢 + 入渣 + 捕集 + 产品携出</span>
          </div>
          <div v-if="auditErr" class="sm-err">{{ auditErr }}</div>
          <div v-if="audit" class="sm-table">
            <div class="sm-th">
              <span>工序</span><span>碳输入</span><span>排CO₂</span><span>固钢</span>
              <span>入渣</span><span>捕集</span><span>产品碳</span><span>残差</span>
            </div>
            <div v-for="u in audit.units" :key="u.id" class="sm-tr">
              <span>{{ u.name }}</span>
              <span>{{ fmt(u.carbon_in) }}</span>
              <span>{{ fmt(u.carbon_to_co2) }}</span>
              <span>{{ fmt(u.carbon_to_steel) }}</span>
              <span>{{ fmt(u.carbon_to_slag) }}</span>
              <span>{{ fmt(u.carbon_captured) }}</span>
              <span>{{ fmt(u.carbon_to_product) }}</span>
              <span :class="{ warn: Math.abs(u.residual) > 0.01 }">{{ fmt(u.residual) }}</span>
            </div>
            <div class="sm-tr sm-total">
              <span>全厂</span>
              <span>{{ fmt(audit.totals.carbon_in) }}</span>
              <span>{{ fmt(audit.totals.carbon_to_co2) }}</span>
              <span>{{ fmt(audit.totals.carbon_to_steel) }}</span>
              <span>{{ fmt(audit.totals.carbon_to_slag) }}</span>
              <span>{{ fmt(audit.totals.carbon_captured) }}</span>
              <span>{{ fmt(audit.totals.carbon_to_product) }}</span>
              <span :class="{ warn: Math.abs(audit.totals.residual) > 0.01 }">{{ fmt(audit.totals.residual) }}</span>
            </div>
          </div>
          <div v-if="audit" class="sm-note">{{ audit.note }}</div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'
import { scanState, closeScanDialog } from '../stores/scan'
import { api } from '../api/client'
import TrendChart from './TrendChart.vue'
import Icon from './Icon.vue'

const store = useSimStore()
const state = scanState

const paramOptions = ref([])
const selKey = ref('')
const low = ref(0)
const high = ref(0)
const steps = ref(11)
const step = ref(1)
const loading = ref(false)
const scan = ref(null)
const err = ref('')
const currentValue = ref(0)

const audit = ref(null)
const auditErr = ref('')
const loadingA = ref(false)

const paramLabel = computed(() => {
  const p = paramOptions.value.find((x) => x.key === selKey.value)
  return p ? `${p.label} (${p.unit})` : selKey.value
})

const intensitySeries = computed(() =>
  (scan.value && scan.value.points || []).map((p) => ({ t: String(p.value), v: p.intensity })))
const co2Series = computed(() =>
  (scan.value && scan.value.points || []).map((p) => ({ t: String(p.value), v: p.co2_total })))

function fmt(n) { return Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }
function isBaseline(v) { return Math.abs(v - currentValue.value) < 1e-6 }

function initScan() {
  scan.value = null
  err.value = ''
  paramOptions.value = []
  selKey.value = ''
  if (!state.unitType || !store.paramSchema) return
  // 后端 /api/param-schema 返回扁平参数列表：schema[type] = [{ key, label, unit, min, max, step, kind: 'config'|'optim' }]
  const arr = (store.paramSchema.schema && store.paramSchema.schema[state.unitType]) || []
  const config = arr.filter((p) => p.kind === 'config')
  const optim = arr.filter((p) => p.kind === 'optim')
  const opts = [...config, ...optim]
    .filter((p) => typeof p.min === 'number' && typeof p.max === 'number' && p.min < p.max)
    .map((p) => ({ key: p.key, label: p.label, unit: p.unit || '', min: p.min, max: p.max, step: p.step || 1 }))
  paramOptions.value = opts
  if (!opts.length) return
  // 默认优先选「决策变量(optim)」参数，否则取第一个
  const optimKeys = new Set(optim.map((x) => x.key))
  const def = opts.find((p) => optimKeys.has(p.key)) || opts[0]
  selKey.value = def.key
  onParamChange()
}

function onParamChange() {
  const p = paramOptions.value.find((x) => x.key === selKey.value)
  if (!p) return
  step.value = p.step
  low.value = p.min
  high.value = p.max
  // 当前基线值：取模型中该工序此参数的实际值（缺省取区间中点）
  const u = store.model && store.model.units ? store.model.units.find((x) => x.id === state.unitId) : null
  const cur = u && u.params && u.params[p.key] != null ? u.params[p.key]
    : (state.unitType && store.paramSchema ? null : null)
  currentValue.value = cur != null ? cur : Math.round((p.min + p.max) / 2)
}

async function runScan() {
  if (!state.unitId || !selKey.value) return
  if (low.value >= high.value) { err.value = '区间下界必须小于上界'; return }
  loading.value = true
  err.value = ''
  try {
    scan.value = await api.scan(store.model, state.unitId, selKey.value, low.value, high.value, steps.value)
  } catch (e) {
    err.value = '扫描失败：' + (e.message || e)
  } finally {
    loading.value = false
  }
}

async function runAudit() {
  loadingA.value = true
  auditErr.value = ''
  try {
    audit.value = await api.audit(store.model)
  } catch (e) {
    auditErr.value = '审计失败：' + (e.message || e)
  } finally {
    loadingA.value = false
  }
}

function close() { closeScanDialog() }

watch(() => state.open, (v) => {
  if (v) nextTick(() => { if (state.tab === 'scan') initScan(); else runAudit() })
})
watch(() => state.tab, (t) => { if (t === 'audit' && !audit.value) runAudit() })
</script>

<style scoped>
.scan-mask { position: fixed; inset: 0; background: rgba(12,16,22,.42); z-index: 260;
  display: flex; align-items: center; justify-content: center; padding: 24px; }
.scan-modal { width: 560px; max-width: 100%; max-height: 86vh; overflow: auto;
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow); }
.sm-head { display: flex; align-items: center; gap: 14px; padding: 10px 14px; border-bottom: 1px solid var(--border);
  background: var(--panel-2); position: sticky; top: 0; }
.sm-title { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--text); font-weight: 500; }
.sm-title .sm-sub { color: var(--muted); font-weight: 400; }
.sm-tabs { display: flex; gap: 4px; margin-left: auto; }
.sm-tab { padding: 4px 10px; font-size: 11px; border-radius: 6px; cursor: pointer; color: var(--muted); }
.sm-tab.on { background: var(--accent-l); color: var(--accent-d); }
.sm-x { background: transparent; border: none; color: var(--muted); font-size: 14px; cursor: pointer; padding: 2px 6px; border-radius: 5px; }
.sm-x:hover { color: var(--text); background: var(--panel-3); }
.sm-body { padding: 14px; }
.sm-empty { color: var(--muted); font-size: 12px; padding: 20px; text-align: center; }
.sm-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.sm-row label { font-size: 11px; color: var(--muted); flex: 0 0 auto; }
.sm-row select { width: auto; min-width: 200px; }
.sm-range input.num { width: 92px; }
.sm-arrow { color: var(--muted); }
.sm-steps { margin-left: 6px; }
.sm-steps-in { width: 60px; }
.sm-run { background: var(--accent); color: #fff; border: 1px solid var(--accent); font-weight: 600; padding: 6px 14px; border-radius: 6px; cursor: pointer; }
.sm-run:hover { background: var(--accent-d); }
.sm-run:disabled { opacity: .6; cursor: default; }
.sm-hint { color: var(--muted); font-size: 11px; }
.sm-err { color: var(--red); font-size: 11px; margin: -4px 0 10px; }
.sm-charts { display: flex; flex-direction: column; gap: 12px; margin: 6px 0 12px; }
.sm-chart-t { font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.sm-table { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 10px; }
.sm-th, .sm-tr { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr 1fr 1fr 0.9fr; gap: 0;
  font-size: 11px; padding: 5px 8px; align-items: center; }
.sm-th { background: var(--panel-2); color: var(--muted); border-bottom: 1px solid var(--border); }
.sm-tr { border-bottom: 1px solid var(--line); }
.sm-tr:last-child { border-bottom: none; }
.sm-tr span { font-variant-numeric: tabular-nums; white-space: nowrap; }
.sm-tr.base { background: var(--accent-l); }
.sm-tr.base span:first-child { color: var(--accent-d); font-weight: 500; }
.sm-tr.warn span:last-child { color: var(--yellow); }
.sm-tr.sm-total { background: var(--panel-3); font-weight: 500; }
.sm-note { font-size: 10px; color: var(--muted); line-height: 1.6; background: var(--panel-2);
  border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; }
</style>
