<template>
  <Teleport to="body">
    <div class="bff-mask" @mousedown.self="$emit('close')">
      <div class="bff-dialog">
        <div class="bff-titlebar">
          <span class="bff-icon">◱</span>
          <span class="bff-title">高炉正向一体化计算</span>
          <span class="bff-sub">物料平衡 · 炉顶煤气 · TFT · CO₂</span>
          <span class="bff-spacer"></span>
          <button class="bff-btn" :disabled="loading" @click="loadDefaults">恢复默认</button>
          <button class="bff-btn primary" :disabled="loading" @click="run">
            {{ loading ? '计算中…' : '开始计算' }}
          </button>
          <button class="bff-close" title="关闭 (Esc)" @click="$emit('close')">✕</button>
        </div>

        <div class="bff-body">
          <!-- 左栏：可编辑参数 -->
          <div class="bff-left">
            <div class="bff-sec">
              <div class="bff-sec-h">矿用量 (kg/tHM)<span class="hint">缺省 = Fe 平衡闭合配比</span></div>
              <div class="bff-row"><label>烧结矿</label><input type="number" v-model.number="p.m_sin" placeholder="自动" /><span class="u">kg/t</span></div>
              <div class="bff-row"><label>球团矿</label><input type="number" v-model.number="p.m_pel" placeholder="自动" /><span class="u">kg/t</span></div>
              <div class="bff-row"><label>块矿</label><input type="number" v-model.number="p.m_lump" placeholder="自动" /><span class="u">kg/t</span></div>
            </div>

            <div class="bff-sec">
              <div class="bff-sec-h">燃料 / 鼓风</div>
              <div class="bff-row"><label>焦比</label><input type="number" v-model.number="p.coke_rate" /><span class="u">kg/tHM</span></div>
              <div class="bff-row"><label>煤比</label><input type="number" v-model.number="p.coal_rate" /><span class="u">kg/tHM</span></div>
              <div class="bff-row"><label>鼓风量 V_B</label><input type="number" v-model.number="p.V_B" /><span class="u">Nm³/t</span></div>
              <div class="bff-row"><label>富氧流量 O₂</label><input type="number" v-model.number="p.O2_flow" /><span class="u">Nm³/t</span></div>
            </div>

            <div class="bff-sec">
              <div class="bff-sec-h">工艺参数</div>
              <div class="bff-row"><label>热风温度</label><input type="number" v-model.number="p.blast_temp" /><span class="u">°C</span></div>
              <div class="bff-row"><label>鼓风湿度</label><input type="number" v-model.number="p.blast_humidity" /><span class="u">g/Nm³</span></div>
              <div class="bff-row"><label>H₂ 间接还原度</label><input type="number" v-model.number="p.eta_H2" step="0.05" /><span class="u">—</span></div>
            </div>

            <div class="bff-sec">
              <div class="bff-sec-h">矿成分覆盖（%）<span class="hint">留空 = 后端默认</span></div>
              <div class="bff-comp">
                <div class="comp-h"><span>成分</span><span v-for="k in compKeys" :key="k">{{ k.toUpperCase() }}</span></div>
                <div class="comp-r" v-for="ore in compNames" :key="ore.key">
                  <span class="comp-name">{{ ore.label }}</span>
                  <input v-for="k in compKeys" :key="k" type="number" step="0.1"
                         v-model.number="comp[ore.key].comp[k]"
                         :placeholder="comp[ore.key].def[k] != null ? String(comp[ore.key].def[k]) : ''" />
                </div>
              </div>
            </div>
          </div>

          <!-- 右栏：结果展示 -->
          <div class="bff-right">
            <div v-if="err" class="bff-err">{{ err }}</div>
            <template v-else-if="r">
              <div class="bff-kpis">
                <div class="kpi"><div class="kpi-v" :class="tftCls">{{ fmt1(r.heat.TFT) }}</div><div class="kpi-l">TFT (°C)</div></div>
                <div class="kpi"><div class="kpi-v">{{ fmt2(r.material.basicity_R) }}</div><div class="kpi-l">碱度 R (CaO/SiO₂)</div></div>
                <div class="kpi"><div class="kpi-v">{{ fmt1(r.material.m_slag) }}</div><div class="kpi-l">渣量 (kg/tHM)</div></div>
                <div class="kpi"><div class="kpi-v">{{ fmt1(r.co2.CO2_potential) }}</div><div class="kpi-l">全碳潜在 CO₂ (kg/t)</div></div>
              </div>

              <div class="bff-tbl-sec">
                <div class="tbl-h">物料平衡（收入 / 支出, kg/tHM）</div>
                <table class="bff-tbl">
                  <tbody>
                    <tr><td>烧结矿 / 球团 / 块矿</td><td>{{ fmt1(r.material.m_sinter) }} / {{ fmt1(r.material.m_pellet) }} / {{ fmt1(r.material.m_lump) }}</td></tr>
                    <tr><td>焦炭 / 煤粉</td><td>{{ fmt1(r.material.m_coke) }} / {{ fmt1(r.material.m_coal) }}</td></tr>
                    <tr><td>炉尘（扣回）</td><td>− {{ fmt1(r.material.m_dust) }}</td></tr>
                    <tr><td>鼓风质量</td><td>{{ fmt1(r.material.mass_in_blast) }}</td></tr>
                    <tr class="sum"><td>收入合计</td><td>{{ fmt1(r.material.mass_in) }}</td></tr>
                    <tr><td>生铁 / 炉渣 / 炉尘</td><td>{{ fmt1(r.material.mass_out_pig) }} / {{ fmt1(r.material.mass_out_slag) }} / {{ fmt1(r.material.mass_out_dust) }}</td></tr>
                    <tr><td>炉顶煤气</td><td>{{ fmt1(r.material.mass_out_gas) }} ({{ fmt1(r.material.V_top) }} Nm³)</td></tr>
                    <tr class="sum"><td>支出合计</td><td>{{ fmt1(r.material.mass_out) }}</td></tr>
                    <tr><td>质量平衡误差</td><td>{{ fmt2(r.material.mass_error_pct) }}%</td></tr>
                  </tbody>
                </table>
              </div>

              <div class="bff-tbl-sec">
                <div class="tbl-h">炉顶煤气组成（体积分数 %）</div>
                <table class="bff-tbl">
                  <tbody>
                    <tr><td>CO₂</td><td>{{ pct(r.material.topgas_co2, r.material.V_top) }}</td></tr>
                    <tr><td>CO</td><td>{{ pct(r.material.topgas_co, r.material.V_top) }}</td></tr>
                    <tr><td>H₂</td><td>{{ pct(r.material.topgas_h2, r.material.V_top) }}</td></tr>
                    <tr><td>H₂O</td><td>{{ pct(r.material.topgas_h2o, r.material.V_top) }}</td></tr>
                    <tr><td>N₂</td><td>{{ pct(r.material.topgas_n2, r.material.V_top) }}</td></tr>
                  </tbody>
                </table>
              </div>

              <div class="bff-tbl-sec">
                <div class="tbl-h">还原度与碳素</div>
                <table class="bff-tbl">
                  <tbody>
                    <tr><td>直接还原度 r_d（碳平衡反推）</td><td>{{ fmt3(r.reduction.r_d) }} <span class="hint">(经验式 {{ fmt3(r.reduction.rd_calc_empirical) }})</span></td></tr>
                    <tr><td>风口前燃烧碳 m_C-R</td><td>{{ fmt1(r.material.m_C_R) }} kg C/tHM</td></tr>
                    <tr><td>入炉总碳 C_in</td><td>{{ fmt1(r.co2.C_in) }} kg C/tHM</td></tr>
                    <tr><td>煤气利用率 η_CO</td><td>{{ fmt1(r.co2.eta_CO) }}%</td></tr>
                  </tbody>
                </table>
              </div>

              <div class="bff-tbl-sec">
                <div class="tbl-h">一致性诊断</div>
                <table class="bff-tbl">
                  <tbody>
                    <tr><td>Fe 平衡残差</td><td>{{ fmt3(r.diagnostics.Fe_resid) }} kg/tHM <span :class="okCls(r.diagnostics.fe_closed)">{{ r.diagnostics.fe_closed ? '✓ 闭合' : '✗ 未闭合' }}</span></td></tr>
                    <tr><td>碳平衡残差</td><td>{{ fmt3(r.diagnostics.carbon_resid) }} kg C/tHM <span :class="okCls(r.diagnostics.carbon_closed)">{{ r.diagnostics.carbon_closed ? '✓ 闭合' : '✗ 未闭合' }}</span></td></tr>
                    <tr><td colspan="2" class="note">{{ r.diagnostics.note }}</td></tr>
                  </tbody>
                </table>
              </div>
            </template>
            <div v-else class="bff-placeholder">
              设置左侧参数后点击「开始计算」。<br>
              直接还原度 r_d 由碳平衡自动反推，无需输入。
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { forwardCalc, forwardDefaults } from '../utils/bfForward.js'

const emit = defineEmits(['close'])
const loading = ref(false)
const err = ref('')
const r = ref(null)

const compKeys = ['tfe', 'feo', 'cao', 'sio2', 'mgo', 'al2o3', 's', 'p', 'loi', 'mn', 'tio2']
const compNames = [
  { key: 'sinter', label: '烧结矿' },
  { key: 'pellet', label: '球团矿' },
  { key: 'lump',   label: '块矿' },
]

// 参数面板状态（后端默认值加载后填充）
const p = reactive({
  m_sin: null, m_pel: null, m_lump: null,
  coke_rate: 340, coal_rate: 180,
  V_B: 1121, O2_flow: 28.36,
  blast_temp: 1150, blast_humidity: 10, eta_H2: 0.40,
})
const comp = reactive({
  sinter: { def: {}, comp: {} },
  pellet: { def: {}, comp: {} },
  lump:   { def: {}, comp: {} },
})

async function loadDefaults() {
  try {
    const d = forwardDefaults()
    p.coke_rate = d.coke_rate; p.coal_rate = d.coal_rate
    p.V_B = d.V_B; p.O2_flow = d.O2_flow
    p.blast_temp = d.blast_temp; p.blast_humidity = d.blast_humidity
    p.eta_H2 = d.eta_H2
    p.m_sin = null; p.m_pel = null; p.m_lump = null
    for (const ore of compNames) {
      const dd = d[ore.key] || {}
      const c = comp[ore.key]
      c.def = { ...dd }
      for (const k of compKeys) c.comp[k] = null
    }
    err.value = ''
  } catch (e) { err.value = String(e.message || e) }
}

function payload() {
  const body = {
    coke_rate: p.coke_rate, coal_rate: p.coal_rate,
    V_B: p.V_B, O2_flow: p.O2_flow,
    blast_temp: p.blast_temp, blast_humidity: p.blast_humidity, eta_H2: p.eta_H2,
  }
  if (p.m_sin != null) body.m_sin = p.m_sin
  if (p.m_pel != null) body.m_pel = p.m_pel
  if (p.m_lump != null) body.m_lump = p.m_lump
  for (const ore of compNames) {
    const c = comp[ore.key].comp
    const ov = {}
    for (const k of compKeys) {
      if (c[k] != null && c[k] !== '') ov[k] = c[k]
    }
    if (Object.keys(ov).length) body[ore.key] = ov
  }
  return body
}

async function run() {
  loading.value = true; err.value = ''
  try {
    r.value = forwardCalc(payload())
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    loading.value = false
  }
}

const tftCls = computed(() => {
  const v = r.value && r.value.heat.TFT
  if (!v) return ''
  if (v < 2050) return 'low'
  if (v > 2250) return 'high'
  return 'ok'
})

const fmt1 = (v) => (v == null ? '—' : Number(v).toFixed(1))
const fmt2 = (v) => (v == null ? '—' : Number(v).toFixed(2))
const fmt3 = (v) => (v == null ? '—' : Number(v).toFixed(3))
const pct = (v, tot) => (v == null || !tot ? '—' : (v / tot * 100).toFixed(2) + '%')
const okCls = (ok) => (ok ? 'ok-dot' : 'bad-dot')

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => {
  loadDefaults()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.bff-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.bff-dialog { width: min(1180px, 96vw); height: min(720px, 92vh); background: var(--panel, #fff); border: 1px solid var(--border, #ddd); border-radius: 10px; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,0.25); }
.bff-titlebar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--border, #ddd); }
.bff-icon { font-size: 14px; color: var(--accent, #185FA5); }
.bff-title { font-weight: 600; font-size: 14px; color: var(--text, #222); }
.bff-sub { font-size: 11px; color: var(--faint, #999); }
.bff-spacer { flex: 1; }
.bff-btn { padding: 4px 12px; border: 1px solid var(--border, #ddd); border-radius: 6px; background: var(--panel2, #f5f5f5); font-size: 12px; cursor: pointer; color: var(--text, #333); }
.bff-btn.primary { background: var(--accent, #185FA5); color: #fff; border-color: var(--accent, #185FA5); }
.bff-btn:disabled { opacity: 0.6; cursor: wait; }
.bff-close { border: none; background: none; font-size: 13px; cursor: pointer; color: var(--faint, #999); padding: 2px 6px; }
.bff-body { flex: 1; display: flex; overflow: hidden; }
.bff-left { width: 330px; flex: none; overflow-y: auto; padding: 10px; border-right: 1px solid var(--border, #ddd); }
.bff-right { flex: 1; overflow-y: auto; padding: 12px; }
.bff-sec { margin-bottom: 12px; }
.bff-sec-h { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--text, #333); display: flex; align-items: baseline; gap: 8px; }
.hint { font-size: 10.5px; color: var(--faint, #999); font-weight: 400; }
.bff-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.bff-row label { width: 92px; font-size: 12px; color: var(--text2, #555); flex: none; }
.bff-row input { flex: 1; min-width: 0; padding: 4px 6px; border: 1px solid var(--border, #ccc); border-radius: 5px; font-size: 12px; background: var(--panel, #fff); color: var(--text, #333); }
.bff-row .u { width: 52px; font-size: 10.5px; color: var(--faint, #999); flex: none; text-align: right; }
.bff-comp { font-size: 11px; }
.comp-h, .comp-r { display: grid; grid-template-columns: 58px repeat(11, 1fr); gap: 2px; align-items: center; }
.comp-h { color: var(--faint, #999); margin-bottom: 2px; }
.comp-r { margin-bottom: 2px; }
.comp-name { color: var(--text2, #555); white-space: nowrap; }
.comp-r input { width: 100%; min-width: 0; padding: 2px 2px; border: 1px solid var(--border, #ddd); border-radius: 3px; font-size: 10.5px; background: var(--panel, #fff); color: var(--text, #333); text-align: right; }
.bff-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
.kpi { background: var(--panel2, #f6f6f6); border: 1px solid var(--border, #eee); border-radius: 8px; padding: 8px 10px; text-align: center; }
.kpi-v { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-v.ok { color: var(--green, #3B6D11); }
.kpi-v.low { color: var(--accent, #185FA5); }
.kpi-v.high { color: var(--red, #A32D2D); }
.kpi-l { font-size: 10.5px; color: var(--faint, #999); margin-top: 2px; }
.bff-tbl-sec { margin-bottom: 10px; }
.tbl-h { font-size: 12px; font-weight: 600; margin-bottom: 4px; color: var(--text, #333); }
.bff-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.bff-tbl td { padding: 3px 8px; border-bottom: 1px solid var(--border, #f0f0f0); color: var(--text, #444); }
.bff-tbl td:first-child { color: var(--text2, #666); width: 46%; }
.bff-tbl tr.sum td { font-weight: 600; background: var(--panel2, #f6f6f6); }
.bff-tbl .note { font-size: 10.5px; color: var(--faint, #999); }
.ok-dot { color: var(--green, #3B6D11); margin-left: 6px; }
.bad-dot { color: var(--red, #A32D2D); margin-left: 6px; }
.bff-err { color: var(--red, #A32D2D); font-size: 12px; padding: 12px; }
.bff-placeholder { color: var(--faint, #999); font-size: 13px; text-align: center; padding-top: 80px; line-height: 2; }
</style>
