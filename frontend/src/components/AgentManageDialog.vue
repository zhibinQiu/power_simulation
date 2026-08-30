<template>
  <div class="am-mask" @click.self="$emit('close')">
    <div class="am-modal" role="dialog" aria-modal="true" :aria-label="t('智能体管理')">
      <div class="am-head">
        <span class="am-title">🧠 {{ t('智能体管理') }}</span>
        <span class="am-sub">{{ t('自定义智能体角色与技能权限，运行时代理由「调度智能体（规划/验收）+ 子智能体（执行）」协作') }}</span>
        <button class="x-btn lg" @click="$emit('close')" :aria-label="t('关闭')">×</button>
      </div>

      <div class="am-body">
        <!-- 左：列表 -->
        <aside class="am-list">
          <button v-for="a in agents" :key="a.id" class="am-item" :class="{ on: cur && cur.id === a.id }"
                  @click="select(a)">
            <span class="am-emoji">{{ a.emoji }}</span>
            <span class="am-meta">
              <span class="am-name">{{ a.name }}<em v-if="a.builtin" class="am-badge">内置</em></span>
              <span class="am-desc">{{ a.description }}</span>
            </span>
          </button>
          <button class="am-new" @click="createNew">
            ＋ {{ t('新建智能体') }}
          </button>
        </aside>

        <!-- 右：编辑 -->
        <section v-if="cur" class="am-editor">
          <div class="am-field">
            <label class="am-label">{{ t('名称') }}</label>
            <div class="am-row2">
              <input v-model="cur.emoji" class="am-input am-emoji-input" maxlength="4" />
              <input v-model="cur.name" class="am-input" :placeholder="t('智能体名称')" />
            </div>
          </div>
          <div class="am-field">
            <label class="am-label">{{ t('一句话介绍') }}</label>
            <input v-model="cur.description" class="am-input" :placeholder="t('用于列表展示')" />
          </div>
          <div class="am-field">
            <label class="am-label">{{ t('系统提示词') }}</label>
            <textarea v-model="cur.system_prompt" class="am-input am-ta" rows="8" :placeholder="t('定义该智能体的角色、专长与回答风格')"></textarea>
          </div>
          <div class="am-field">
            <label class="am-label">
              {{ t('技能白名单') }}
              <span class="am-hint">{{ cur.available_skills ? t('仅以下技能可用（可多选）') : t('不限（全部技能可用）') }}</span>
            </label>
            <div class="am-skills">
              <button v-for="s in allSkills" :key="s.name" class="am-skill"
                      :class="{ on: isSkillOn(s.name) }"
                      @click="toggleSkill(s.name)">{{ skillLabel(s.name) }}</button>
            </div>
            <label class="am-lock">
              <input type="checkbox" :checked="!cur.available_skills" @change="toggleUnlimited" />
              <span>{{ t('不限技能（默认全量可用）') }}</span>
            </label>
          </div>
          <div class="am-field">
            <label class="am-label">{{ t('默认启用技能') }}</label>
            <div class="am-skills">
              <button v-for="s in allSkills" :key="'d' + s.name" class="am-skill"
                      :class="{ on: cur.default_skills.includes(s.name) }"
                      @click="toggleDefault(s.name)">{{ skillLabel(s.name) }}</button>
            </div>
          </div>

          <div class="am-actions">
            <button v-if="!cur.builtin" class="am-btn am-danger" @click="remove">
              🗑 {{ t('删除') }}
            </button>
            <span class="am-flex"></span>
            <button class="am-btn" @click="save">{{ t('保存') }}</button>
          </div>
        </section>
        <section v-else class="am-editor am-empty">{{ t('选择左侧智能体进行编辑，或新建智能体') }}</section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { t } from '../i18n'
import { api } from '../api/client'
const agents = ref([])
const allSkills = ref([])
const cur = ref(null)
const pristine = ref('')

async function load() {
  const r = await api.get('/agents')
  agents.value = r.agents || []
  const s = await api.get('/skills?all=1')
  allSkills.value = s.skills || []
}
function select(a) { cur.value = JSON.parse(JSON.stringify(a)); pristine.value = JSON.stringify(a) }
function createNew() {
  cur.value = { id: '', name: '', emoji: '🤖', description: '', system_prompt: '', default_skills: [], available_skills: null, builtin: false }
  pristine.value = ''
}
function isSkillOn(name) { return cur.value.available_skills ? cur.value.available_skills.includes(name) : true }
function toggleUnlimited(e) {
  cur.value.available_skills = e.target.checked ? null : (cur.value.available_skills || [])
}
function toggleSkill(name) {
  if (!cur.value.available_skills) cur.value.available_skills = []
  const i = cur.value.available_skills.indexOf(name)
  if (i >= 0) cur.value.available_skills.splice(i, 1); else cur.value.available_skills.push(name)
}
function toggleDefault(name) {
  const i = cur.value.default_skills.indexOf(name)
  if (i >= 0) cur.value.default_skills.splice(i, 1); else cur.value.default_skills.push(name)
}
function skillLabel(name) { return name.includes('__') ? name.split('__').pop() : name }
async function save() {
  if (!cur.value.name.trim()) { alert(t('请填写智能体名称')); return }
  if (!cur.value.system_prompt.trim()) { alert(t('请填写系统提示词')); return }
  const body = {
    name: cur.value.name, emoji: cur.value.emoji || '🤖', description: cur.value.description,
    system_prompt: cur.value.system_prompt,
    default_skills: cur.value.default_skills || [],
    available_skills: cur.value.available_skills,
  }
  if (cur.value.id) {
    await api.put(`/agents/${cur.value.id}`, body)
  } else {
    await api.post('/agents', body)
  }
  load()
  alert(t('已保存'))
}
async function remove() {
  if (!confirm(t('确定删除智能体') + `「${cur.value.name}」？`)) return
  await api.del(`/agents/${cur.value.id}`)
  cur.value = null
  load()
}
onMounted(load)
</script>

<style scoped>
.am-mask { position: fixed; inset: 0; background: rgba(16,24,34,.5); z-index: 300; display: flex; align-items: center; justify-content: center; }
.am-modal { width: 900px; max-width: 95vw; height: 80vh; background: var(--panel); color: var(--text); border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; box-shadow: 0 18px 50px rgba(0,0,0,.35); overflow: hidden; }
.am-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, var(--panel)), var(--panel)); }
.am-title { font-weight: 700; font-size: 15px; letter-spacing: 1px; }
.am-sub { flex: 1; color: var(--faint); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-body { flex: 1; display: flex; min-height: 0; }
.am-list { width: 300px; border-right: 1px solid var(--border); overflow: auto; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
.am-item { display: flex; gap: 10px; align-items: flex-start; padding: 9px 10px; border: 1px solid transparent; border-radius: 6px; background: none; color: var(--text); cursor: pointer; text-align: left; }
.am-item:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.am-item.on { background: color-mix(in srgb, var(--accent) 14%, transparent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.am-emoji { font-size: 20px; line-height: 1.3; }
.am-meta { flex: 1; min-width: 0; }
.am-name { font-weight: 600; font-size: 13.5px; display: flex; align-items: center; gap: 6px; color: var(--text); }
.am-badge { font-style: normal; font-size: 10px; color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 0 4px; }
.am-desc { display: block; font-size: 11.5px; color: var(--faint); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-new { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 9px; border: 1px dashed var(--border); border-radius: 6px; background: none; color: var(--accent); cursor: pointer; font-size: 13px; }
.am-new:hover { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }
.am-editor { flex: 1; overflow: auto; padding: 18px 22px; }
.am-empty { display: flex; align-items: center; justify-content: center; color: var(--faint); font-size: 13px; }
.am-field { margin-bottom: 16px; }
.am-label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 6px; color: var(--text); }
.am-hint { font-weight: 400; color: var(--faint); font-size: 11.5px; margin-left: 8px; }
.am-row2 { display: flex; gap: 8px; }
.am-emoji-input { width: 64px; text-align: center; }
.am-input { width: 100%; padding: 7px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); color: var(--text); font-size: 13px; }
.am-input:focus { outline: none; border-color: var(--accent); }
.am-ta { resize: vertical; font-family: inherit; line-height: 1.6; }
.am-skills { display: flex; flex-wrap: wrap; gap: 6px; }
.am-skill { padding: 4px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); color: var(--muted); font-size: 12px; cursor: pointer; transition: all .15s; }
.am-skill:hover { border-color: var(--accent-d); color: var(--accent-d); }
.am-skill.on { background: color-mix(in srgb, var(--accent) 18%, transparent); border-color: var(--accent); color: var(--accent-d); font-weight: 600; }
.am-lock { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--faint); margin-top: 8px; cursor: pointer; }
.am-actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.am-flex { flex: 1; }
.am-btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 18px; border-radius: 4px; border: 1px solid var(--border); background: var(--panel-2); color: var(--text); cursor: pointer; font-size: 13px; transition: all .15s; }
.am-btn:hover { border-color: var(--accent); color: var(--accent); }
.am-danger:hover { border-color: #e5484d; color: #e5484d; }
</style>
