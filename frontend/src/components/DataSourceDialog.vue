<template>
  <div class="ds-mask" @click.self="$emit('close')">
    <div class="ds-modal" role="dialog" aria-modal="true" :aria-label="t('连接数据源')">
      <div class="ds-head">
        <span class="ds-title">{{ t('连接数据源') }}</span>
        <button class="x-btn lg" @click="$emit('close')" :aria-label="t('关闭')">×</button>
      </div>

      <div class="ds-body">
        <p class="ds-tip">
          {{ t('平台内置两条数据源：') }}<b>{{ t('能碳一体机') }}</b>{{ t('以 MQTT 形式订阅云端 Broker 采集盒子实时读数（Broker 配置在「能碳一体机管理」视图维护）；') }}
          <b>{{ t('模拟数据') }}</b>{{ t('无需连接，按频率基于场景内传感器生成波动读数，适合演示与离线调试。') }}
          {{ t('多条数据源可同时启用，但同一设备只能绑定一个数据源。') }}
        </p>

        <!-- 当前编辑的数据源（编辑活动源；如需切换请回到「连接」面板） -->
        <div class="ds-field">
          <label>{{ t('当前数据源') }}</label>
          <div class="ds-current">
            <span class="ds-mark" :class="form.type"></span>
            <span class="ds-current-name">{{ form.name || (form.type === 'sim' ? t('能碳一体机') : t('模拟数据')) }}</span>
            <span class="ds-type-tag" :class="form.type">{{ form.type === 'sim' ? t('云端 MQTT') : t('本地模拟') }}</span>
          </div>
        </div>

        <div class="ds-field" v-if="form.type === 'local'">
          <label>{{ t('模拟频率 (毫秒)') }}</label>
          <input class="ds-input" type="number" min="500" step="500" v-model.number="form.interval" />
        </div>

        <div class="ds-field">
          <label>{{ t('显示名称（可选）') }}</label>
          <input class="ds-input" v-model.trim="form.name" :placeholder="form.type === 'sim' ? t('能碳一体机') : t('模拟数据')" />
        </div>

        <!-- 传感器字段对齐（模拟数据直接对应场景内传感器，无需映射；同一设备只能绑定一个数据源） -->
        <div class="ds-field" v-if="form.type !== 'local'">
          <label>{{ t('传感器字段对齐') }}
            <button class="ds-map-auto" type="button" @click="autoMatch">{{ t('自动匹配') }}</button>
          </label>
          <p class="ds-map-tip">
            {{ t('把盒子遥测字段名映射为场景内传感器/设备 id，使真实读数与场景对齐。') }}
            <b>{{ t('同一设备只能绑定一个数据源：已被其它数据源绑定的设备不可选。') }}</b>
          </p>
          <div class="ds-map-detect">
            <template v-if="lastFields.length">
              {{ t('该源已收到字段：') }}<code v-for="f in lastFields" :key="f">{{ f }}</code>
            </template>
            <template v-else>{{ t('连接成功后此处会显示收到的外部字段，便于对齐') }}</template>
          </div>
          <div v-if="!form.rows.length" class="ds-map-empty">{{ t('尚未配置映射') }}</div>
          <div v-for="(r, i) in form.rows" :key="i" class="ds-map-row">
            <input v-model="r.ext" type="text" class="ds-input ds-map-ext" :placeholder="t('外部字段名，如 weight')" />
            <span class="ds-map-arrow">→</span>
            <select v-model="r.int" class="ds-input ds-map-int">
              <option value="">{{ t('（不映射 / 忽略）') }}</option>
              <option v-for="d in deviceOptions" :key="d.id" :value="d.id" :disabled="isDeviceLocked(d.id, i)">{{ d.label }}{{ lockHint(d.id, i) }}</option>
            </select>
            <button class="ds-map-del" type="button" :title="t('删除该映射')" @click="form.rows.splice(i, 1)">✕</button>
          </div>
          <button class="ds-map-add" type="button" @click="form.rows.push({ ext: '', int: '' })">+ {{ t('添加映射') }}</button>
        </div>

        <div class="ds-actions">
          <button class="ds-btn" :disabled="!canTest" @click="testConn">{{ t('测试连接') }}</button>
          <span class="ds-test" :class="testClass">{{ testText }}</span>
          <span class="sp"></span>
          <button class="ds-btn ghost" @click="$emit('close')">{{ t('取消') }}</button>
          <button class="ds-btn primary" :disabled="!canApply" @click="apply">{{ t('保存并连接') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
const emit = defineEmits(['close'])

// 平台仅两条内置数据源：能碳一体机（sim / MQTT 云端）+ 模拟数据（local）。
// 对话框直接编辑当前活动数据源，无「数据源」下拉与新建入口。
const form = reactive({ type: 'sim', url: '', interval: 1000, name: '', rows: [] })

const testText = ref('')
const testState = ref('') // '' | 'ok' | 'err' | 'wait'

const canTest = computed(() => form.type === 'sim' || form.type === 'local')
const canApply = computed(() => form.type === 'sim' || form.type === 'local')
const testClass = computed(() => 'ds-test' + (testState.value ? ' ' + testState.value : ''))

// 内部传感器选项（场景内真实设备）
const deviceOptions = computed(() =>
  store.allDevices.map((d) => ({
    id: d.id,
    label: `${d.label} · ${d.unitName || d.unitType || ''}${d.unit ? ' (' + d.unit + ')' : ''}`,
  }))
)
// 该数据源最近收到的外部字段
const lastFields = computed(() => store.lastFields[form.type] || [])

// 初始化：载入当前活动数据源配置（sim / local 均为内置且固定存在）
function loadFromSource() {
  const src = store.dataSources.find((s) => s.id === form.type) || store.dataSources[0] || null
  form.rows = []
  if (!src) { Object.assign(form, { type: 'sim', url: '', interval: 1000, name: '' }); return }
  Object.assign(form, {
    type: src.type || 'sim',
    url: src.url || '',
    interval: src.interval || 1000,
    name: src.name || '',
  })
  form.rows = Object.entries(src.mapping || {}).map(([ext, int]) => ({ ext, int }))
}
form.type = store.activeDataSourceId === 'local' ? 'local' : 'sim'
loadFromSource()

// 同一设备只能绑定一个数据源：已被其它数据源绑定 / 本表单其它行已选时禁用选项
function isDeviceLocked(devId, rowIdx) {
  if (store.isDeviceBoundByOther(devId, form.type)) return true
  return form.rows.some((r, j) => j !== rowIdx && r.int === devId)
}
function lockHint(devId, rowIdx) {
  const owner = store.isDeviceBoundByOther(devId, form.type)
  if (owner) return t('（已被「{owner}」绑定）', { owner })
  if (form.rows.some((r, j) => j !== rowIdx && r.int === devId)) return t('（本表单已选）')
  return ''
}

function testConn() {
  testState.value = 'wait'
  testText.value = t('连接中…')
  if (form.type === 'local') {
    // 模拟数据无需连接，检查场景内是否有可用传感器即可
    const devs = store.allDevices
    testState.value = 'ok'
    testText.value = devs.length ? t('模拟数据可用（{n} 个传感器）', { n: devs.length }) : t('暂无可模拟的传感器（请先加载场景）')
    return
  }
  // 能碳一体机（MQTT）：后端已订阅云端 Broker，检测后端健康即可
  fetch('/api/health').then((r) => {
    if (r.ok) { testState.value = 'ok'; testText.value = t('能碳一体机 MQTT 数据可用') }
    else { testState.value = 'err'; testText.value = t('后端不可用 ({status})', { status: r.status }) }
  }).catch(() => { testState.value = 'err'; testText.value = t('无法连接后端') })
}

// 自动匹配：把最近收到的外部字段与内部传感器按 id/名称 精确或包含匹配（跳过已被其它数据源绑定的设备）
function autoMatch() {
  const fields = lastFields.value
  if (!fields.length) { store.showToast(t('尚未收到该数据源的遥测字段，请先测试连接'), 'warn'); return }
  const devs = store.allDevices
  let matched = 0
  for (const f of fields) {
    if (form.rows.some((r) => r.ext === f)) continue
    const hit =
      devs.find((d) => d.id === f) ||
      devs.find((d) => d.label === f) ||
      devs.find((d) => d.id.includes(f) || f.includes(d.id)) ||
      devs.find((d) => d.label.includes(f) || f.includes(d.label))
    if (hit && store.isDeviceBoundByOther(hit.id, form.type)) continue
    form.rows.push({ ext: f, int: hit ? hit.id : '' })
    if (hit) matched++
  }
  store.showToast(t('自动匹配成功 {n} 项，其余可手动指定', { n: matched }), matched ? 'success' : 'info')
}

function apply() {
  const mapping = {}
  for (const r of form.rows) {
    const ext = (r.ext || '').trim()
    if (!ext || !r.int) continue
    if (Object.values(mapping).includes(r.int)) continue
    mapping[ext] = r.int
  }
  const payload = {
    type: form.type,
    url: form.url,
    interval: Number(form.interval) || 1000,
    name: form.name || (form.type === 'sim' ? t('能碳一体机') : t('模拟数据')),
    mapping,
  }
  store.updateDataSource(form.type, payload)
  store.showToast(t('数据源「{name}」已更新并重新连接', { name: payload.name }), 'success')
  emit('close')
}
</script>

<style scoped>
.ds-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ds-modal { width: 520px; max-width: 94vw; max-height: 88vh; display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--border); border-radius: 0;
  box-shadow: 0 18px 50px rgba(0,0,0,.28); font-family: var(--ui); color: var(--text); }
.ds-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.ds-title { font-size: 14px; font-weight: 700; letter-spacing: .02em; }
.ds-body { padding: 14px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.ds-tip { font-size: 10px; color: var(--muted); line-height: 1.7; margin: 0; }
.ds-tip b { color: var(--text); }
.ds-field { display: flex; flex-direction: column; gap: 6px; }
.ds-field label { font-size: 10px; font-weight: 600; color: var(--muted); display: flex; align-items: center; gap: 8px; }
.ds-current { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--border); border-left-width: 3px; border-radius: 0; background: var(--bar); }
.ds-mark { flex: 0 0 auto; width: 10px; height: 10px; }
.ds-mark.sim { background: #2e6fdb; }
.ds-mark.local { border-radius: 50%; background: #e0a629; }
.ds-current-name { font-size: 12.5px; font-weight: 700; color: var(--text); }
.ds-type-tag { flex: 0 0 auto; margin-left: auto; font-size: 9px; letter-spacing: .08em; padding: 1px 6px; border-radius: 0; border: 1px solid currentColor; text-transform: uppercase; }
.ds-type-tag.sim { color: #2e6fdb; }
.ds-type-tag.local { color: #e0a629; }
.ds-input { padding: 7px 10px; border: 1px solid var(--border); border-radius: 0; background: var(--bar); color: var(--text); font-size: 12px; font-family: var(--ui); }
.ds-input:focus { outline: none; border-color: var(--accent-d); }
.ds-map-auto { margin-left: auto; font-size: 10px; color: var(--accent-d); background: transparent; border: 1px solid var(--accent-d);
  border-radius: 0; padding: 2px 8px; cursor: pointer; }
.ds-map-auto:hover { background: var(--accent-l); }
.ds-map-tip { margin: 0; font-size: 10px; color: var(--muted); line-height: 1.6; }
.ds-map-tip b { color: var(--text); }
.ds-map-detect { font-size: 10px; color: var(--accent2); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.ds-map-detect code { background: var(--bar); border: 1px solid var(--border); border-radius: 0; padding: 1px 5px; font-size: 10px; }
.ds-map-empty { font-size: 10.5px; color: var(--faint); padding: 2px 0; }
.ds-map-row { display: flex; align-items: center; gap: 6px; }
.ds-map-ext { flex: 0 0 38%; min-width: 0; }
.ds-map-arrow { color: var(--faint); font-size: 11px; flex: 0 0 auto; }
.ds-map-int { flex: 1; min-width: 0; }
.ds-map-int option:disabled { color: var(--faint); }
.ds-map-del { flex: 0 0 auto; width: 18px; height: 18px; display: grid; place-items: center; border: none; border-radius: 0;
  background: transparent; color: var(--faint); font-size: 9px; cursor: pointer; padding: 0; }
.ds-map-del:hover { color: #c0392b; background: rgba(192,57,43,.1); }
.ds-map-add { align-self: flex-start; font-size: 10.5px; color: var(--muted); background: transparent; border: 1px dashed var(--border);
  border-radius: 0; padding: 3px 9px; cursor: pointer; }
.ds-map-add:hover { color: var(--accent-d); border-color: var(--accent-d); }
.ds-actions { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
.ds-actions .sp { flex: 1; }
.ds-test { font-size: 10px; color: var(--muted); }
.ds-test.ok { color: #2e8b57; }
.ds-test.err { color: #c0392b; }
.ds-test.wait { color: var(--accent-d); }
.ds-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 0; background: var(--bar); cursor: pointer; font-size: 12px; color: var(--text); }
.ds-btn:hover { border-color: var(--accent-d); }
.ds-btn.primary { background: var(--accent); border-color: var(--accent-d); color: #fff; }
.ds-btn.primary:hover { background: var(--accent-d); }
.ds-btn.ghost { background: transparent; }
.ds-btn:disabled { color: var(--faint); cursor: default; border-color: var(--border); }
</style>
