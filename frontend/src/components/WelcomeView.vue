<template>
  <!-- 工程选择（VS Code 欢迎页形态）：启动后先停在这里，由用户新建 / 打开工程才进入主界面。
       左栏（活动栏 + 资源管理器）由外层 App 保留，本组件只占中间内容区。 -->
  <div class="wv">
    <!-- 方形容纳框：品牌 + 三个入口（横向并排）+ 最近工程列表，整块居中于内容区 -->
    <div class="wv-panel">
      <header class="wv-brand">
        <div class="wv-mark">能</div>
        <h1 class="wv-title">{{ t('能优算·工业能碳智控平台') }}</h1>
        <p class="wv-sub">{{ t('选择工程以开始：新建场景、打开本地工程包，或从最近的工程继续。') }}</p>
      </header>

      <!-- 开始：三个入口横向并排（文件夹式卡片，等宽同高） -->
      <section class="wv-starts">
        <button class="wv-start" @click="emit('new-scene')">
          <Icon name="newFile" :size="22" :stroke="1.5" class="ws-ic" />
          <b>{{ t('新建场景…') }}</b>
          <em>{{ t('选择行业类别，新建空白编排方案') }}</em>
        </button>
        <button class="wv-start" @click="pickPackage">
          <Icon name="open" :size="22" :stroke="1.5" class="ws-ic" />
          <b>{{ t('打开文件夹…') }}</b>
          <em>{{ t('导入本地 .ec 工程资源包并打开') }}</em>
        </button>
        <button class="wv-start" @click="emit('open-scene')">
          <Icon name="product" :size="22" :stroke="1.5" class="ws-ic" />
          <b>{{ t('打开场景…') }}</b>
          <em>{{ t('从已安装的工程列表中选择') }}</em>
        </button>
      </section>

      <!-- 最近：列表形式（无记录时回落到已安装工程） -->
      <section class="wv-recent">
        <h2 class="wv-h">{{ t('最近') }}</h2>
        <ul v-if="recents.length" class="wv-list">
          <li v-for="r in recents" :key="r.id">
            <div class="wv-rec" :class="{ off: !r.ready }" @click="openRecent(r)">
              <Icon name="product" :size="16" :stroke="1.5" class="wr-ic" />
              <span class="wr-tx">
                <b>{{ r.label }}</b>
                <em>{{ r.sub }}</em>
              </span>
              <span class="wr-time">{{ r.ts ? fromNow(r.ts) : '' }}</span>
              <button class="wr-x" :title="t('从最近列表移除')" :aria-label="t('从最近列表移除')" @click.stop="store.removeRecentScene(r.id)">×</button>
            </div>
          </li>
        </ul>
        <div v-else class="wv-empty">{{ t('暂无可用工程：请先新建场景，或导入 .ec 工程资源包。') }}</div>
      </section>

      <p v-if="busy" class="wv-busy">{{ busy }}</p>
    </div>
    <!-- 「打开文件夹」：选择本地 .ec 工程资源包（隐藏原生 file 输入，由按钮触发） -->
    <input ref="fileRef" class="wv-file" type="file" accept=".ec,.zip" @change="onPickPackage" />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'
import { api } from '../api/client'
import Icon from './Icon.vue'

const emit = defineEmits(['new-scene', 'open-scene'])
const store = useSimStore()
const fileRef = ref(null)
const busy = ref('')

const RECENT_MAX = 5   // 「最近」最多展示 5 条

// 最近工程：以记录为准（保留注册表里已不存在的条目，标记为未安装，不静默吞掉历史），
// 无记录时回落到注册表中已就绪的工程，避免首次进入是一块空列表。
const recents = computed(() => {
  const idx = store.sceneIndex || []
  const metaOf = (id) => idx.find((x) => x.id === id) || null
  const norm = (r) => {
    const m = metaOf(r.id)
    const label = (m && (m.label || m.name || m.industry)) || r.label || r.id
    const sub = (m && (m.industryGroup || m.industry)) || r.industry || r.id
    return { id: r.id, label, sub, ts: r.ts || 0, ready: m ? !!m.ready : false, known: !!m }
  }
  const list = (store.recentScenes || []).map(norm).filter((x) => x.known)
  if (list.length) return list.slice(0, RECENT_MAX)
  // 没有打开记录：展示已安装工程（未打开过也算可选项）
  return idx.filter((m) => m.ready).slice(0, RECENT_MAX).map((m) => ({
    id: m.id,
    label: m.label || m.name || m.industry || m.id,
    sub: m.industryGroup || m.industry || m.id,
    ts: 0,
    ready: true,
    known: true,
  }))
})

function fromNow(ts) {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return t('刚刚')
  if (s < 3600) return Math.floor(s / 60) + ' ' + t('分钟前')
  if (s < 86400) return Math.floor(s / 3600) + ' ' + t('小时前')
  if (s < 2592000) return Math.floor(s / 86400) + ' ' + t('天前')
  try { return new Date(ts).toLocaleDateString() } catch (e) { return '' }
}

async function openRecent(r) {
  if (!r.ready) {
    store.toast = t('「{label}」资源包尚未就绪：请先通过「打开文件夹…」导入该工程的 .ec 资源包', { label: r.label })
    return
  }
  await store.openProjectScene(r.id)
}

// 「打开文件夹」：选择 .ec 工程资源包 → 安装 → 打开（与「设置 → 场景 → 导入资源包」同一链路）
function pickPackage() { fileRef.value && fileRef.value.click() }
async function onPickPackage(e) {
  const f = e.target && e.target.files && e.target.files[0]
  if (e.target) e.target.value = ''   // 允许再次选择同一个文件
  if (!f) return
  busy.value = t('正在导入工程包…')
  try {
    const res = await api.installScenePackage(f)
    if (!res || !res.ok) {
      store.toast = t('导入工程包失败：') + ((res && res.error) || t('未知错误'))
      return
    }
    await store.refreshSceneIndex()
    const sc = res.scene || {}
    if (sc.id && sc.ready) await store.openScene(sc.id, { reload: true })   // 整页重建进入该工程
    else store.toast = t('工程包已导入：请在「打开场景…」中选择该工程')
  } catch (err) {
    store.toast = t('导入工程包失败：') + (err && err.message ? err.message : '')
  } finally {
    busy.value = ''
  }
}

onMounted(() => { if (!store.sceneIndex.length) store.refreshSceneIndex() })
</script>

<style scoped>
/* 内容区居中：面板用 margin:auto，溢出时可滚动且不裁掉顶部（flex 居中在溢出时会裁切）。
   欢迎页固定白底 + 灰框，与工作台明暗主题解耦：深色主题下文字也必须深色，
   故在本作用域内把中性令牌统一覆盖成这套（只影响本组件，不外溢）。
   分层靠背景明度而非线条：内容区白 → 承载内容的容器灰（无边框）→ 容器内的卡片白。 */
.wv {
  position: absolute; inset: 0; display: flex; overflow: auto; padding: 28px;
  background: #FFFFFF;
  --panel: #FFFFFF;      /* 容器内卡片 / 列表行：白，浮在灰容器上 */
  --panel-2: #F2F3F4;    /* 承载内容的容器底：灰 */
  --panel-3: #E9EAEC;
  --text: #1E1F22;
  --muted: #6B6E76;
  --faint: #9A9DA3;
  --line: #D9DADE;
  --line-soft: rgba(0,0,0,.07);
  --hover: rgba(255,255,255,.9);   /* 灰容器上的悬停：提亮为白，而不是压深 */
  --shadow: 0 1px 2px rgba(0,0,0,.08);   /* 白底配克制弱阴影，不用深色主题的重阴影 */
}
/* 方形容器：品牌 + 入口 + 最近整块装进去 —— 灰色承载面，不描边（靠与内容区的明度差划界） */
.wv-panel {
  margin: auto; width: 100%; max-width: 720px;
  background: var(--panel-2); border: 0; border-radius: var(--r-lg);
  padding: 30px 28px 20px; box-shadow: none;
}
/* 品牌区：居中，中性底 + 一个主题色方块，克制不花哨 */
.wv-brand { display: flex; flex-direction: column; align-items: center; text-align: center; }
.wv-mark {
  flex: 0 0 auto; width: 44px; height: 44px; border-radius: var(--r-md);
  background: var(--accent); color: var(--on-accent);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 600; letter-spacing: 0;
}
.wv-title { margin: 14px 0 0; font-size: 20px; font-weight: 600; letter-spacing: .3px; color: var(--text); }
.wv-sub { margin: 8px 0 0; max-width: 460px; font-size: var(--fs-body2); color: var(--muted); line-height: 1.7; }

.wv-h {
  margin: 0 0 8px; font-size: var(--fs-caption); font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase; color: var(--faint);
}
.wv-list { list-style: none; margin: 0; padding: 0; }

/* 三个入口：横向并排的文件夹式卡片，等宽同高，图标在上 */
.wv-starts { margin-top: 26px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 620px) { .wv-starts { grid-template-columns: minmax(0, 1fr); } }
.wv-start {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  /* button 作为 grid item 不会自动 stretch 到列宽（各卡文案长短不同会参差不齐），显式占满 */
  width: 100%; min-height: 104px; padding: 14px; text-align: left; cursor: pointer;
  /* 白卡片浮在灰容器上：不描边，靠明度差划界；悬停只加一层弱投影（不做底色位移） */
  background: var(--panel); border: 0; border-radius: var(--r-md);
  color: var(--text); font-size: var(--fs-body); box-shadow: 0 1px 2px rgba(0,0,0,.05);
  transition: background var(--dur-fast, .12s) var(--ease), box-shadow var(--dur-fast, .12s) var(--ease),
              transform var(--dur-fast, .12s) var(--ease);
}
.wv-start:hover { background: #FFFFFF; box-shadow: 0 2px 8px rgba(0,0,0,.10); }
.wv-start:active { transform: translateY(1px); }
.ws-ic { flex: 0 0 auto; color: var(--muted); margin-bottom: 2px; transition: color var(--dur-fast, .12s) var(--ease); }
.wv-start:hover .ws-ic { color: var(--text); }
.wv-start b { font-weight: 500; font-size: var(--fs-body); }
.wv-start em { font-style: normal; font-size: var(--fs-caption); color: var(--muted); line-height: 1.6; }

/* 最近：与上方入口卡片同处一张面板，用一条极淡分隔线划分区域（面板同色，线不可重） */
.wv-recent { margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line-soft); }
/* 最近工程行：名称 + 行业/标识，右侧时间与移除（移除 hover 才显示） */
.wv-rec {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  border-radius: var(--r); cursor: pointer;
  transition: background var(--dur-fast, .12s) var(--ease);
}
.wv-rec:hover { background: var(--hover); }
.wv-rec.off { opacity: .55; cursor: not-allowed; }
.wr-ic { flex: 0 0 auto; color: var(--muted); }
.wv-rec:hover .wr-ic { color: var(--text); }
.wr-tx { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.wr-tx b { font-weight: 400; font-size: var(--fs-body); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wr-tx em { font-style: normal; font-size: var(--fs-caption); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wr-time { flex: 0 0 auto; font-size: var(--fs-caption); color: var(--faint); font-variant-numeric: tabular-nums; }
.wr-x {
  flex: 0 0 auto; width: 20px; height: 20px; padding: 0; line-height: 1;
  border: 0; border-radius: var(--r-xs, 3px); background: transparent; color: var(--muted);
  font-size: 14px; cursor: pointer; opacity: 0;
  transition: opacity var(--dur-fast, .12s) var(--ease), background var(--dur-fast, .12s) var(--ease);
}
.wv-rec:hover .wr-x { opacity: 1; }
.wr-x:hover { background: var(--hover); color: var(--text); }

.wv-empty { font-size: var(--fs-body2); color: var(--muted); line-height: 1.7; padding: 4px 12px; }
.wv-busy { margin: 24px 0 0; font-size: var(--fs-body2); color: var(--muted); }
.wv-file { display: none; }
</style>
