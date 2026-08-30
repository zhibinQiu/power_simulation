<template>
  <div class="sm-mask" @click.self="$emit('close')">
    <div class="sm-modal" role="dialog" aria-modal="true" :aria-label="t('技能管理')">
      <div class="sm-head">
        <span class="sm-title">⚙️ {{ t('技能管理') }}</span>
        <span class="sm-sub">{{ t('Skills 是智能体的工具集（内置 + MCP 接入），可启停控制可用范围') }}</span>
        <button class="x-btn lg" @click="$emit('close')" :aria-label="t('关闭')">×</button>
      </div>

      <div class="sm-body">
        <div class="sm-toolbar">
          <span class="sm-count">{{ t('共') }} {{ skills.length }} {{ t('个技能') }}</span>
          <span class="sm-flex"></span>
          <button class="sm-btn" @click="reload">🔄 {{ t('刷新') }}</button>
        </div>
        <div class="sm-list">
          <div v-for="s in skills" :key="s.name" class="sm-item" :class="{ off: !s.enabled }">
            <span class="sm-icon">{{ iconOf(s) }}</span>
            <div class="sm-meta">
              <div class="sm-name">
                {{ skillLabel(s.name) }}
                <em class="sm-src" :class="s.source">{{ srcLabel(s.source) }}</em>
                <em v-if="s.timeout" class="sm-timeout">{{ t('超时') }} {{ s.timeout }}s</em>
              </div>
              <div class="sm-desc">{{ s.description }}</div>
            </div>
            <button class="sm-switch" :class="{ on: s.enabled }" :aria-pressed="s.enabled"
                    @click="toggle(s)">{{ s.enabled ? t('启用') : t('停用') }}</button>
          </div>
          <div v-if="!skills.length" class="sm-empty">{{ t('暂无技能') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { t } from '../i18n'
import { api } from '../api/client'
const skills = ref([])

async function load() {
  const r = await api.get('/skills?all=1')
  skills.value = r.skills || []
}
async function toggle(s) {
  const r = await api.post(`/skills/${encodeURIComponent(s.name)}/toggle`, { enabled: !s.enabled })
  if (r && r.ok) { s.enabled = !s.enabled }
}
function reload() { load() }
function skillLabel(name) { return name.includes('__') ? name.split('__').pop() : name }
function srcLabel(src) { return src === 'mcp' ? 'MCP' : (src === 'builtin' ? t('内置') : src) }
function iconOf(s) { return s.source === 'mcp' ? '🔌' : (s.name.startsWith('query') ? '📡' : s.name.startsWith('run') ? '🧪' : '🛠️') }
onMounted(load)
</script>

<style scoped>
.sm-mask { position: fixed; inset: 0; background: rgba(16,24,34,.5); z-index: 300; display: flex; align-items: center; justify-content: center; }
.sm-modal { width: 720px; max-width: 94vw; height: 72vh; background: var(--panel); color: var(--text); border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; box-shadow: 0 18px 50px rgba(0,0,0,.35); overflow: hidden; }
.sm-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, var(--panel)), var(--panel)); }
.sm-title { font-weight: 700; font-size: 15px; letter-spacing: 1px; }
.sm-sub { flex: 1; color: var(--faint); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sm-body { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.sm-toolbar { display: flex; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--border); }
.sm-count { font-size: 12.5px; color: var(--faint); }
.sm-flex { flex: 1; }
.sm-btn { padding: 5px 12px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); color: var(--text); cursor: pointer; font-size: 12.5px; transition: all .15s; }
.sm-btn:hover { border-color: var(--accent); color: var(--accent); }
.sm-list { flex: 1; overflow: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.sm-item { display: flex; align-items: center; gap: 12px; padding: 11px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); }
.sm-item:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--border)); }
.sm-item.off { opacity: .55; }
.sm-icon { font-size: 20px; }
.sm-meta { flex: 1; min-width: 0; }
.sm-name { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13.5px; color: var(--text); }
.sm-src { font-style: normal; font-size: 10.5px; border-radius: 4px; padding: 1px 6px; }
.sm-src.builtin { color: var(--accent); border: 1px solid var(--accent); }
.sm-src.mcp { color: #7c5cff; border: 1px solid #7c5cff; }
.sm-timeout { font-style: normal; font-size: 10.5px; color: var(--faint); }
.sm-desc { font-size: 12px; color: var(--faint); margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sm-switch { padding: 4px 12px; border-radius: 4px; border: 1px solid var(--border); background: var(--panel-2); color: var(--faint); cursor: pointer; font-size: 12px; transition: all .15s; }
.sm-switch:hover { border-color: var(--accent-d); color: var(--accent-d); }
.sm-switch.on { background: color-mix(in srgb, var(--accent) 18%, transparent); border-color: var(--accent); color: var(--accent-d); font-weight: 600; }
.sm-empty { color: var(--faint); text-align: center; padding: 40px; font-size: 13px; }
</style>
