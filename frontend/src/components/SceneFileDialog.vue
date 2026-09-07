<template>
  <div class="sf-mask" @click.self="$emit('close')">
    <div class="sf-modal">
      <div class="sf-head">
        <span class="sf-title">{{ title }}</span>
        <button class="sf-x" :title="t('关闭')" @click="$emit('close')">×</button>
      </div>

      <div class="sf-body">
        <!-- ===== 新建场景：先选场景类别（四大控排 / 其它） ===== -->
        <template v-if="mode === 'new'">
          <div class="sf-desc">{{ t('选择场景类别：平台将打开该类别下可用的场景资源包，并据此新建一份空白编排方案（当前场景的编排已自动保存，切回即用）。') }}</div>
          <div class="sf-cats">
            <button v-for="c in catGroups" :key="c.key" class="sf-cat" :class="{ on: pickedCat === c.key }" @click="pickedCat = c.key">
              <div class="c-top">
                <b>{{ t(c.label) }}</b>
                <span class="c-badge" :class="{ ok: !!c.meta }">{{ c.meta ? sceneLabel(c.meta) : t('需导入 .ec') }}</span>
              </div>
              <div class="c-desc">{{ t(c.desc) }}</div>
            </button>
          </div>
          <div v-if="curCat && !curCat.meta" class="sf-warn">
            {{ t('「{label}」类别暂无已安装的资源包：请先在「设置 → 场景」导入该场景的 .ec 文件。', { label: t(curCat.label) }) }}
            <button class="sf-link" @click="$emit('settings')">{{ t('前往导入资源包') }}</button>
          </div>
        </template>

        <!-- ===== 打开场景：按行业分组列出场景注册表 ===== -->
        <template v-else-if="mode === 'open'">
          <div class="sf-desc">{{ t('选择要打开的场景：切换场景会重建编排方案与数字孪生（各场景的编排方案独立保存）。') }}</div>
          <div v-for="g in sceneGroups" :key="g.name" class="sf-group">
            <div class="sf-gname">{{ g.name }}</div>
            <div v-for="m in g.items" :key="m.id" class="sf-row"
                 :class="{ on: pickedScene === m.id, cur: m.id === store.sceneId }"
                 @click="onPickScene(m)" @dblclick="onOk">
              <span class="sf-dot" :class="{ on: !!m.ready }"></span>
              <div class="sf-main">
                <div class="sf-name">{{ sceneLabel(m) }}<em v-if="m.enterprise" class="sf-ent">·{{ m.enterprise }}</em></div>
                <div class="sf-sub">{{ m.desc || m.industry || m.id }}<span v-if="pkgVersion(m)"> · {{ pkgVersion(m) }}</span></div>
              </div>
              <span v-if="m.id === store.sceneId" class="sf-tag cur">{{ t('当前') }}</span>
              <span v-else-if="!m.ready" class="sf-tag">{{ t('未安装 .ec') }}</span>
            </div>
          </div>
          <div v-if="!store.sceneIndex.length" class="sf-warn">{{ t('场景注册表为空：请确认后端可用，或导入 .ec 资源包。') }}</div>
        </template>

        <!-- ===== 另存为场景：把当前场景（含编排快照）打包为 .ec 下载 ===== -->
        <template v-else>
          <div class="sf-desc">{{ t('把当前场景（默认含当前编排方案快照）另存为可分发的 .ec 资源包；导出包为非内置分发包，重新导入后即回到当前编排态。') }}</div>
          <label class="sf-field">
            <span>{{ t('场景名称') }}</span>
            <input v-model="form.label" class="sf-input" :placeholder="t('例如：某钢厂 · 长流程场景')" />
          </label>
          <label class="sf-field">
            <span>{{ t('行业类别') }}</span>
            <select v-model="form.industry" class="sf-input">
              <option v-for="c in INDUSTRIES" :key="c" :value="c">{{ c }}</option>
            </select>
          </label>
          <label class="sf-field">
            <span>{{ t('版本号') }}</span>
            <input v-model="form.version" class="sf-input" placeholder="1.0.0" />
          </label>
          <label class="sf-check">
            <input type="checkbox" v-model="form.withScheme" />
            <span>{{ t('包含当前编排方案快照（导出后打开即为当前编排）') }}</span>
          </label>
          <div class="sf-meta">{{ t('当前场景：{label}（{id}）· 工序 {n} 个', { label: curLabel, id: store.sceneId, n: (store.scheme.nodes || []).length }) }}</div>
        </template>
      </div>

      <div class="sf-foot">
        <span class="sf-busy">{{ busy ? t('处理中…') : '' }}</span>
        <button class="sf-btn" @click="$emit('close')">{{ t('取消') }}</button>
        <button class="sf-btn primary" :disabled="busy || !canOk" @click="onOk">{{ okText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const props = defineProps({
  mode: { type: String, default: 'open' },   // new | open | saveAs
})
const emit = defineEmits(['close', 'settings'])

const store = useSimStore()

// 场景类别：四大控排（钢铁 / 水泥 / 化工 / 有色）+ 其它（通用资源包场景）
const CATEGORIES = [
  { key: 'steel', group: '钢铁', label: '钢铁', desc: '四大控排行业：内置钢铁碳引擎，支持长/短流程编排与全厂碳核算' },
  { key: 'cement', group: '水泥', label: '水泥', desc: '四大控排行业：水泥窑线工艺，需导入对应 .ec 资源包' },
  { key: 'chem', group: '化工', label: '化工', desc: '四大控排行业：化工装置工艺，需导入对应 .ec 资源包' },
  { key: 'nonferrous', group: '有色', label: '有色', desc: '四大控排行业：有色/电解铝工艺，需导入对应 .ec 资源包' },
  { key: 'other', group: '其它', label: '其它', desc: '非四大控排：通用资源包场景（内置示例：机房温控）' },
]
const INDUSTRIES = ['钢铁', '水泥', '化工', '有色', '其它']

const busy = ref(false)
const pickedCat = ref('steel')
const pickedScene = ref('')

const title = computed(() => ({ new: t('新建场景'), open: t('打开场景'), saveAs: t('另存为场景') }[props.mode] || t('场景')))
const okText = computed(() => ({ new: t('新建'), open: t('打开'), saveAs: t('另存为 .ec') }[props.mode] || t('确定')))

const sceneLabel = (m) => (m && (m.label || m.name || m.industry || m.id)) || ''
const pkgVersion = (m) => (m && m.package && (m.package.version || m.version)) || ''
const readyOf = (group) => {
  if (group === '钢铁') return store.sceneIndex.find((m) => m.id === 'steel' && m.ready) || null
  return store._readySceneOfGroup(group)
}
const catGroups = computed(() => CATEGORIES.map((c) => ({ ...c, meta: readyOf(c.group) })))
const curCat = computed(() => catGroups.value.find((c) => c.key === pickedCat.value) || null)

// 打开场景：按行业分组（与「设置 → 场景」同序）
const sceneGroups = computed(() => {
  const map = new Map()
  for (const m of store.sceneIndex) {
    const g = m.industryGroup || '其它'
    if (!map.has(g)) map.set(g, [])
    map.get(g).push(m)
  }
  return [...map.entries()].map(([name, items]) => ({
    name,
    items: items.slice().sort((a, b) => (a.order == null ? 99 : a.order) - (b.order == null ? 99 : b.order)),
  })).sort((a, b) => {
    const oa = a.items[0] && a.items[0].order != null ? a.items[0].order : 99
    const ob = b.items[0] && b.items[0].order != null ? b.items[0].order : 99
    return oa - ob
  })
})
function onPickScene(m) {
  if (!m || !m.ready || m.id === store.sceneId) return
  pickedScene.value = m.id
}

// 另存为场景表单
const form = ref({ label: '', industry: '钢铁', version: '1.0.0', withScheme: true })
const curLabel = computed(() => {
  const m = store.sceneIndex.find((x) => x.id === store.sceneId)
  return sceneLabel(m) || store.sceneId
})
function bumpVersion(v) {
  const m = String(v || '').match(/^(\d+)\.(\d+)\.(\d+)$/)
  if (!m) return '1.0.0'
  return `${m[1]}.${m[2]}.${Number(m[3]) + 1}`
}

const canOk = computed(() => {
  if (props.mode === 'new') return !!(curCat.value && curCat.value.meta)
  if (props.mode === 'open') return !!pickedScene.value
  return !!(form.value.label || '').trim()
})

onMounted(async () => {
  if (!store.sceneIndex.length) await store.refreshSceneIndex()
  const cur = store.sceneIndex.find((x) => x.id === store.sceneId)
  const ind = (cur && (cur.industryGroup || cur.industry)) || '钢铁'
  form.value = {
    label: sceneLabel(cur) || '',
    industry: INDUSTRIES.includes(ind) ? ind : '钢铁',
    version: bumpVersion(pkgVersion(cur)),
    withScheme: true,
  }
  // 新建场景默认选中当前场景所属类别
  const hit = catGroups.value.find((c) => c.group === ind)
  if (hit) pickedCat.value = hit.key
})

async function onOk() {
  if (busy.value || !canOk.value) return
  busy.value = true
  try {
    if (props.mode === 'new') {
      const c = curCat.value
      const ok = await store.openScene(c.meta.id)
      if (ok) {
        store.enterEdit()
        store.clearScheme()   // 新场景从空白编排开始
        store.pushCmd(t('已基于「{label}」类别新建场景方案：编排画布已清空，可拖入工艺节点开始编排。', { label: t(c.label) }), 'out')
        store.toast = t('已新建场景「{label}」', { label: sceneLabel(c.meta) })
      }
    } else if (props.mode === 'open') {
      const id = pickedScene.value
      const ok = await store.openScene(id)
      if (!ok) return
    } else {
      const f = form.value
      const file = await store.exportSceneAsPackage({
        label: f.label.trim(),
        industry: f.industry,
        version: f.version.trim() || '1.0.0',
        withScheme: f.withScheme,
      })
      store.pushCmd(t('已另存场景包：{file}（行业 {ind} · 版本 {ver}）', { file: file || (store.sceneId + '.ec'), ind: f.industry, ver: f.version }), 'out')
      store.toast = t('已另存为场景资源包「{label}」', { label: f.label.trim() })
    }
    emit('close')
  } catch (e) {
    store.toast = (props.mode === 'saveAs' ? t('另存为场景失败：') : t('操作失败：')) + (e && e.message ? e.message : '')
    store.notify('error', title.value, e && e.message ? e.message : String(e))
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.sf-mask { position: fixed; inset: 0; z-index: 4000; background: rgba(12, 16, 20, 0.45); display: flex; align-items: center; justify-content: center; }
.sf-modal { width: 560px; max-width: calc(100vw - 40px); max-height: calc(100vh - 80px); display: flex; flex-direction: column; background: var(--panel, #1b2028); border: 1px solid var(--line, #2c333d); border-radius: 6px; box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45); }
.sf-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid var(--line, #2c333d); }
.sf-title { font-size: 13px; font-weight: 600; }
.sf-x { border: 0; background: transparent; color: var(--muted, #8b95a3); font-size: 16px; line-height: 1; cursor: pointer; padding: 2px 6px; border-radius: 3px; }
.sf-x:hover { color: var(--text, #e6ebf2); background: rgba(255, 255, 255, 0.06); }
.sf-body { padding: 12px; overflow: auto; }
.sf-desc { font-size: 11.5px; color: var(--muted, #8b95a3); line-height: 1.7; margin-bottom: 10px; }
.sf-cats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sf-cat { text-align: left; padding: 8px 10px; border: 1px solid var(--line, #2c333d); border-radius: 4px; background: transparent; color: var(--text, #e6ebf2); cursor: pointer; }
.sf-cat:hover { border-color: var(--accent2, #4f9d6b); }
.sf-cat.on { border-color: var(--accent, #c9a33e); background: rgba(201, 163, 62, 0.09); }
.c-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 12px; margin-bottom: 4px; }
.c-badge { font-size: 10px; color: var(--muted, #8b95a3); border: 1px solid var(--line, #2c333d); border-radius: 8px; padding: 1px 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 46%; }
.c-badge.ok { color: var(--accent2, #4f9d6b); border-color: rgba(79, 157, 107, 0.5); }
.c-desc { font-size: 10.5px; color: var(--muted, #8b95a3); line-height: 1.6; }
.sf-warn { margin-top: 10px; font-size: 11px; color: #d08a3a; line-height: 1.7; }
.sf-link { border: 0; background: transparent; color: var(--accent-d, #d8b45c); font-size: 11px; cursor: pointer; padding: 0 2px; text-decoration: underline; }
.sf-group + .sf-group { margin-top: 10px; }
.sf-gname { font-size: 10px; color: var(--accent2, #4f9d6b); margin-bottom: 4px; }
.sf-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid transparent; border-radius: 4px; cursor: pointer; }
.sf-row:hover { background: rgba(255, 255, 255, 0.04); }
.sf-row.on { border-color: var(--accent, #c9a33e); background: rgba(201, 163, 62, 0.08); }
.sf-row.cur { cursor: default; opacity: 0.75; }
.sf-dot { width: 6px; height: 6px; border-radius: 50%; background: #6b7480; flex: 0 0 auto; }
.sf-dot.on { background: var(--accent2, #4f9d6b); }
.sf-main { flex: 1; min-width: 0; }
.sf-name { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sf-ent { font-size: 10px; color: var(--muted, #8b95a3); font-style: normal; }
.sf-sub { font-size: 10.5px; color: var(--muted, #8b95a3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sf-tag { font-size: 10px; color: var(--muted, #8b95a3); border: 1px solid var(--line, #2c333d); border-radius: 8px; padding: 1px 6px; }
.sf-tag.cur { color: var(--accent, #c9a33e); border-color: rgba(201, 163, 62, 0.5); }
.sf-field { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 11.5px; }
.sf-field > span { width: 68px; flex: 0 0 auto; color: var(--muted, #8b95a3); }
.sf-input { flex: 1; min-width: 0; font-size: 11.5px; padding: 4px 6px; border: 1px solid var(--line, #2c333d); border-radius: 3px; background: var(--bg, #14181e); color: var(--text, #e6ebf2); }
.sf-check { display: flex; align-items: center; gap: 6px; font-size: 11.5px; margin-top: 2px; cursor: pointer; }
.sf-meta { margin-top: 8px; font-size: 10.5px; color: var(--muted, #8b95a3); }
.sf-foot { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--line, #2c333d); }
.sf-busy { flex: 1; font-size: 11px; color: var(--muted, #8b95a3); }
.sf-btn { font-size: 11.5px; padding: 5px 12px; border: 1px solid var(--line, #2c333d); border-radius: 3px; background: transparent; color: var(--text, #e6ebf2); cursor: pointer; }
.sf-btn:hover { border-color: var(--accent2, #4f9d6b); }
.sf-btn.primary { background: var(--accent, #c9a33e); border-color: var(--accent, #c9a33e); color: #1a1a1a; }
.sf-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
