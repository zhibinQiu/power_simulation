<template>
  <div class="sf-mask" @click.self="$emit('close')">
    <div class="sf-modal">
      <div class="sf-head">
        <span class="sf-title">{{ title }}</span>
        <button class="sf-x" :title="t('关闭')" @click="$emit('close')">×</button>
      </div>

      <div class="sf-body">
        <!-- ===== 新建场景：先选场景类别（四大控排 / 其它），按组分区 —— 类别卡片两列等宽，
               「其它」单独成组并独占一行，避免出现半格孤卡导致排版参差 ===== -->
        <template v-if="mode === 'new'">
          <div class="sf-desc">{{ t('选择场景类别：将打开该类别可用的资源包并新建空白编排（切换场景前请先「保存」）。') }}</div>
          <div v-for="g in catSections" :key="g.key" class="sf-sec">
            <div class="sf-sec-h">{{ t(g.name) }}</div>
            <div class="sf-cats" :class="{ one: g.items.length === 1 }">
              <button v-for="c in g.items" :key="c.key" class="sf-cat" :class="{ on: pickedCat === c.key }"
                      :disabled="!c.meta" :title="c.meta ? sceneLabel(c.meta) : t('该类别暂无已安装的资源包')"
                      @click="pickedCat = c.key">
                <span class="cat-hd">
                  <b>{{ t(c.label) }}</b>
                  <span class="cat-badge" :class="{ ok: !!c.meta }">{{ c.meta ? sceneLabel(c.meta) : t('需导入 .ec') }}</span>
                </span>
                <span class="cat-desc">{{ t(c.desc) }}</span>
              </button>
            </div>
          </div>
          <div v-if="curCat && !curCat.meta" class="sf-note">
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
          <div v-if="!store.sceneIndex.length" class="sf-note">{{ t('场景注册表为空：请确认后端可用，或导入 .ec 资源包。') }}</div>
        </template>

        <!-- ===== 另存为场景：把当前场景（含编排快照）打包为 .ec 下载 ===== -->
        <template v-else>
          <div class="sf-desc">{{ t('把当前场景另存为可分发的 .ec 资源包（含编排快照，重新导入即回到当前编排态）。') }}</div>
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
// 描述不再重复「四大控排行业」前缀：该语义由分组标题承担，卡片内只写工艺差异
const CATEGORIES = [
  { key: 'steel', group: '钢铁', label: '钢铁', desc: '内置钢铁碳引擎，支持长 / 短流程编排与全厂碳核算' },
  { key: 'cement', group: '水泥', label: '水泥', desc: '水泥窑线工艺，需导入对应 .ec 资源包' },
  { key: 'chem', group: '化工', label: '化工', desc: '化工装置工艺，需导入对应 .ec 资源包' },
  { key: 'nonferrous', group: '有色', label: '有色', desc: '有色 / 电解铝工艺，需导入对应 .ec 资源包' },
  { key: 'other', group: '其它', label: '其它', desc: '通用资源包场景（内置示例：机房温控）' },
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
// 分区呈现：四大控排（2×2 等宽）与「其它」（独占一行），避免第 5 张卡片落单成半格
const catSections = computed(() => [
  { key: 'key', name: '四大控排行业', items: catGroups.value.filter((c) => c.key !== 'other') },
  { key: 'other', name: '其它行业', items: catGroups.value.filter((c) => c.key === 'other') },
].filter((g) => g.items.length))

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
  // 新建场景默认选中当前场景所属类别；该类别无可用资源包时退到第一个可用的类别，
  // 避免「打开弹窗即底部按钮禁用、却没有任何提示指向可选项」
  const hit = catGroups.value.find((c) => c.group === ind)
  if (hit) pickedCat.value = hit.key
  if (!(curCat.value && curCat.value.meta)) {
    const fb = catGroups.value.find((c) => c.meta)
    if (fb) pickedCat.value = fb.key
  }
})

async function onOk() {
  if (busy.value || !canOk.value) return
  busy.value = true
  try {
    if (props.mode === 'new') {
      const c = curCat.value
      // openProjectScene：目标已是当前场景时也能正确「进入工作区」（openScene 会早退不记入最近）
      const ok = await store.openProjectScene(c.meta.id)
      if (ok) {
        store.enterEdit()
        store.clearScheme()   // 新场景从空白编排开始
        store.pushCmd(t('已基于「{label}」类别新建场景方案：编排画布已清空，可拖入工艺节点开始编排。', { label: t(c.label) }), 'out')
        store.toast = t('已新建场景「{label}」', { label: sceneLabel(c.meta) })
      }
    } else if (props.mode === 'open') {
      // 打开场景 = 切换工作区：整页重新加载（所有页面按新场景重建），不自动打开任何功能视图标签
      const id = pickedScene.value
      const ok = await store.openScene(id, { reload: true })
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
/* overflow:hidden —— 头/底用底色铺底，需靠容器圆角裁掉直角 */
.sf-modal { width: 600px; max-width: calc(100vw - 40px); max-height: calc(100vh - 80px); display: flex; flex-direction: column; overflow: hidden; background: var(--panel, #1b2028); border: 1px solid var(--stroke, var(--line, #2c333d)); border-radius: var(--r-lg, 10px); box-shadow: var(--glass-shadow-lg, 0 18px 48px rgba(0, 0, 0, 0.45)); }
/* 头 / 底：铺 --head-bg 与内容区形成色差，不再用灰分隔线 */
.sf-head { display: flex; align-items: center; justify-content: space-between; min-height: var(--head-h, 28px); padding: 8px 8px 8px 14px; background: var(--head-bg, var(--panel-2)); }
.sf-title { font-size: var(--fs-head, 14px); font-weight: 600; color: var(--text, #e6ebf2); }
.sf-x { flex: 0 0 auto; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: var(--r-sm, 4px); background: transparent; color: var(--muted, #8b95a3); font-size: 16px; line-height: 1; cursor: pointer; transition: background var(--dur-fast, .12s) var(--ease), color var(--dur-fast, .12s) var(--ease); }
.sf-x:hover { color: var(--text, #e6ebf2); background: var(--hover); }
.sf-body { padding: 14px; overflow: auto; }
.sf-desc { font-size: var(--fs-body2, 11px); color: var(--muted, #8b95a3); line-height: 1.7; margin: 0 0 12px; }
/* 分组：标题 12px/600 + 主题色竖线（与右侧属性面板同一契约） */
.sf-sec + .sf-sec { margin-top: 14px; }
.sf-sec-h { display: flex; align-items: center; padding-left: 8px; margin-bottom: 8px; font-size: var(--fs-body, 12px); font-weight: 600; color: var(--text, #e6ebf2); border-left: 2px solid var(--accent, #c9a33e); line-height: 1.3; }
/* 类别卡片：两列等宽同高，名称行与描述行分离，徽标不再与名称抢宽度；
   卡片本身 min-width:0 强制等分 grid track，避免中文长描述把卡片撑成宽窄不一 */
.sf-cats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.sf-cats.one { grid-template-columns: minmax(0, 1fr); }   /* 单卡片组（其它）：独占一行 */
.sf-cat {
  display: flex; flex-direction: column; gap: 4px; min-height: 62px; width: 100%; min-width: 0;
  padding: 9px 11px; text-align: left; cursor: pointer;
  border: 1px solid var(--stroke-soft, var(--line, #2c333d)); border-radius: var(--r, 6px);
  background: var(--fill-1, rgba(0,0,0,.045)); color: var(--text, #e6ebf2); font-size: var(--fs-body, 12px);
  transition: background var(--dur-fast, .12s) var(--ease), border-color var(--dur-fast, .12s) var(--ease),
              box-shadow var(--dur-fast, .12s) var(--ease);
}
.sf-cat:hover:not(:disabled) { border-color: var(--stroke, var(--line, #2c333d)); background: var(--fill-2, rgba(0,0,0,.07)); }
.sf-cat.on { border-color: var(--accent, #c9a33e); background: var(--accent-l, rgba(201, 163, 62, 0.12)); }
.sf-cat:disabled { cursor: not-allowed; }
.sf-cat:disabled .cat-hd b,
.sf-cat:disabled .cat-desc { color: var(--muted, #8b95a3); }
.sf-cat:focus-visible { outline: 2px solid var(--accent, #c9a33e); outline-offset: 1px; }
.cat-hd { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.cat-hd b { font-weight: 600; font-size: var(--fs-title, 13px); }
.cat-badge { flex: 0 1 auto; min-width: 0; max-width: 50%; font-size: var(--fs-caption, 10px); color: var(--muted, #8b95a3); border: 1px solid var(--stroke-soft, var(--line, #2c333d)); border-radius: 8px; padding: 1px 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cat-badge.ok { color: var(--text, #e6ebf2); border-color: var(--stroke, var(--line, #2c333d)); }
.cat-desc { font-size: var(--fs-body2, 11px); color: var(--muted, #8b95a3); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
/* 提示条：弱底 + 警告色竖线，与分组标题同构 */
.sf-note { margin-top: 12px; padding: 8px 10px; border-left: 2px solid var(--yellow); border-radius: var(--r-sm, 4px); background: var(--fill-1, rgba(0,0,0,.045)); font-size: var(--fs-body2, 11px); color: var(--muted, #8b95a3); line-height: 1.7; }
.sf-link { border: 0; background: transparent; color: var(--accent-d, #d8b45c); font-size: var(--fs-body2, 11px); cursor: pointer; padding: 0 2px; text-decoration: underline; }
.sf-group + .sf-group { margin-top: 10px; }
.sf-gname { padding-left: 8px; margin-bottom: 6px; font-size: var(--fs-body, 12px); font-weight: 600; color: var(--text, #e6ebf2); border-left: 2px solid var(--accent, #c9a33e); line-height: 1.3; }
.sf-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid transparent; border-radius: 4px; cursor: pointer; }
.sf-row:hover { background: var(--hover); }
.sf-row.on { border-color: var(--accent, #c9a33e); background: var(--sel, rgba(0,0,0,.085)); }
.sf-row.cur { cursor: default; opacity: 0.75; }
.sf-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--faint); flex: 0 0 auto; }
.sf-dot.on { background: var(--accent2, #4f9d6b); }
.sf-main { flex: 1; min-width: 0; }
.sf-name { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sf-ent { font-size: 10px; color: var(--muted, #8b95a3); font-style: normal; }
.sf-sub { font-size: 11px; color: var(--muted, #8b95a3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sf-tag { font-size: 10px; color: var(--muted, #8b95a3); border: 1px solid var(--line, #2c333d); border-radius: 8px; padding: 1px 6px; }
.sf-tag.cur { color: var(--accent, #c9a33e); border-color: rgba(201, 163, 62, 0.5); }
.sf-field { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: var(--fs-body, 12px); }
.sf-field > span { width: 72px; flex: 0 0 auto; color: var(--muted, #8b95a3); }
.sf-input { flex: 1; min-width: 0; font-size: var(--fs-body, 12px); padding: 4px 8px; border: 1px solid var(--stroke-soft, var(--line, #2c333d)); border-radius: var(--r-sm, 4px); background: var(--bg, #14181e); color: var(--text, #e6ebf2); }
.sf-check { display: flex; align-items: center; gap: 6px; font-size: var(--fs-body, 12px); margin-top: 2px; cursor: pointer; }
.sf-meta { margin-top: 8px; font-size: var(--fs-body2, 11px); color: var(--muted, #8b95a3); }
/* 底部操作区：与头部同底同色差（不画线），主操作右对齐 */
.sf-foot { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 10px 12px; background: var(--head-bg, var(--panel-2)); }
.sf-busy { flex: 1; font-size: var(--fs-body2, 11px); color: var(--muted, #8b95a3); }
.sf-btn { font-size: var(--fs-body, 12px); padding: 0 var(--btn-pad-x-lg, 12px); min-height: var(--btn-h-lg, 28px); min-width: var(--btn-min-w, 76px); display: inline-flex; align-items: center; justify-content: center; border: 1px solid transparent; border-radius: var(--r, 6px); background: var(--btn-bg, var(--panel-3, #2c333d)); color: var(--text, #e6ebf2); cursor: pointer; transition: background var(--dur-fast, .12s) var(--ease); }
.sf-btn:hover { background: var(--btn-bg-hover, #3a3f47); }
.sf-btn.primary { background: var(--accent, #c9a33e); border-color: var(--accent, #c9a33e); color: var(--on-accent); }
.sf-btn.primary:hover { background: var(--accent-h, #b8932f); border-color: var(--accent-h, #b8932f); }
.sf-btn:active { transform: translateY(1px); }
.sf-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
</style>
