<template>
  <div class="pc-mask" @click.self="$emit('close')">
    <div class="pc-modal" role="dialog" aria-modal="true" aria-label="平台配置">
      <div class="pc-head">
        <span class="pc-title">平台配置</span>
        <button class="pc-x" @click="$emit('close')" aria-label="关闭">×</button>
      </div>

      <div class="pc-tabs">
        <button v-for="t in tabs" :key="t.id" class="pc-tab" :class="{ on: tab === t.id }" @click="tab = t.id">
          {{ t.label }}
        </button>
      </div>

      <div class="pc-body">
        <p class="pc-tip">
          为不同钢厂/产线调整通用性配置：设备量程、参数运行空间。
          保存后参数编辑器、设备面板与 3D 标注自动使用新范围。
          「设备规格」为内置档位，在流程编排的工序节点上选择后，该节点按规格的默认参数与范围参与仿真。
        </p>

        <!-- 设备量程 -->
        <div v-if="tab === 'device'" class="pc-list">
          <div v-for="(d, dev) in form.device_ranges" :key="dev" class="pc-row">
            <div class="pc-row-head">
              <span class="pc-ut">{{ d.label || dev }}</span>
              <span class="sp"></span>
            </div>
            <div class="pc-row-fields">
              <label>量程下限 <input type="number" v-model.number="d.min" /></label>
              <label>量程上限 <input type="number" v-model.number="d.max" /></label>
              <label>单位 <input v-model.trim="d.unit" style="width: 90px" /></label>
            </div>
          </div>
          <div v-if="!Object.keys(form.device_ranges || {}).length" class="pc-empty">暂无设备量程配置</div>
        </div>

        <!-- 参数运行空间 -->
        <div v-if="tab === 'param'" class="pc-list">
          <details v-for="(params, ut) in form.param_ranges" :key="ut" class="pc-detail" open>
            <summary>{{ unitLabel(ut) }} <em>{{ Object.keys(params || {}).length }} 项</em></summary>
            <div v-for="(p, key) in params" :key="key" class="pc-row thin">
              <span class="pc-param">{{ p.label || key }}</span>
              <span class="sp"></span>
              <div class="pc-row-fields inline">
                <label>min <input type="number" v-model.number="p.min" /></label>
                <label>max <input type="number" v-model.number="p.max" /></label>
                <label>step <input type="number" v-model.number="p.step" /></label>
              </div>
            </div>
          </details>
          <div v-if="!Object.keys(form.param_ranges || {}).length" class="pc-empty">暂无参数运行空间配置</div>
        </div>

        <!-- 设备规格（内置档位，只读） -->
        <div v-if="tab === 'spec'" class="pc-list">
          <div v-if="!Object.keys(form.process_specs || {}).length" class="pc-empty">暂无设备规格档位</div>
          <details v-for="(specs, ut) in form.process_specs" :key="ut" class="pc-detail" open>
            <summary>{{ unitLabel(ut) }} <em>{{ specs.length }} 档</em></summary>
            <div v-for="s in specs" :key="s.key" class="pc-row thin">
              <span class="pc-ut" style="min-width: 168px">{{ s.label }}</span>
              <span class="pc-param">{{ s.key }}</span>
              <span class="sp"></span>
              <span class="pc-param" v-if="s.desc" style="max-width: 200px">{{ s.desc }}</span>
            </div>
          </details>
        </div>
      </div>

      <div class="pc-actions">
        <button class="pc-btn ghost" :disabled="saving" @click="resetAll">恢复出厂默认</button>
        <span class="sp"></span>
        <button class="pc-btn ghost" :disabled="saving" @click="$emit('close')">取消</button>
        <button class="pc-btn primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存配置' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const emit = defineEmits(['close'])

const tabs = [
  { id: 'device', label: '设备量程' },
  { id: 'param', label: '参数运行空间' },
  { id: 'spec', label: '设备规格' },
]
const tab = ref('device')
const saving = ref(false)
const form = reactive({ device_ranges: {}, param_ranges: {}, process_specs: {} })

function unitLabel(ut) {
  const info = (store.paramSchema?.unit_types || []).find((u) => u.type === ut)
  return info?.label || ut
}

function syncForm() {
  const cfg = store.platformConfig || {}
  Object.assign(form.device_ranges, JSON.parse(JSON.stringify(cfg.device_ranges || {})))
  Object.assign(form.param_ranges, JSON.parse(JSON.stringify(cfg.param_ranges || {})))
  Object.assign(form.process_specs, JSON.parse(JSON.stringify(cfg.process_specs || {})))
}

async function save() {
  saving.value = true
  try {
    await store.savePlatformConfig({
      device_ranges: form.device_ranges,
      param_ranges: form.param_ranges,
    })
    emit('close')
  } catch (e) {
    store.toast = '保存平台配置失败：' + (e.message || e)
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  saving.value = true
  try {
    await store.resetPlatformConfig()
    syncForm()
  } catch (e) {
    store.toast = '重置平台配置失败：' + (e.message || e)
  } finally {
    saving.value = false
  }
}

onMounted(syncForm)
</script>

<style scoped>
.pc-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.pc-modal { width: 680px; max-width: 94vw; max-height: 86vh; display: flex; flex-direction: column; background: var(--panel);
  border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 18px 50px rgba(0,0,0,.28); font-family: var(--ui); color: var(--text); }
.pc-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.pc-title { font-size: 14px; font-weight: 700; }
.pc-x { border: none; background: transparent; font-size: 14px; line-height: 1; color: var(--muted); cursor: pointer; padding: 0 4px; }
.pc-x:hover { color: var(--text); }
.pc-tabs { display: flex; gap: 4px; padding: 10px 14px 0; }
.pc-tab { padding: 7px 12px; border: 1px solid transparent; border-radius: 6px 6px 0 0; background: transparent;
  cursor: pointer; font-size: 12px; color: var(--muted); }
.pc-tab:hover { color: var(--text); }
.pc-tab.on { border-color: var(--border); border-bottom-color: var(--panel); background: var(--panel); color: var(--accent-d); font-weight: 600; }
.pc-body { padding: 12px 14px 14px; overflow: auto; }
.pc-tip { font-size: 10px; color: var(--muted); line-height: 1.6; margin: 0 0 12px; }
.pc-list { display: flex; flex-direction: column; gap: 10px; }
.pc-row { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; background: var(--bar); display: flex; flex-direction: column; gap: 6px; }
.pc-row.thin { flex-direction: row; align-items: center; padding: 6px 10px; }
.pc-row-head { display: flex; align-items: center; gap: 8px; }
.pc-ut { font-size: 12px; font-weight: 700; }
.pc-param { font-size: 11px; color: var(--muted); }
.pc-param em { font-style: normal; color: var(--faint); margin-left: 4px; }
.pc-row-fields { display: flex; gap: 10px; }
.pc-row-fields.inline { gap: 8px; }
.pc-row-fields label { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); }
.pc-row-fields input { width: 82px; padding: 5px 7px; border: 1px solid var(--border); border-radius: 5px; background: var(--panel); color: var(--text); font-size: 11px; font-family: var(--ui); }
.pc-row-fields input:focus { outline: none; border-color: var(--accent); }
.pc-detail { border: 1px solid var(--border); border-radius: 6px; background: var(--bar); }
.pc-detail summary { cursor: pointer; padding: 8px 10px; font-size: 12px; font-weight: 700; }
.pc-detail summary em { font-style: normal; font-weight: 400; color: var(--muted); font-size: 10px; margin-left: 6px; }
.pc-detail .pc-row { border: none; border-top: 1px solid var(--border); border-radius: 0; background: transparent; }
.pc-empty { font-size: 11px; color: var(--faint); text-align: center; padding: 16px 0; }
.pc-actions { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-top: 1px solid var(--border); }
.pc-actions .sp { flex: 1; }
.pc-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); cursor: pointer; font-size: 12px; color: var(--text); }
.pc-btn:hover { border-color: var(--accent); }
.pc-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.pc-btn.primary:hover { background: var(--accent-d); }
.pc-btn.ghost { background: transparent; }
.pc-btn:disabled { color: var(--faint); cursor: default; border-color: var(--border); }
.sp { flex: 1; }
</style>
