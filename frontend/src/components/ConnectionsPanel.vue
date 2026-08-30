<template>
  <div class="cn-wrap">
    <!-- 编辑表单（平台仅两条内置数据源：能碳一体机 MQTT + 模拟数据，无新建入口） -->
    <div v-if="formOpen" class="cn-form">
      <div class="cn-form-title">
        {{ t('编辑数据源') }}
        <span class="cn-form-type" :class="form.type">{{ t(typeLabel(form.type)) }}</span>
      </div>
      <label class="cn-fld">
        <span>{{ t('名称') }}</span>
        <input v-model="form.name" type="text" :placeholder="form.type === 'sim' ? t('能碳一体机') : t('模拟数据')" />
      </label>
      <label v-if="form.type === 'local'" class="cn-fld">
        <span>{{ t('模拟频率 (ms)') }}</span>
        <input v-model.number="form.interval" type="number" min="500" step="100" />
      </label>
      <p v-if="form.type === 'local'" class="cn-local-note">
        {{ t('模拟数据无需外部连接：按设定频率基于场景内传感器生成周期性波动读数，适合演示与离线调试。') }}
      </p>
      <p v-else-if="form.type === 'sim'" class="cn-local-note">
        {{ t('能碳一体机数据源：以 MQTT 形式订阅云端 Broker 采集盒子实时读数。Broker 地址与订阅主题随「能碳一体机管理」视图的前端配置自动就绪。') }}
      </p>

      <!-- 传感器字段对齐（模拟数据直接对应场景内传感器，无需映射；同一设备只能绑定一个数据源） -->
      <div v-if="form.type === 'sim'" class="cn-map">
        <div class="cn-map-head">
          <span class="cn-map-title">{{ t('传感器字段对齐') }}</span>
          <button class="cn-map-auto" @click="autoMatch" :title="t('依据最近收到的遥测字段自动匹配内部传感器')">
            <Icon name="bolt" :size="12" /> {{ t('自动匹配') }}
          </button>
        </div>
        <p class="cn-map-tip">
          {{ t('把盒子遥测字段名映射为场景内传感器/设备 id，使真实读数与场景对齐。') }}
          <b>{{ t('同一设备只能绑定一个数据源：已被其它数据源绑定的设备不可选。') }}</b>
        </p>
        <div v-if="lastFields.length" class="cn-map-detect">
          {{ t('已收到字段：') }}<code v-for="f in lastFields" :key="f">{{ f }}</code>
        </div>
        <div v-else class="cn-map-detect idle">
          {{ t('暂无遥测字段：连接成功后这里会显示外部字段，便于手动/自动对齐。') }}
        </div>
        <div v-if="!form.rows.length" class="cn-map-empty">{{ t('尚未配置映射') }}</div>
        <div v-for="(r, i) in form.rows" :key="i" class="cn-map-row">
          <input v-model="r.ext" type="text" class="cn-map-ext" :placeholder="t('外部字段名，如 weight')" />
          <span class="cn-map-arrow">→</span>
          <select v-model="r.int" class="cn-map-int">
            <option value="">{{ t('（不映射 / 忽略）') }}</option>
            <option v-for="d in deviceOptions" :key="d.id" :value="d.id" :disabled="isDeviceLocked(d.id, i)">{{ d.label }}{{ lockHint(d.id, i) }}</option>
          </select>
          <button class="x-btn danger" :title="t('删除该映射')" @click="form.rows.splice(i, 1)">✕</button>
        </div>
        <button class="cn-map-add" @click="form.rows.push({ ext: '', int: '' })">+ {{ t('添加映射') }}</button>
      </div>

      <div class="cn-form-actions">
        <button class="cn-save" @click="save">{{ t('保存') }}</button>
        <button class="cn-cancel" @click="formOpen = false">{{ t('取消') }}</button>
      </div>
    </div>

    <!-- 数据源列表 -->
    <div class="cn-list" @scroll="onScroll" :class="{ scrolling }">
      <div v-if="!store.dataSources.length" class="empty-hint">
        <p>{{ t('暂无数据源，刷新页面后会自动恢复内置数据源。') }}</p>
      </div>

      <div v-for="src in store.dataSources" :key="src.id" class="cn-card"
           :class="[src.type, { disabled: src.enabled === false, active: src.id === store.activeDataSourceId }]">
        <div class="cn-card-top">
          <span class="cn-mark" :class="src.type"></span>
          <span class="cn-card-name" :title="src.name || src.id">{{ src.name || src.id }}</span>
          <span class="cn-type" :class="src.type">{{ t(typeLabel(src.type)) }}</span>
          <span v-if="src.id === store.activeDataSourceId" class="cn-active">{{ t('活动') }}</span>
          <span class="cn-st" :class="statusClass(src.id)" :title="t(statusLabel(src.id))"></span>
        </div>

        <!-- 能碳一体机（MQTT）数据源：展示云端 Broker / 订阅 / 最近消息 -->
        <div v-if="src.type === 'sim'" class="cn-mqtt-detail">
          <div class="cn-mqtt-row">
            <span>{{ t('云端 Broker') }}</span>
            <code>{{ mqttBroker }}</code>
            <template v-if="store.mqttSource">
              <span class="cn-sep">·</span>
              <span>{{ t('已收') }} {{ store.mqttSource.message_count || 0 }} {{ t('条') }}</span>
            </template>
          </div>
          <div class="cn-mqtt-row" v-if="mqttTopics.length">
            <span>{{ t('订阅') }}</span>
            <code v-for="tp in mqttTopics" :key="tp">{{ tp }}</code>
          </div>
          <div v-if="mqttRecentMsg" class="cn-mqtt-msg">
            <span>{{ t('最近消息') }}</span>
            <code class="cn-mqtt-topic">{{ mqttRecentMsg.topic }}</code>
            <div class="cn-mqtt-payload">{{ mqttRecentMsg.payload }}</div>
          </div>
        </div>
        <div v-else-if="src.url" class="cn-card-url">{{ src.url }}</div>

        <div class="cn-card-sub">
          <span>{{ t(statusLabel(src.id)) }}</span>
          <template v-if="src.type === 'local'">
            <span class="cn-sep">·</span>
            <span>{{ t('每') }} {{ src.interval || 1000 }} ms {{ t('生成模拟读数') }}</span>
          </template>
          <template v-else-if="src.enabled !== false && store.lastFields[src.id]">
            <span class="cn-sep">·</span>
            <span>{{ t('遥测字段') }} {{ store.lastFields[src.id].length }} {{ t('个') }}</span>
          </template>
          <template v-if="src.mapping && Object.keys(src.mapping).length">
            <span class="cn-sep">·</span>
            <span>{{ t('已对齐') }} {{ Object.keys(src.mapping).length }} {{ t('项') }}</span>
          </template>
        </div>

        <div class="cn-card-ops">
          <label class="cn-switch" :title="t(src.enabled === false ? '启用' : '停用') + '「' + (src.name || src.id) + '」'">
            <input type="checkbox" :checked="src.enabled !== false" @change="store.toggleDataSource(src.id)" />
            <span class="cn-switch-track"></span>
          </label>
          <span class="cn-op-grow"></span>
          <button v-if="src.id !== store.activeDataSourceId" class="cn-op" @click="store.setActiveDataSource(src.id)">
            <Icon name="target" :size="11" /> {{ t('设为活动') }}
          </button>
          <button class="cn-op" @click="openEdit(src)" :title="t('编辑数据源配置')">
            <Icon name="pencil" :size="11" /> {{ t('编辑') }}
          </button>
          <button class="cn-op danger" @click="remove(src)" :title="t('删除该数据源')">
            <Icon name="trash" :size="11" /> {{ t('删除') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { t } from '../i18n'

const store = useSimStore()

// 平台仅保留两条内置数据源：能碳一体机（MQTT 云端）+ 模拟数据（本地）
const TYPE_META = {
  sim: { label: '云端 MQTT' },
  local: { label: '本地模拟' },
}
function typeLabel(x) { return TYPE_META[x] ? TYPE_META[x].label : x }

// MQTT 实时数据源状态（store.mqttSource 由 /api/realtime/source 轮询得到）
const mqttBroker = computed(() => {
  const s = store.mqttSource
  return s ? `${s.broker_host}:${s.broker_port}` : '—'
})
const mqttTopics = computed(() => (store.mqttSource && store.mqttSource.topics) || [])
const mqttRecentMsg = computed(() => {
  const s = store.mqttSource
  const recs = s && s.recent_messages
  return recs && recs.length ? recs[recs.length - 1] : null
})
const STATUS_META = {
  init: { label: '连接中' },
  open: { label: '已连接' },
  closed: { label: '已断开' },
  error: { label: '错误' },
}
function statusLabel(id) {
  const st = store.sourceStatus[id]
  return st ? (STATUS_META[st] ? STATUS_META[st].label : st) : '未连接'
}
function statusClass(id) {
  const st = store.sourceStatus[id]
  return st && STATUS_META[st] ? st : ''
}

// ---- 编辑表单 ----
const formOpen = ref(false)
const editingId = ref(null)
const form = reactive({ name: '', type: 'sim', url: '', interval: 1000, enabled: true, rows: [] })

function openEdit(src) {
  editingId.value = src.id
  Object.assign(form, {
    name: src.name || '',
    type: src.type || 'sim',
    url: src.url || '',
    interval: src.interval || 1000,
    enabled: src.enabled !== false,
  })
  form.rows = Object.entries(src.mapping || {}).map(([ext, int]) => ({ ext, int }))
  formOpen.value = true
}
// 保存：把 rows 组装为 mapping（外部字段 -> 内部设备 id），同一设备只保留一次绑定；
// 与其它数据源冲突的项由 store 校验后自动跳过
function save() {
  if (!form.name) form.name = form.type === 'sim' ? t('能碳一体机') : t('模拟数据')
  const mapping = {}
  for (const r of form.rows) {
    const ext = (r.ext || '').trim()
    if (!ext || !r.int) continue
    if (Object.values(mapping).includes(r.int)) continue
    mapping[ext] = r.int
  }
  const payload = { name: form.name, type: form.type, url: form.url, interval: form.interval, enabled: form.enabled, mapping }
  store.updateDataSource(editingId.value, payload)
  store.showToast(t('已更新数据源「{name}」并重新连接', { name: payload.name }), 'success')
  formOpen.value = false
}
async function remove(src) {
  if (!(await store.confirm({
    title: t('删除数据源'),
    message: t('确认删除数据源「{name}」？该源为平台内置数据源，删除后刷新页面会自动恢复。', { name: src.name || src.id }),
    okText: t('删除'), danger: true,
  }))) return
  store.removeDataSource(src.id)
}

// ---- 传感器字段对齐 ----
// 内部传感器选项（场景内真实设备）
const deviceOptions = computed(() =>
  store.allDevices.map((d) => ({
    id: d.id,
    label: `${d.label} · ${d.unitName || d.unitType || ''}${d.unit ? ' (' + d.unit + ')' : ''}`,
  }))
)
// 该数据源最近收到的外部字段
const lastFields = computed(() => {
  if (!editingId.value) return []
  return store.lastFields[editingId.value] || []
})
// 同一设备只能绑定一个数据源：已被其它数据源绑定 / 本表单其它行已选时禁用选项
function isDeviceLocked(devId, rowIdx) {
  if (store.isDeviceBoundByOther(devId, editingId.value)) return true
  return form.rows.some((r, j) => j !== rowIdx && r.int === devId)
}
function lockHint(devId, rowIdx) {
  const owner = store.isDeviceBoundByOther(devId, editingId.value)
  if (owner) return t('（已被「{owner}」绑定）', { owner })
  if (form.rows.some((r, j) => j !== rowIdx && r.int === devId)) return t('（本表单已选）')
  return ''
}
// 自动匹配：把最近收到的外部字段与内部传感器按 id/名称 精确或包含匹配（跳过已被其它数据源绑定的设备）
function autoMatch() {
  const fields = lastFields.value
  if (!fields.length) {
    store.showToast(t('尚未收到该数据源的遥测字段，请先确保连接成功'), 'warn')
    return
  }
  const devs = store.allDevices
  let matched = 0
  for (const f of fields) {
    if (form.rows.some((r) => r.ext === f)) continue
    const hit =
      devs.find((d) => d.id === f) ||
      devs.find((d) => d.label === f) ||
      devs.find((d) => d.id.includes(f) || f.includes(d.id)) ||
      devs.find((d) => d.label.includes(f) || f.includes(d.label))
    if (hit && store.isDeviceBoundByOther(hit.id, editingId.value)) continue
    form.rows.push({ ext: f, int: hit ? hit.id : '' })
    if (hit) matched++
  }
  store.showToast(t('已按外部字段自动匹配：成功 {n} 项，其余可手动指定', { n: matched }), matched ? 'success' : 'info')
}

// 滚动条显隐
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}
</script>

<style scoped>
.cn-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ---- 编辑表单 ---- */
.cn-form { flex: 0 0 auto; padding: 10px; border-bottom: 1px solid var(--border); background: var(--panel-2); max-height: 55%; overflow-y: auto; }
.cn-form-title { font-size: 11.5px; font-weight: 700; letter-spacing: .03em; margin-bottom: 8px; color: var(--text); display: flex; align-items: center; gap: 6px; }
.cn-form-type { font-size: 9px; letter-spacing: .08em; padding: 1px 6px; border-radius: 0; border: 1px solid currentColor; text-transform: uppercase; font-weight: 600; }
.cn-form-type.sim { color: #2e6fdb; }
.cn-form-type.local { color: #e0a629; }
.cn-fld { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
.cn-fld > span { font-size: 10.5px; color: var(--muted); }
.cn-fld input, .cn-fld select {
  border: 1px solid var(--border); border-radius: 0; background: var(--panel);
  color: var(--text); font-size: 11.5px; padding: 4px 7px; outline: none; min-width: 0;
}
.cn-fld input:focus, .cn-fld select:focus { border-color: var(--accent-d); }
.cn-local-note { margin: 0 0 8px; font-size: 10.5px; color: var(--muted); line-height: 1.6; }

/* ---- 字段对齐 ---- */
.cn-map { margin-top: 2px; border: 1px dashed var(--border); border-radius: 0; padding: 8px; }
.cn-map-head { display: flex; align-items: center; gap: 6px; }
.cn-map-title { font-size: 11px; font-weight: 600; color: var(--text); }
.cn-map-auto {
  margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
  font-size: 10.5px; color: var(--accent-d); background: transparent; border: 1px solid var(--accent-d);
  border-radius: 0; padding: 2px 7px; cursor: pointer;
}
.cn-map-auto:hover { background: var(--accent-l); }
.cn-map-tip { margin: 5px 0 6px; font-size: 10px; color: var(--muted); line-height: 1.6; }
.cn-map-tip b { color: var(--text); }
.cn-map-detect { margin-bottom: 6px; font-size: 10px; color: var(--accent2); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.cn-map-detect code { background: var(--panel); border: 1px solid var(--border); border-radius: 0; padding: 1px 5px; font-size: 10px; }
.cn-map-detect.idle { color: var(--faint); }
.cn-map-empty { font-size: 10.5px; color: var(--faint); padding: 4px 0; }
.cn-map-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.cn-map-ext { flex: 0 0 42%; min-width: 0; border: 1px solid var(--border); border-radius: 0; background: var(--panel); color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; }
.cn-map-ext:focus { border-color: var(--accent-d); }
.cn-map-arrow { flex: 0 0 auto; color: var(--faint); font-size: 11px; }
.cn-map-int { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 0; background: var(--panel); color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; }
.cn-map-int:focus { border-color: var(--accent-d); }
.cn-map-int option:disabled { color: var(--faint); }
.cn-map-add {
  font-size: 10.5px; color: var(--muted); background: transparent; border: 1px dashed var(--border);
  border-radius: 0; padding: 3px 8px; cursor: pointer; margin-top: 2px;
}
.cn-map-add:hover { color: var(--accent-d); border-color: var(--accent-d); }
.cn-form-actions { display: flex; gap: 8px; margin-top: 10px; justify-content: flex-end; }
.cn-save { font-size: 11px; color: #fff; background: var(--accent); border: none; border-radius: 0; padding: 4px 16px; cursor: pointer; letter-spacing: .05em; }
.cn-save:hover { filter: brightness(1.06); }
.cn-cancel { font-size: 11px; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: 0; padding: 4px 12px; cursor: pointer; }
.cn-cancel:hover { color: var(--text); }

/* ---- 能碳一体机（MQTT）数据源详情 ---- */
.cn-mqtt-detail { margin-top: 7px; padding: 7px 8px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 0; display: flex; flex-direction: column; gap: 5px; }
.cn-mqtt-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--muted); flex-wrap: wrap; }
.cn-mqtt-row code {
  background: var(--panel); border: 1px solid var(--border); border-radius: 0;
  padding: 1px 6px; font-size: 10px; color: var(--accent2);
}
.cn-mqtt-msg { display: flex; align-items: flex-start; gap: 6px; font-size: 10px; color: var(--muted); flex-direction: column; }
.cn-mqtt-msg .cn-mqtt-topic { background: var(--panel); border: 1px solid var(--border); border-radius: 0; padding: 1px 6px; color: var(--accent2); }
.cn-mqtt-payload {
  width: 100%; max-height: 56px; overflow: hidden; font-size: 10px; line-height: 1.5;
  color: var(--faint); background: var(--panel); border-radius: 0; padding: 4px 6px;
  word-break: break-all; font-family: var(--mono, ui-monospace, monospace);
}

/* ---- 列表（包豪斯：几何直角、单色块、无圆角与阴影） ---- */
.cn-list { flex: 1; min-height: 0; overflow-y: auto; padding: 10px 10px 14px; }
.cn-list.scrolling { scrollbar-width: thin; }
.cn-card {
  position: relative; border: 1px solid var(--border); border-left-width: 3px;
  border-radius: 0; padding: 9px 11px 10px; margin-bottom: 9px; background: var(--panel);
  transition: border-color .15s, opacity .2s;
}
.cn-card.sim { border-left-color: #2e6fdb; }
.cn-card.local { border-left-color: #e0a629; }
.cn-card:hover { border-color: var(--accent-l); }
.cn-card.active { border-color: var(--accent-d); }
.cn-card.disabled { opacity: .45; }
.cn-card.disabled:hover { opacity: .75; }
.cn-card-top { display: flex; align-items: center; gap: 7px; }
/* 几何标记：能碳一体机=方、模拟=圆（包豪斯基本形） */
.cn-mark { flex: 0 0 auto; width: 10px; height: 10px; }
.cn-mark.sim { background: #2e6fdb; }
.cn-mark.local { border-radius: 50%; background: #e0a629; }
.cn-card-name { font-size: 12.5px; font-weight: 700; color: var(--text); letter-spacing: .02em; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cn-type { flex: 0 0 auto; font-size: 9px; letter-spacing: .08em; padding: 1px 6px; border-radius: 0; border: 1px solid currentColor; text-transform: uppercase; }
.cn-type.sim { color: #2e6fdb; }
.cn-type.local { color: #e0a629; }
.cn-active { flex: 0 0 auto; font-size: 9px; letter-spacing: .1em; padding: 1px 6px; border-radius: 0; border: 1px solid var(--accent-d); color: var(--accent-d); text-transform: uppercase; }
/* 状态：几何方块，实心=已连接 */
.cn-st { flex: 0 0 auto; width: 8px; height: 8px; margin-left: auto; border: 1px solid #b3b3b3; border-radius: 0; }
.cn-st.open { background: #3a9d5d; border-color: #3a9d5d; }
.cn-st.init { border-color: #c9a24b; }
.cn-st.error { background: #d9534f; border-color: #d9534f; }
.cn-st.closed { border-color: #b3b3b3; }
.cn-card-url { margin-top: 5px; font-size: 10.5px; color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.cn-card-sub { margin-top: 5px; display: flex; gap: 6px; align-items: center; font-size: 10.5px; color: var(--muted); flex-wrap: wrap; }
.cn-sep { color: var(--border); }
.cn-card-ops { margin-top: 8px; display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--border); padding-top: 7px; }
.cn-op-grow { flex: 1; }
/* 方形开关 */
.cn-switch { position: relative; display: inline-flex; cursor: pointer; }
.cn-switch input { display: none; }
.cn-switch-track { width: 28px; height: 14px; border-radius: 0; background: var(--border); border: 1px solid var(--border); transition: background .15s, border-color .15s; position: relative; }
.cn-switch-track::after { content: ''; position: absolute; left: 2px; top: 2px; width: 8px; height: 8px; border-radius: 0; background: #fff; transition: left .15s; }
.cn-switch input:checked + .cn-switch-track { background: var(--accent); border-color: var(--accent); }
.cn-switch input:checked + .cn-switch-track::after { left: 16px; }
/* 文字操作：无按钮底，hover 强调色 */
.cn-op { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; color: var(--muted); background: transparent; border: none; padding: 2px 3px; cursor: pointer; letter-spacing: .02em; }
.cn-op:hover { color: var(--accent-d); }
.cn-op.danger:hover { color: #d9534f; }
.empty-hint { padding: 18px 12px; color: var(--faint); font-size: 11.5px; line-height: 1.8; text-align: center; }
.empty-hint p { margin: 0; }
</style>
