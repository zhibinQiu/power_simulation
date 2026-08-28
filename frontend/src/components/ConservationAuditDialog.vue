<template>
  <teleport to="body">
    <div v-if="state.open" class="audit-mask" @click.self="close">
      <div class="audit-modal" role="dialog" aria-label="碳素流守恒审计">
        <div class="am-head">
          <div class="am-title">
            <Icon name="bolt" :size="15" />
            <span>碳素流守恒审计</span>
          </div>
          <button class="am-x" @click="close" title="关闭 (Esc)">✕</button>
        </div>
        <div class="am-body">
          <div class="am-row">
            <button class="am-run" @click="runAudit" :disabled="loadingA">{{ loadingA ? '计算中…' : '运行守恒审计' }}</button>
            <span class="am-hint">逐工序核对碳输入 = 排CO₂ + 固钢 + 入渣 + 捕集 + 产品携出</span>
          </div>
          <div v-if="auditErr" class="am-err">{{ auditErr }}</div>
          <div v-if="audit" class="am-table">
            <div class="am-th">
              <span>工序</span><span>碳输入</span><span>排CO₂</span><span>固钢</span>
              <span>入渣</span><span>捕集</span><span>产品碳</span><span>残差</span>
            </div>
            <div v-for="u in audit.units" :key="u.id" class="am-tr">
              <span>{{ u.name }}</span>
              <span>{{ fmt(u.carbon_in) }}</span>
              <span>{{ fmt(u.carbon_to_co2) }}</span>
              <span>{{ fmt(u.carbon_to_steel) }}</span>
              <span>{{ fmt(u.carbon_to_slag) }}</span>
              <span>{{ fmt(u.carbon_captured) }}</span>
              <span>{{ fmt(u.carbon_to_product) }}</span>
              <span :class="{ warn: Math.abs(u.residual) > 0.01 }">{{ fmt(u.residual) }}</span>
            </div>
            <div class="am-tr am-total">
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
          <div v-if="audit" class="am-note">{{ audit.note }}</div>
          <div v-if="audit && hasSankey" class="am-sankey">
            <div class="am-sankey-title">碳素流桑基图</div>
            <CarbonSankey />
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'
import { auditState, closeAuditDialog } from '../stores/audit'
import { api } from '../api/client'
import Icon from './Icon.vue'
import CarbonSankey from './CarbonSankey.vue'

const store = useSimStore()
const state = auditState

const audit = ref(null)
const auditErr = ref('')
const loadingA = ref(false)

const hasSankey = computed(() => !!(store.resultForView && store.resultForView.sankey && store.resultForView.sankey.nodes && store.resultForView.sankey.nodes.length))

function fmt(n) { return Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }

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

function close() { closeAuditDialog() }

watch(() => state.open, (v) => {
  if (v) nextTick(() => { if (!audit.value) runAudit() })
})
</script>

<style scoped>
.audit-mask { position: fixed; inset: 0; background: rgba(12,16,22,.42); z-index: 260;
  display: flex; align-items: center; justify-content: center; padding: 24px; }
.audit-modal { width: 560px; max-width: 100%; max-height: 86vh; overflow: auto;
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px; box-shadow: var(--shadow); }
.am-head { display: flex; align-items: center; gap: 14px; padding: 10px 14px; border-bottom: 1px solid var(--border);
  background: var(--panel-2); position: sticky; top: 0; }
.am-title { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--text); font-weight: 500; }
.am-x { margin-left: auto; background: transparent; border: none; color: var(--muted); font-size: 14px; cursor: pointer; padding: 2px 6px; border-radius: 5px; }
.am-x:hover { color: var(--text); background: var(--panel-3); }
.am-body { padding: 14px; }
.am-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.am-row label { font-size: 11px; color: var(--muted); flex: 0 0 auto; }
.am-run { background: var(--accent); color: #fff; border: 1px solid var(--accent); font-weight: 600; padding: 6px 14px; border-radius: 6px; cursor: pointer; }
.am-run:hover { background: var(--accent-d); }
.am-run:disabled { opacity: .6; cursor: default; }
.am-hint { color: var(--muted); font-size: 11px; }
.am-err { color: var(--red); font-size: 11px; margin: -4px 0 10px; }
.am-table { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 10px; }
.am-th, .am-tr { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr 1fr 1fr 0.9fr; gap: 0;
  font-size: 11px; padding: 5px 8px; align-items: center; }
.am-th { background: var(--panel-2); color: var(--muted); border-bottom: 1px solid var(--border); }
.am-tr { border-bottom: 1px solid var(--line); }
.am-tr:last-child { border-bottom: none; }
.am-tr span { font-variant-numeric: tabular-nums; white-space: nowrap; }
.am-tr.warn span:last-child { color: var(--yellow); }
.am-tr.am-total { background: var(--panel-3); font-weight: 500; }
.am-note { font-size: 10px; color: var(--muted); line-height: 1.6; background: var(--panel-2);
  border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; }
.am-sankey { margin-top: 10px; background: var(--panel-2); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px; }
.am-sankey-title { font-size: 11px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
</style>
