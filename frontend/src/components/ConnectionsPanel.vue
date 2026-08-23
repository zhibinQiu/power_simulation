<template>
  <div class="cn-wrap">
    <div class="cn-head">
      <div class="cn-head-row">
        <Icon name="database" :size="15" class="cn-head-ic" />
        <span class="cn-title">数据源</span>
        <span class="cn-badge">{{ store.dataSources.length }}</span>
      </div>
      <button class="cn-new" @click="openNew">
        <Icon name="newFile" :size="13" /> 新建数据源
      </button>
    </div>

    <!-- MQTT 实时数据源状态（平台默认数据源：后端订阅云端 Broker 获取真实设备读数，参照参考项目 yunduan1 数据链路） -->
    <div class="cn-mqtt" :class="{ on: mqttConnected }">
      <div class="cn-mqtt-head">
        <span class="cn-mqtt-title">Mqtt 实时数据源</span>
        <span class="cn-mqtt-status" :class="{ on: mqttConnected }">{{ mqttStatusText }}</span>
      </div>
      <div class="cn-mqtt-row">
        <span>Broker</span>
        <code>{{ mqttBroker }}</code>
        <template v-if="store.mqttSource">
          <span class="cn-sep">·</span>
          <span>已收 {{ store.mqttSource.message_count || 0 }} 条</span>
        </template>
      </div>
      <div class="cn-mqtt-row" v-if="mqttTopics.length">
        <span>订阅</span>
        <code v-for="t in mqttTopics" :key="t">{{ t }}</code>
      </div>
      <div v-if="mqttRecentMsg" class="cn-mqtt-msg">
        <span>最近消息</span>
        <code class="cn-mqtt-topic">{{ mqttRecentMsg.topic }}</code>
        <div class="cn-mqtt-payload">{{ mqttRecentMsg.payload }}</div>
      </div>
      <div class="cn-mqtt-note">设备读数由后端订阅 MQTT 获取（Broker 配置在「能碳一体机管理」视图前端配置），不再生成模拟数据。</div>
    </div>

    <!-- 新建 / 编辑表单 -->
    <div v-if="formOpen" class="cn-form">
      <div class="cn-form-title">{{ editingId ? '编辑数据源' : '新建数据源' }}</div>
      <label class="cn-fld">
        <span>名称</span>
        <input v-model="form.name" type="text" placeholder="如：1# 高炉 DCS" />
      </label>
      <label class="cn-fld">
        <span>类型</span>
        <select v-model="form.type">
          <option value="sim">Mqtt 实时数据</option>
          <option value="ws">WebSocket</option>
          <option value="http">HTTP 轮询</option>
        </select>
      </label>
      <label v-if="form.type !== 'sim'" class="cn-fld">
        <span>{{ form.type === 'ws' ? 'WebSocket 地址' : 'HTTP 地址' }}</span>
        <input v-model="form.url" type="text" :placeholder="form.type === 'ws' ? 'ws://主机:端口/…' : 'http://主机:端口/telemetry'" />
      </label>
      <label v-if="form.type === 'http'" class="cn-fld">
        <span>轮询间隔 (ms)</span>
        <input v-model.number="form.interval" type="number" min="500" step="100" />
      </label>

      <!-- 传感器字段对齐 -->
      <div class="cn-map">
        <div class="cn-map-head">
          <span class="cn-map-title">传感器字段对齐</span>
          <button class="cn-map-auto" @click="autoMatch" title="依据最近收到的遥测字段自动匹配内部传感器">
            <Icon name="bolt" :size="12" /> 自动匹配
          </button>
        </div>
        <p class="cn-map-tip">
          将数据源遥测中的<b>外部字段名</b>映射为<b>场景内传感器/设备 id</b>，
          使外部实时数值与场景传感器读数对齐。未映射的字段沿用其自身 id。
        </p>
        <div v-if="lastFields.length" class="cn-map-detect">
          已收到字段：<code v-for="f in lastFields" :key="f">{{ f }}</code>
        </div>
        <div v-else-if="form.type !== 'sim'" class="cn-map-detect idle">
          暂无遥测字段：连接成功后这里会显示外部字段，便于手动/自动对齐。
        </div>
        <div v-if="!form.rows.length" class="cn-map-empty">尚未配置映射</div>
        <div v-for="(r, i) in form.rows" :key="i" class="cn-map-row">
          <input v-model="r.ext" type="text" class="cn-map-ext" placeholder="外部字段名，如 temp_1" />
          <span class="cn-map-arrow">→</span>
          <select v-model="r.int" class="cn-map-int">
            <option value="">（不映射 / 忽略）</option>
            <option v-for="d in deviceOptions" :key="d.id" :value="d.id">{{ d.label }}</option>
          </select>
          <button class="cn-map-del" title="删除该映射" @click="form.rows.splice(i, 1)">✕</button>
        </div>
        <button class="cn-map-add" @click="form.rows.push({ ext: '', int: '' })">+ 添加映射</button>
      </div>

      <div class="cn-form-actions">
        <button class="cn-save" @click="save">保存</button>
        <button class="cn-cancel" @click="formOpen = false">取消</button>
      </div>
    </div>

    <!-- 数据源列表 -->
    <div class="cn-list" @scroll="onScroll" :class="{ scrolling }">
      <div v-if="!store.dataSources.length" class="empty-hint">暂无数据源，点击上方「新建数据源」接入实时数据。</div>
      <div v-for="src in store.dataSources" :key="src.id" class="cn-card"
           :class="{ disabled: src.enabled === false }">
        <div class="cn-card-top">
          <span class="cn-dot" :style="{ background: statusColor(src.id) }" :title="statusLabel(src.id)"></span>
          <span class="cn-card-name">{{ src.name || src.id }}</span>
          <span class="cn-type" :class="src.type">{{ TYPE_META[src.type] ? TYPE_META[src.type].label : src.type }}</span>
          <span v-if="src.id === store.activeDataSourceId" class="cn-active">活动</span>
        </div>
        <div v-if="src.type !== 'sim' && src.url" class="cn-card-url">{{ src.url }}</div>
        <div class="cn-card-sub">
          <span>{{ statusLabel(src.id) }}</span>
          <template v-if="src.enabled !== false && store.lastFields[src.id]">
            <span class="cn-sep">·</span>
            <span>遥测字段 {{ store.lastFields[src.id].length }} 个</span>
          </template>
          <template v-if="src.mapping && Object.keys(src.mapping).length">
            <span class="cn-sep">·</span>
            <span>已对齐 {{ Object.keys(src.mapping).length }} 项</span>
          </template>
        </div>
        <div class="cn-card-ops">
          <label class="cn-switch" :title="(src.enabled === false ? '启用' : '停用') + '该数据源'">
            <input type="checkbox" :checked="src.enabled !== false" @change="store.toggleDataSource(src.id)" />
            <span class="cn-switch-track"></span>
          </label>
          <button v-if="src.id !== store.activeDataSourceId" class="cn-op" @click="store.setActiveDataSource(src.id)">设为活动</button>
          <button class="cn-op" @click="openEdit(src)">编辑</button>
          <button v-if="src.id !== 'sim'" class="cn-op danger" @click="remove(src)">删除</button>
        </div>
      </div>

      <div class="cn-tip">
        说明：多个数据源可同时启用并接入实时数据；「活动」数据源用于状态栏与指令区展示。
        每个数据源可配置「字段对齐」，把外部遥测字段名映射为场景内传感器/设备 id，实现数值对齐。
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'

const store = useSimStore()

const TYPE_META = {
  sim: { label: 'Mqtt 实时' },
  ws: { label: 'WebSocket' },
  http: { label: 'HTTP 轮询' },
}
// MQTT 实时数据源状态（store.mqttSource 由 /api/realtime/source 轮询得到）
const mqttConnected = computed(() => !!(store.mqttSource && store.mqttSource.connected))
const mqttStatusText = computed(() => {
  const s = store.mqttSource
  if (!s) return '获取中…'
  if (s.connected) return '已连接'
  return s.last_error ? '异常' : '未连接'
})
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
  init: { label: '连接中', color: '#c9a24b' },
  open: { label: '已连接', color: '#3a9d5d' },
  closed: { label: '已断开', color: '#b3b3b3' },
  error: { label: '错误', color: '#d9534f' },
}
function statusLabel(id) {
  const st = store.sourceStatus[id]
  return st ? (STATUS_META[st] ? STATUS_META[st].label : st) : '未连接'
}
function statusColor(id) {
  const st = store.sourceStatus[id]
  return st ? (STATUS_META[st] ? STATUS_META[st].color : '#b3b3b3') : '#b3b3b3'
}

// ---- 新建/编辑表单 ----
const formOpen = ref(false)
const editingId = ref(null)
const form = reactive({ name: '', type: 'ws', url: '', interval: 1000, enabled: true, rows: [] })

function openNew() {
  editingId.value = null
  Object.assign(form, { name: '', type: 'ws', url: '', interval: 1000, enabled: true })
  form.rows = []
  formOpen.value = true
}
function openEdit(src) {
  editingId.value = src.id
  Object.assign(form, {
    name: src.name || '',
    type: src.type || 'ws',
    url: src.url || '',
    interval: src.interval || 1000,
    enabled: src.enabled !== false,
  })
  form.rows = Object.entries(src.mapping || {}).map(([ext, int]) => ({ ext, int }))
  formOpen.value = true
}
// 保存：把 rows 组装为 mapping（外部字段 -> 内部设备 id），并交给 store 新建/更新（更新即重连）
function save() {
  const mapping = {}
  for (const r of form.rows) {
    const ext = (r.ext || '').trim()
    if (!ext) continue
    mapping[ext] = r.int
  }
  const payload = { name: form.name, type: form.type, url: form.url, interval: form.interval, enabled: form.enabled, mapping }
  if (editingId.value) {
    if (!payload.name) payload.name = store.dataSources.find((s) => s.id === editingId.value)?.name || '数据源'
    store.updateDataSource(editingId.value, payload)
    store.toast = `已更新数据源「${payload.name}」并重新连接`
  } else {
    const id = store.addDataSource(payload)
    store.toast = `已新建数据源「${payload.name || '数据源'}」并开始连接`
    editingId.value = id
  }
  formOpen.value = false
}
function remove(src) {
  if (!window.confirm(`确认删除数据源「${src.name || src.id}」？`)) return
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
// 自动匹配：把最近收到的外部字段与内部传感器按 id/名称 精确或包含匹配
function autoMatch() {
  const fields = lastFields.value
  if (!fields.length) {
    store.toast = '尚未收到该数据源的遥测字段，请先确保连接成功'
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
    form.rows.push({ ext: f, int: hit ? hit.id : '' })
    if (hit) matched++
  }
  store.toast = `已按外部字段自动匹配：成功 ${matched} 项，其余可手动指定`
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
.cn-head { flex: 0 0 auto; padding: 8px 10px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; }
.cn-head-row { display: flex; align-items: center; gap: 6px; }
.cn-head-ic { color: var(--accent2); opacity: .85; }
.cn-title { font-size: 12px; font-weight: 600; color: var(--text); }
.cn-badge { font-size: 10px; color: var(--accent); background: var(--accent-l); border-radius: 8px; padding: 1px 7px; }
.cn-new {
  margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #fff; background: var(--accent); border: none;
  border-radius: 5px; padding: 4px 9px; cursor: pointer; transition: opacity .15s;
}
.cn-new:hover { opacity: .88; }

/* ---- MQTT 实时数据源状态 ---- */
.cn-mqtt {
  flex: 0 0 auto; margin: 8px 10px 0; padding: 8px 10px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--panel-2); display: flex; flex-direction: column; gap: 5px;
}
.cn-mqtt.on { border-color: rgba(58,157,93,.5); background: rgba(58,157,93,.06); }
.cn-mqtt-head { display: flex; align-items: center; gap: 8px; }
.cn-mqtt-title { font-size: 11.5px; font-weight: 600; color: var(--text); }
.cn-mqtt-status {
  margin-left: auto; font-size: 10px; padding: 1px 8px; border-radius: 8px;
  color: var(--muted); background: var(--panel); border: 1px solid var(--border);
}
.cn-mqtt-status.on { color: #2e8b57; background: rgba(58,157,93,.12); border-color: rgba(58,157,93,.35); }
.cn-mqtt-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--muted); flex-wrap: wrap; }
.cn-mqtt-row code {
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 6px; font-size: 10px; color: var(--accent2);
}
.cn-mqtt-msg { display: flex; align-items: flex-start; gap: 6px; font-size: 10px; color: var(--muted); flex-direction: column; }
.cn-mqtt-msg .cn-mqtt-topic { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; color: var(--accent2); }
.cn-mqtt-payload {
  width: 100%; max-height: 56px; overflow: hidden; font-size: 10px; line-height: 1.5;
  color: var(--faint); background: var(--panel); border-radius: 4px; padding: 4px 6px;
  word-break: break-all; font-family: var(--mono, ui-monospace, monospace);
}
.cn-mqtt-note { font-size: 10px; color: var(--faint); line-height: 1.5; }

/* ---- 表单 ---- */
.cn-form { flex: 0 0 auto; padding: 10px; border-bottom: 1px solid var(--border); background: var(--panel-2); max-height: 55%; overflow-y: auto; }
.cn-form-title { font-size: 11.5px; font-weight: 600; margin-bottom: 8px; color: var(--text); }
.cn-fld { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
.cn-fld > span { font-size: 10.5px; color: var(--muted); }
.cn-fld input, .cn-fld select {
  border: 1px solid var(--border); border-radius: 5px; background: var(--panel);
  color: var(--text); font-size: 11.5px; padding: 4px 7px; outline: none; min-width: 0;
}
.cn-fld input:focus, .cn-fld select:focus { border-color: var(--accent); }

/* ---- 字段对齐 ---- */
.cn-map { margin-top: 2px; border: 1px dashed var(--border); border-radius: 6px; padding: 8px; }
.cn-map-head { display: flex; align-items: center; gap: 6px; }
.cn-map-title { font-size: 11px; font-weight: 600; color: var(--text); }
.cn-map-auto {
  margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
  font-size: 10.5px; color: var(--accent); background: var(--accent-l); border: 1px solid var(--accent-l);
  border-radius: 4px; padding: 2px 7px; cursor: pointer;
}
.cn-map-auto:hover { border-color: var(--accent); }
.cn-map-tip { margin: 5px 0 6px; font-size: 10px; color: var(--muted); line-height: 1.6; }
.cn-map-tip b { color: var(--text); }
.cn-map-detect { margin-bottom: 6px; font-size: 10px; color: var(--accent2); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.cn-map-detect code { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; font-size: 10px; }
.cn-map-detect.idle { color: var(--faint); }
.cn-map-empty { font-size: 10.5px; color: var(--faint); padding: 4px 0; }
.cn-map-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.cn-map-ext { flex: 0 0 42%; min-width: 0; border: 1px solid var(--border); border-radius: 5px; background: var(--panel); color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; }
.cn-map-ext:focus { border-color: var(--accent); }
.cn-map-arrow { flex: 0 0 auto; color: var(--faint); font-size: 11px; }
.cn-map-int { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 5px; background: var(--panel); color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; }
.cn-map-int:focus { border-color: var(--accent); }
.cn-map-del { flex: 0 0 auto; width: 17px; height: 17px; display: grid; place-items: center; border: none; border-radius: 50%; background: transparent; color: var(--faint); font-size: 9px; cursor: pointer; padding: 0; }
.cn-map-del:hover { color: #d9534f; background: rgba(217,83,79,.12); }
.cn-map-add {
  font-size: 10.5px; color: var(--muted); background: transparent; border: 1px dashed var(--border);
  border-radius: 5px; padding: 3px 8px; cursor: pointer; margin-top: 2px;
}
.cn-map-add:hover { color: var(--accent); border-color: var(--accent); }

.cn-form-actions { display: flex; gap: 8px; margin-top: 10px; justify-content: flex-end; }
.cn-save { font-size: 11px; color: #fff; background: var(--accent); border: none; border-radius: 5px; padding: 4px 14px; cursor: pointer; }
.cn-save:hover { opacity: .88; }
.cn-cancel { font-size: 11px; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: 5px; padding: 4px 12px; cursor: pointer; }
.cn-cancel:hover { color: var(--text); }

/* ---- 列表 ---- */
.cn-list { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 8px 14px; }
.cn-list.scrolling { scrollbar-width: thin; }
.cn-card { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; background: var(--panel); }
.cn-card.disabled { opacity: .55; }
.cn-card-top { display: flex; align-items: center; gap: 6px; }
.cn-dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.cn-card-name { font-size: 12px; font-weight: 600; color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cn-type { flex: 0 0 auto; font-size: 9.5px; padding: 1px 6px; border-radius: 8px; background: var(--panel-2); color: var(--muted); border: 1px solid var(--border); }
.cn-type.ws { color: #2d7dd2; background: rgba(45,125,210,.1); border-color: rgba(45,125,210,.25); }
.cn-type.http { color: #9a6b08; background: rgba(255,180,0,.1); border-color: rgba(255,180,0,.25); }
.cn-active { flex: 0 0 auto; font-size: 9.5px; color: #fff; background: var(--accent); border-radius: 8px; padding: 1px 7px; }
.cn-card-url { margin-top: 5px; font-size: 10.5px; color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }
.cn-card-sub { margin-top: 4px; display: flex; gap: 6px; align-items: center; font-size: 10.5px; color: var(--muted); flex-wrap: wrap; }
.cn-sep { color: var(--border); }
.cn-card-ops { margin-top: 8px; display: flex; align-items: center; gap: 6px; }
.cn-switch { position: relative; display: inline-flex; cursor: pointer; }
.cn-switch input { display: none; }
.cn-switch-track { width: 28px; height: 15px; border-radius: 8px; background: var(--border); transition: background .15s; position: relative; }
.cn-switch-track::after {
  content: ''; position: absolute; left: 2px; top: 2px; width: 11px; height: 11px;
  border-radius: 50%; background: #fff; transition: left .15s; box-shadow: 0 1px 2px rgba(0,0,0,.25);
}
.cn-switch input:checked + .cn-switch-track { background: var(--accent); }
.cn-switch input:checked + .cn-switch-track::after { left: 15px; }
.cn-op {
  font-size: 10.5px; color: var(--muted); background: transparent; border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 8px; cursor: pointer; transition: all .15s;
}
.cn-op:hover { color: var(--accent); border-color: var(--accent); }
.cn-op.danger:hover { color: #d9534f; border-color: #d9534f; }
.cn-tip { font-size: 10.5px; color: var(--faint); line-height: 1.7; padding: 6px 4px; }
.empty-hint { padding: 14px 10px; color: var(--faint); font-size: 11.5px; line-height: 1.7; }
</style>
