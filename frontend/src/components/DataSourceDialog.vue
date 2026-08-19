<template>
  <div class="ds-mask" @click.self="$emit('close')">
    <div class="ds-modal" role="dialog" aria-modal="true" aria-label="连接数据源">
      <div class="ds-head">
        <span class="ds-title">连接数据源</span>
        <button class="ds-x" @click="$emit('close')" aria-label="关闭">×</button>
      </div>

      <div class="ds-body">
        <p class="ds-tip">
          平台支持多个实时数据源并存（可分别启用/停用）。遥测数据形如
          <code>{ devices: [{ id, reading }], units?: [...] }</code>；
          通过「字段对齐」可把外部遥测字段名映射为场景内传感器/设备 id，实现数值对齐。
        </p>

        <!-- 数据源选择：新建或编辑已有 -->
        <div class="ds-field">
          <label>数据源</label>
          <select class="ds-input" v-model="editingId" @change="loadFromSource">
            <option value="">＋ 新建数据源</option>
            <option v-for="s in store.dataSources" :key="s.id" :value="s.id">
              {{ s.name || s.id }}{{ s.type === 'sim' ? '（内置模拟）' : '' }}{{ s.enabled === false ? '（已停用）' : '' }}
            </option>
          </select>
        </div>

        <div class="ds-field">
          <label>数据源类型</label>
          <div class="ds-types">
            <button v-for="t in types" :key="t.id" class="ds-type" :class="{ on: form.type === t.id }"
                    @click="form.type = t.id">{{ t.label }}</button>
          </div>
        </div>

        <div class="ds-field" v-if="form.type !== 'sim'">
          <label>连接地址 (URL)</label>
          <input class="ds-input" v-model.trim="form.url" :placeholder="form.type === 'ws' ? 'ws://主机:端口/路径' : 'https://主机:端口/数据接口'" />
        </div>

        <div class="ds-field" v-if="form.type === 'http'">
          <label>轮询间隔 (毫秒)</label>
          <input class="ds-input" type="number" min="500" step="500" v-model.number="form.interval" />
        </div>

        <div class="ds-field">
          <label>显示名称（可选）</label>
          <input class="ds-input" v-model.trim="form.name" placeholder="例如：1# 高炉实时测点" />
        </div>

        <!-- 传感器字段对齐 -->
        <div class="ds-field">
          <label>传感器字段对齐
            <button class="ds-map-auto" type="button" @click="autoMatch">自动匹配</button>
          </label>
          <div v-if="form.type !== 'sim'" class="ds-map-detect">
            <template v-if="lastFields.length">
              该源已收到字段：<code v-for="f in lastFields" :key="f">{{ f }}</code>
            </template>
            <template v-else>连接成功后此处会显示收到的外部字段，便于对齐</template>
          </div>
          <div v-if="!form.rows.length" class="ds-map-empty">尚未配置映射</div>
          <div v-for="(r, i) in form.rows" :key="i" class="ds-map-row">
            <input v-model="r.ext" type="text" class="ds-input ds-map-ext" placeholder="外部字段名，如 temp_1" />
            <span class="ds-map-arrow">→</span>
            <select v-model="r.int" class="ds-input ds-map-int">
              <option value="">（不映射 / 忽略）</option>
              <option v-for="d in deviceOptions" :key="d.id" :value="d.id">{{ d.label }}</option>
            </select>
            <button class="ds-map-del" type="button" title="删除该映射" @click="form.rows.splice(i, 1)">✕</button>
          </div>
          <button class="ds-map-add" type="button" @click="form.rows.push({ ext: '', int: '' })">+ 添加映射</button>
        </div>

        <div class="ds-actions">
          <button class="ds-btn" :disabled="!canTest" @click="testConn">测试连接</button>
          <span class="ds-test" :class="testClass">{{ testText }}</span>
          <span class="sp"></span>
          <button class="ds-btn ghost" @click="$emit('close')">取消</button>
          <button class="ds-btn primary" :disabled="!canApply" @click="apply">保存并连接</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const emit = defineEmits(['close'])

const types = [
  { id: 'sim', label: '内置模拟' },
  { id: 'ws', label: '自定义 WebSocket' },
  { id: 'http', label: '自定义 HTTP 轮询' },
]

// editingId = '' 表示新建；否则为已存在数据源 id
const editingId = ref('')
const form = reactive({ type: 'sim', url: '', interval: 1000, name: '', rows: [] })

const testText = ref('')
const testState = ref('') // '' | 'ok' | 'err' | 'wait'

const canTest = computed(() => form.type === 'sim' || !!form.url)
const canApply = computed(() => form.type === 'sim' || !!form.url)
const testClass = computed(() => 'ds-test' + (testState.value ? ' ' + testState.value : ''))

// 内部传感器选项（场景内真实设备）
const deviceOptions = computed(() =>
  store.allDevices.map((d) => ({
    id: d.id,
    label: `${d.label} · ${d.unitName || d.unitType || ''}${d.unit ? ' (' + d.unit + ')' : ''}`,
  }))
)
const lastFields = computed(() => (editingId.value ? store.lastFields[editingId.value] || [] : []))

// 切换编辑对象时载入其配置与已有映射
function loadFromSource() {
  form.rows = []
  const src = store.dataSources.find((s) => s.id === editingId.value)
  if (!src) { Object.assign(form, { type: 'sim', url: '', interval: 1000, name: '' }); return }
  Object.assign(form, {
    type: src.type || 'sim',
    url: src.url || '',
    interval: src.interval || 1000,
    name: src.name || '',
  })
  form.rows = Object.entries(src.mapping || {}).map(([ext, int]) => ({ ext, int }))
}

function testConn() {
  testState.value = 'wait'
  testText.value = '连接中…'
  if (form.type === 'sim') {
    fetch('/api/health').then((r) => {
      if (r.ok) { testState.value = 'ok'; testText.value = '内置模拟数据可用' }
      else { testState.value = 'err'; testText.value = '后端不可用 (' + r.status + ')' }
    }).catch(() => { testState.value = 'err'; testText.value = '无法连接后端' })
    return
  }
  if (form.type === 'ws') {
    try {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const url = form.url.startsWith('ws') ? form.url : `${proto}://${form.url}`
      const ws = new WebSocket(url)
      const to = setTimeout(() => { try { ws.close() } catch (e) {} testState.value = 'err'; testText.value = '连接超时' }, 5000)
      ws.onopen = () => { clearTimeout(to); testState.value = 'ok'; testText.value = 'WebSocket 连接成功'; ws.close() }
      ws.onerror = () => { clearTimeout(to); testState.value = 'err'; testText.value = '连接失败' }
    } catch (e) { testState.value = 'err'; testText.value = '地址无效' }
    return
  }
  fetch(form.url, { headers: { Accept: 'application/json' } })
    .then((r) => { if (r.ok) { testState.value = 'ok'; testText.value = 'HTTP ' + r.status + ' 正常' } else { testState.value = 'err'; testText.value = 'HTTP ' + r.status } })
    .catch(() => { testState.value = 'err'; testText.value = '请求失败' })
}

// 自动匹配：把最近收到的外部字段与内部传感器按 id/名称 精确或包含匹配
function autoMatch() {
  const fields = lastFields.value
  if (!fields.length) { store.toast = '尚未收到该数据源的遥测字段，请先测试连接'; return }
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
  store.toast = `自动匹配成功 ${matched} 项，其余可手动指定`
}

function apply() {
  const mapping = {}
  for (const r of form.rows) {
    const ext = (r.ext || '').trim()
    if (ext) mapping[ext] = r.int
  }
  const payload = {
    type: form.type,
    url: form.url,
    interval: Number(form.interval) || 1000,
    name: form.name || (form.type === 'sim' ? '内置模拟数据' : form.url),
    mapping,
  }
  if (editingId.value) {
    store.updateDataSource(editingId.value, payload)
    store.toast = `数据源「${payload.name}」已更新并重新连接`
  } else {
    store.addDataSource(payload)
    store.toast = `数据源「${payload.name}」已创建并开始连接`
  }
  emit('close')
}

// 默认编辑当前活动数据源
watch(editingId, () => { testState.value = ''; testText.value = '' }, { immediate: false })
if (store.dataSource && store.dataSource.id && store.dataSource.id !== 'sim') {
  editingId.value = store.dataSource.id
  loadFromSource()
}
</script>

<style scoped>
.ds-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ds-modal { width: 520px; max-width: 94vw; max-height: 88vh; display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 18px 50px rgba(0,0,0,.28); font-family: var(--ui); color: var(--text); }
.ds-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.ds-title { font-size: 14px; font-weight: 700; }
.ds-x { border: none; background: transparent; font-size: 14px; line-height: 1; color: var(--muted); cursor: pointer; padding: 0 4px; }
.ds-x:hover { color: var(--text); }
.ds-body { padding: 14px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.ds-tip { font-size: 10px; color: var(--muted); line-height: 1.6; margin: 0; }
.ds-tip code { background: var(--bar); padding: 1px 5px; border-radius: 4px; font-size: 10px; }
.ds-field { display: flex; flex-direction: column; gap: 6px; }
.ds-field label { font-size: 10px; font-weight: 600; color: var(--muted); display: flex; align-items: center; gap: 8px; }
.ds-types { display: flex; gap: 8px; }
.ds-type { flex: 1; padding: 8px 6px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); cursor: pointer;
  font-size: 12px; color: var(--text); }
.ds-type.on { border-color: var(--accent); background: var(--accent-l); color: var(--accent-d); font-weight: 600; }
.ds-input { padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); color: var(--text); font-size: 12px; font-family: var(--ui); }
.ds-input:focus { outline: none; border-color: var(--accent); }
.ds-map-auto { margin-left: auto; font-size: 10px; color: var(--accent); background: var(--accent-l); border: 1px solid var(--accent-l);
  border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.ds-map-auto:hover { border-color: var(--accent); }
.ds-map-detect { font-size: 10px; color: var(--accent2); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.ds-map-detect code { background: var(--bar); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; font-size: 10px; }
.ds-map-empty { font-size: 10.5px; color: var(--faint); padding: 2px 0; }
.ds-map-row { display: flex; align-items: center; gap: 6px; }
.ds-map-ext { flex: 0 0 38%; min-width: 0; }
.ds-map-arrow { color: var(--faint); font-size: 11px; flex: 0 0 auto; }
.ds-map-int { flex: 1; min-width: 0; }
.ds-map-del { flex: 0 0 auto; width: 18px; height: 18px; display: grid; place-items: center; border: none; border-radius: 50%;
  background: transparent; color: var(--faint); font-size: 9px; cursor: pointer; padding: 0; }
.ds-map-del:hover { color: #c0392b; background: rgba(192,57,43,.1); }
.ds-map-add { align-self: flex-start; font-size: 10.5px; color: var(--muted); background: transparent; border: 1px dashed var(--border);
  border-radius: 5px; padding: 3px 9px; cursor: pointer; }
.ds-map-add:hover { color: var(--accent); border-color: var(--accent); }
.ds-actions { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
.ds-actions .sp { flex: 1; }
.ds-test { font-size: 10px; color: var(--muted); }
.ds-test.ok { color: #2e8b57; }
.ds-test.err { color: #c0392b; }
.ds-test.wait { color: var(--accent); }
.ds-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); cursor: pointer; font-size: 12px; color: var(--text); }
.ds-btn:hover { border-color: var(--accent); }
.ds-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.ds-btn.primary:hover { background: var(--accent-d); }
.ds-btn.ghost { background: transparent; }
.ds-btn:disabled { color: var(--faint); cursor: default; border-color: var(--border); }
</style>
