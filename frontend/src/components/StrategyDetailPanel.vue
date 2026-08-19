<template>
  <div class="strategy-detail">
    <template v-if="strategy">
      <!-- 内置预置策略：只读展示 -->
      <template v-if="strategy.source === 'preset'">
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>名称</span><b>{{ strategy.name }} <span class="tag">内置</span></b></div></div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        </CollapseSection>
        <CollapseSection title="数值调整" tone="amber" :show-more="false">
        <div class="note">该策略为系统内置，点击「策略仿真」进入仿真模式解析测试。</div>
        <div class="actions">
          <button class="x" :disabled="store.busy" @click="runSim">策略仿真</button>
        </div>
        </CollapseSection>
      </template>

      <!-- 工艺策略（某工艺对应的绿色策略）：只读展示 + 启用/停用 + 查看工艺 -->
      <template v-else-if="strategy.source === 'green'">
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>名称</span><b>{{ strategy.name }} <span class="tag">工艺策略</span></b></div></div>
        <div class="card">
          <div class="kv2"><span>所属工艺</span><b>{{ strategy.processLabel }}</b></div>
        </div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        <div class="card" v-if="strategy.saving || strategy.carbon">
          <div class="kv2" v-if="strategy.saving"><span>节能效果</span><b>{{ strategy.saving }}</b></div>
          <div class="kv2" v-if="strategy.carbon"><span>减碳效果</span><b>{{ strategy.carbon }} kgCO₂/t</b></div>
        </div>
        <div class="card" v-if="strategy.tags && strategy.tags.length">
          <div class="tag-row">
            <span v-for="t in strategy.tags" :key="t" class="tag">{{ t }}</span>
          </div>
        </div>
        </CollapseSection>
        <CollapseSection title="启用状态" tone="green" :show-more="false">
        <div class="card toggle-card">
          <span class="muted">{{ strategy.enabled ? '该策略已在对应工艺中启用' : '该策略未启用' }}</span>
          <button class="x" :class="{ on: strategy.enabled }" @click="toggleGreen">
            {{ strategy.enabled ? '已启用' : '启用策略' }}
          </button>
        </div>
        <button class="btn-mini" @click="goProcess">查看工艺属性</button>
        </CollapseSection>
      </template>

      <!-- 自定义策略：可编辑 -->
      <template v-else>
        <CollapseSection title="策略名称" tone="blue" :show-more="false">
        <div class="card"><input v-model="nameDraft" class="inp" @change="markDirty" /></div>
        </CollapseSection>
        <CollapseSection title="来源" tone="teal" :show-more="false">
        <div class="card">
          <span class="tag">{{ strategy.applied ? '已应用' : '自定义' }}</span>
          <span class="muted src-tip">仿真模式下保存</span>
        </div>
        </CollapseSection>
        <CollapseSection v-if="strategy.description" title="描述" tone="teal" :show-more="false">
        <div class="card">
          <textarea v-model="descDraft" class="inp" rows="2" @change="markDirty"></textarea>
        </div>
        </CollapseSection>

        <!-- 数值调整（可编辑） -->
        <CollapseSection title="数值调整" tone="amber" :show-more="false">
        <div v-if="opsDraft.length" class="ops">
          <div v-for="(op, i) in opsDraft" :key="i" class="op-row">
            <div class="op-head">
              <span class="op-note">{{ opNote(op) }}</span>
              <span class="op-kind">{{ op.action === 'set_param' ? '参数' : op.action === 'apply_tech' ? '技术' : '操作' }}</span>
            </div>
            <div v-if="op.action === 'set_param'" class="op-edit">
              <span class="op-label">{{ op.target }} {{ opParamLabel(op) }}</span>
              <input v-model.number="op.value" type="number" class="inp num" @change="markDirty" />
              <span class="op-unit">{{ opUnit(op) }}</span>
            </div>
            <div v-else class="op-static muted">{{ opNote(op) }}</div>
          </div>
        </div>
        <div v-else class="note">该策略暂无数值调整项。</div>

        <div class="actions">
          <button class="x" :disabled="store.busy" @click="save">保存修改</button>
          <button class="x" :disabled="store.busy" @click="runSim">策略仿真</button>
        </div>
        </CollapseSection>
      </template>
    </template>
    <div v-else class="empty">未选择策略，请先在左侧「策略」中选择。</div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useSimStore, EDITABLE_PARAMS } from '../stores/sim'
import CollapseSection from './CollapseSection.vue'

const store = useSimStore()

const strategy = computed(() => store.selectedStrategy)
const nameDraft = ref('')
const descDraft = ref('')
const opsDraft = ref([])

watch(strategy, (s) => {
  nameDraft.value = s ? s.name || '' : ''
  descDraft.value = s ? s.description || '' : ''
  opsDraft.value = s && s.ops ? JSON.parse(JSON.stringify(s.ops)) : []
}, { immediate: true })

function opParamLabel(op) {
  const u = op.target
  const p = op.param
  if (!u || !p) return p || ''
  // 从参数元数据中查找该工序参数的显示名（label），找不到则回退原始 key
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.label || p
  }
  return p
}
function opUnit(op) {
  const p = op.param
  if (!p) return ''
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.unit || ''
  }
  return ''
}
function opNote(op) {
  return op.note || (op.action === 'set_param' ? `${op.target || ''} ${op.param || ''} = ${op.value}` : op.action || '')
}
function markDirty() {}

async function save() {
  if (!strategy.value) return
  await store.updateStrategy(strategy.value.id, {
    name: nameDraft.value.trim() || '未命名策略',
    description: descDraft.value,
    ops: opsDraft.value,
  })
}
function runSim() {
  if (!strategy.value) return
  store.runStrategySimulation(strategy.value.id)
}
// 工艺策略：跳转到对应工艺的属性面板
function goProcess() {
  if (!strategy.value) return
  store.selectAssetType(strategy.value.processType)
}
// 工艺策略：切换启用/停用
function toggleGreen() {
  if (!strategy.value) return
  store.toggleGreenStrategy(strategy.value.processType, strategy.value.sid)
  const on = store.greenStrategiesFor(strategy.value.processType).includes(strategy.value.sid)
  store.toast = on ? `已启用策略「${strategy.value.name}」` : `已停用策略「${strategy.value.name}」`
}
</script>

<style scoped>
.strategy-detail { padding: 2px 0; }
.inp { width: 100%; box-sizing: border-box; background: var(--panel-2); border: 1px solid var(--line); color: var(--text); border-radius: 3px; padding: 4px 8px; font-size: 11px; }
.inp.num { width: 90px; text-align: right; flex: 0 0 auto; padding: 4px 8px; }
textarea.inp { resize: vertical; font-family: inherit; line-height: 1.5; }
.tag { display: inline-block; font-size: 10px; color: var(--accent2); border: 1px solid var(--line); border-radius: 3px; padding: 1px 6px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.toggle-card { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.src-tip { margin-left: 8px; }
.toggle-card .x.on { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; border: none; }
.btn-mini { flex: 0 0 auto; font-size: 11px; padding: 3px 9px; border-radius: 3px; background: var(--panel-2); color: var(--accent2); border: 1px solid var(--line); cursor: pointer; margin-top: 8px; }
.btn-mini:hover { border-color: var(--accent2); }
.ops { display: flex; flex-direction: column; gap: 8px; }
.op-row { border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; background: var(--panel-2); }
.op-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.op-note { font-size: 11px; color: var(--text); }
.op-kind { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 6px; }
.op-edit { display: flex; align-items: center; gap: 8px; }
.op-label { flex: 1; font-size: 11px; color: var(--muted); }
.op-unit { font-size: 11px; color: var(--muted); }
.op-static { font-size: 11px; }
.actions { display: flex; gap: 8px; margin-top: 14px; }
.actions .x { flex: 1; padding: 9px 0; font-size: 12px; }
</style>
